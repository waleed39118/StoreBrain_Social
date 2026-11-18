"""Bulk catalog import from Excel (.xlsx) or CSV, with Arabic/English headers.

Guarantees
----------
* Validate-then-apply: every row is validated first; by default any error rejects the
  whole file (nothing is written). ``skip_invalid=True`` applies only the valid rows.
* ``dry_run=True`` returns the full report without touching the database (preview).
* Upsert by SKU, falling back to barcode. Rows without SKU but with barcode use the barcode
  as SKU. Duplicate keys inside one file are reported.
* Every stock change is written to ``stock_movements`` (reason=import).
* Hardened parsing: size/row limits; openpyxl uses defusedxml when installed (XML bombs).
"""
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

import pandas as pd
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.barcode import normalize_barcode
from app.database import begin_write
from app.models import MovementReason, Product, ProductCondition, StockMovement

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000

# Canonical column -> accepted header spellings (compared after normalisation).
HEADER_ALIASES: dict[str, set[str]] = {
    "sku": {"sku", "code", "item code", "product code", "رمز", "الرمز", "كود", "رمز المنتج", "كود المنتج"},
    "barcode": {"barcode", "ean", "upc", "gtin", "باركود", "الباركود", "رقم الباركود"},
    "name_en": {"name", "name en", "name_en", "english name", "product name", "الاسم بالانجليزية", "الاسم الانجليزي"},
    "name_ar": {"name ar", "name_ar", "arabic name", "الاسم", "اسم المنتج", "الاسم بالعربية", "الاسم العربي"},
    "category": {"category", "group", "الفئة", "التصنيف", "القسم"},
    "price": {"price", "sale price", "selling price", "السعر", "سعر البيع"},
    "cost": {"cost", "cost price", "purchase price", "التكلفة", "سعر الشراء", "سعر التكلفة"},
    "stock_qty": {"stock", "qty", "quantity", "stock qty", "stock_qty", "الكمية", "المخزون", "الرصيد"},
    "reorder_level": {"reorder level", "reorder_level", "min stock", "حد الطلب", "الحد الأدنى", "حد إعادة الطلب"},
    "lead_time_days": {"lead time", "lead_time_days", "lead time days", "مدة التوريد", "أيام التوريد"},
    "expiry_date": {"expiry", "expiry date", "expiry_date", "exp", "تاريخ الانتهاء", "الصلاحية"},
    "condition": {"condition", "status", "الحالة"},
}
TEMPLATE_HEADERS = ["SKU", "Barcode", "Name EN", "Name AR", "Category", "Price", "Cost",
                    "Stock", "Reorder Level", "Lead Time Days", "Expiry Date"]


class StockMode(StrEnum):
    SET = "set"   # file quantity becomes the stock level (stock-take)
    ADD = "add"   # file quantity is added to current stock (goods received)


class ImportRow(BaseModel):
    sku: str | None = Field(None, max_length=64)
    barcode: str | None = None
    name_en: str | None = Field(None, max_length=200)
    name_ar: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=100)
    price: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    cost: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    stock_qty: int | None = Field(None, ge=0)
    reorder_level: int | None = Field(None, ge=0)
    lead_time_days: int | None = Field(None, ge=0)
    expiry_date: date | None = None
    condition: ProductCondition | None = None

    @field_validator("barcode", mode="before")
    @classmethod
    def _barcode(cls, v):
        return normalize_barcode(v)

    @field_validator("sku", "name_en", "name_ar", "category", mode="before")
    @classmethod
    def _text(cls, v):
        if v is None or (isinstance(v, float) and v != v):
            return None
        if isinstance(v, float) and v.is_integer():
            v = int(v)                        # numeric SKUs read from Excel
        return str(v).strip() or None

    @field_validator("price", "cost", mode="before")
    @classmethod
    def _round_money(cls, v):
        return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"))

    @field_validator("stock_qty", "reorder_level", "lead_time_days", mode="before")
    @classmethod
    def _int(cls, v):
        if isinstance(v, float):
            if not v.is_integer():
                raise ValueError("must be a whole number")
            return int(v)
        return v

    @field_validator("expiry_date", mode="before")
    @classmethod
    def _date(cls, v):
        if isinstance(v, pd.Timestamp):
            return v.date()
        return v

    @field_validator("condition", mode="before")
    @classmethod
    def _cond(cls, v):
        return str(v).strip().lower() if v is not None else None


@dataclass
class ImportReport:
    total_rows: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    applied: bool = False
    dry_run: bool = False
    unknown_columns: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)   # {"row": excel_row, "error": "..."}


class ImportFileError(ValueError):
    pass


def _norm_header(h: str) -> str:
    h = re.sub(r"[\s_\-]+", " ", str(h).strip().lower())
    return h.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")


_LOOKUP = {_norm_header(a): canon for canon, aliases in HEADER_ALIASES.items() for a in aliases}


def read_table(filename: str, data: bytes) -> pd.DataFrame:
    if len(data) > MAX_FILE_BYTES:
        raise ImportFileError("File too large (max 5 MB)")
    name = filename.lower()
    try:
        if name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(data), engine="openpyxl", dtype=object, nrows=MAX_ROWS + 1)
        elif name.endswith((".csv", ".txt")):
            df = None
            for enc in ("utf-8-sig", "cp1256"):         # cp1256 = Arabic Windows Excel exports
                try:
                    df = pd.read_csv(io.BytesIO(data), dtype=str, encoding=enc, sep=None,
                                     engine="python", nrows=MAX_ROWS + 1, keep_default_na=False)
                    break
                except UnicodeDecodeError:
                    continue
            if df is None:
                raise ImportFileError("Unsupported text encoding (use UTF-8)")
            df = df.replace({"": None})
        else:
            raise ImportFileError("Unsupported file type. Use .xlsx or .csv (save .xls as .xlsx)")
    except ImportFileError:
        raise
    except Exception as exc:  # parser errors -> clean 400 for the user
        raise ImportFileError(f"Could not read file: {exc}") from exc
    if len(df) > MAX_ROWS:
        raise ImportFileError(f"Too many rows (max {MAX_ROWS})")
    return df.dropna(how="all")


class CatalogImporter:
    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, filename: str, data: bytes, *, stock_mode: StockMode = StockMode.SET,
            dry_run: bool = False, skip_invalid: bool = False) -> ImportReport:
        df = read_table(filename, data)
        rename, unknown = {}, []
        for col in df.columns:
            canon = _LOOKUP.get(_norm_header(col))
            (rename.__setitem__(col, canon) if canon else unknown.append(str(col)))
        df = df.rename(columns=rename)[list(dict.fromkeys(rename.values()))]
        if not {"sku", "barcode"} & set(df.columns):
            raise ImportFileError("File needs a SKU or Barcode column")

        report = ImportReport(total_rows=len(df), dry_run=dry_run, unknown_columns=unknown)
        valid: list[tuple[int, ImportRow]] = []
        seen: set[str] = set()
        for idx, raw in enumerate(df.to_dict("records")):
            excel_row = idx + 2  # header is row 1
            try:
                row = ImportRow.model_validate({k: v for k, v in raw.items() if not _blank(v)})
            except (ValidationError, ValueError) as exc:
                report.errors.append({"row": excel_row, "error": _fmt(exc)})
                continue
            row.sku = row.sku or row.barcode
            if not row.sku:
                report.errors.append({"row": excel_row, "error": "SKU or barcode is required"})
                continue
            dup = next((k for k in (row.sku, row.barcode) if k and k in seen), None)
            if dup:
                report.errors.append({"row": excel_row, "error": f"Duplicate in file: {dup}"})
                continue
            seen.update(k for k in (row.sku, row.barcode) if k)
            valid.append((excel_row, row))

        if report.errors and not skip_invalid:
            return report                              # atomic: reject the whole file
        begin_write(self.db)
        try:
            self._apply(valid, stock_mode, report)
            if dry_run or (report.errors and not skip_invalid):
                self.db.rollback()
            else:
                self.db.commit()
                report.applied = True
        except Exception:
            self.db.rollback()
            raise
        report.skipped = report.total_rows - report.created - report.updated
        return report

    def _apply(self, rows: list[tuple[int, ImportRow]], mode: StockMode, report: ImportReport) -> None:
        fields = ("barcode", "name_en", "name_ar", "category", "price", "cost", "reorder_level",
                  "lead_time_days", "expiry_date", "condition")
        for excel_row, r in rows:
            # SKU is the primary key of identity; barcode is only a fallback match.
            p = self.db.scalar(select(Product).where(Product.sku == r.sku))
            if p is None and r.barcode:
                p = self.db.scalar(select(Product).where(Product.barcode == r.barcode))
            if r.barcode:
                owner = self.db.scalar(select(Product.sku).where(Product.barcode == r.barcode))
                if owner and p is not None and owner != p.sku:
                    report.errors.append({"row": excel_row,
                                          "error": f"Barcode {r.barcode} already belongs to {owner}"})
                    continue
            with self.db.begin_nested():               # savepoint per row
                if p is None:
                    if not (r.name_en or r.name_ar) or r.price is None:
                        report.errors.append({"row": excel_row,
                                              "error": "New product needs a name and a price"})
                        continue
                    p = Product(sku=r.sku, name_en=r.name_en or r.name_ar, stock_qty=0,
                                **{f: getattr(r, f) for f in fields
                                   if f != "name_en" and getattr(r, f) is not None})
                    self.db.add(p)
                    self.db.flush()
                    report.created += 1
                else:
                    for f in fields:
                        if getattr(r, f) is not None:
                            setattr(p, f, getattr(r, f))
                    report.updated += 1
                if r.stock_qty is not None:
                    delta = r.stock_qty - p.stock_qty if mode is StockMode.SET else r.stock_qty
                    if delta:
                        p.stock_qty += delta
                        self.db.add(StockMovement(product_id=p.id, delta=delta,
                                                  reason=MovementReason.IMPORT, ref="file-import"))
                self.db.flush()


def build_template() -> bytes:
    """Excel template with the bilingual headers and one example row."""
    buf = io.BytesIO()
    example = ["MILK-1L", "6291041500213", "Milk 1L", "حليب 1 لتر", "dairy", 1.5, 1.0, 24, 10, 3, ""]
    pd.DataFrame([example], columns=TEMPLATE_HEADERS).to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _blank(v) -> bool:
    """Empty Excel/CSV cell: None, NaN, NaT or whitespace-only text."""
    if isinstance(v, str):
        return not v.strip()
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _fmt(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'row'}: {e['msg']}" for e in exc.errors())
    return str(exc)
