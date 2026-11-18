import io

import pandas as pd
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.database import Base, engine
from app.migrate import alembic_config
from tests.conftest import reset_db


# ---------- Alembic ----------
def test_migrations_match_models():
    """Fails if someone changes models.py without adding a migration."""
    reset_db()
    command.upgrade(alembic_config(), "head")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True, "render_as_batch": True})
        assert compare_metadata(ctx, Base.metadata) == []


def test_downgrade_upgrade_roundtrip():
    reset_db()
    cfg = alembic_config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


# ---------- barcode & manual edit ----------
def test_barcode_lookup_and_validation(seeded):
    r = seeded.patch("/api/v1/products/MILK-1L", json={"barcode": "6291041500213", "price": "1.60"})
    assert r.status_code == 200 and r.json()["barcode"] == "6291041500213"
    r = seeded.get("/api/v1/products/by-barcode/6291041500213")
    assert r.json()["sku"] == "MILK-1L" and r.json()["price"] == "1.60"
    assert seeded.get("/api/v1/products/by-barcode/6291041500214").status_code == 422  # bad check digit
    assert seeded.patch("/api/v1/products/EGG-12", json={"barcode": "6291041500213"}).status_code == 409
    r = seeded.post("/api/v1/ada/chat", json={"text": "how many 6291041500213"}).json()
    assert "12" in r["reply"]


# ---------- import ----------
def _xlsx(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _post(client, name, data, **form):
    return client.post("/api/v1/products/import", files={"file": (name, data)},
                       data={k: str(v).lower() for k, v in form.items()})


def test_import_xlsx_arabic_headers_upsert(seeded):
    data = _xlsx([
        {"الرمز": "MILK-1L", "السعر": 1.8, "الكمية": 40},                     # update + stock-take
        {"الباركود": 4006381333931, "اسم المنتج": "قلم", "السعر": 0.5,       # new, sku from barcode
         "الفئة": "stationery", "الكمية": 100, "ملاحظات": "x"},
    ])
    preview = _post(seeded, "p.xlsx", data, dry_run=True).json()
    assert preview["created"] == 1 and preview["updated"] == 1 and not preview["applied"]
    assert preview["unknown_columns"] == ["ملاحظات"]
    assert seeded.get("/api/v1/products/by-barcode/4006381333931").status_code == 404  # dry run

    r = _post(seeded, "p.xlsx", data).json()
    assert r["applied"] and r["errors"] == []
    pen = seeded.get("/api/v1/products/by-barcode/4006381333931").json()
    assert pen["sku"] == "4006381333931" and pen["stock_qty"] == 100 and pen["name_en"] == "قلم"
    milk = seeded.get("/api/v1/products", params={"q": "MILK-1L"}).json()[0]
    assert milk["stock_qty"] == 40 and milk["price"] == "1.80"


def test_import_is_atomic_on_errors(seeded):
    data = _xlsx([{"SKU": "EGG-12", "Price": 9}, {"SKU": "X1", "Price": -1},
                  {"SKU": "X2", "Barcode": "4006381333932", "Name": "Bad", "Price": 1}])
    r = _post(seeded, "p.xlsx", data).json()
    assert not r["applied"] and {e["row"] for e in r["errors"]} == {3, 4}
    assert seeded.get("/api/v1/products", params={"q": "EGG-12"}).json()[0]["price"] == "3.00"

    r = _post(seeded, "p.xlsx", data, skip_invalid=True).json()
    assert r["applied"] and r["updated"] == 1 and r["skipped"] == 2
    assert seeded.get("/api/v1/products", params={"q": "EGG-12"}).json()[0]["price"] == "9.00"


def test_import_csv_cp1256_add_mode(seeded):
    csv = "الرمز;الكمية\nEGG-12;5\n".encode("cp1256")
    r = _post(seeded, "goods.csv", csv, stock_mode="add").json()
    assert r["applied"] and r["updated"] == 1
    assert seeded.get("/api/v1/products", params={"q": "EGG-12"}).json()[0]["stock_qty"] == 35


def test_import_rejects_bad_files(seeded):
    assert _post(seeded, "a.exe", b"MZ").status_code == 400
    assert _post(seeded, "a.xlsx", b"not a zip").status_code == 400
    assert _post(seeded, "a.csv", "name,price\nx,1\n".encode()).status_code == 400  # no key column
    dup = _xlsx([{"SKU": "A", "Name": "a", "Price": 1}, {"SKU": "A", "Name": "a", "Price": 1}])
    assert "Duplicate" in _post(seeded, "d.xlsx", dup).json()["errors"][0]["error"]


def test_template_roundtrip(seeded):
    r = seeded.get("/api/v1/products/import/template")
    assert r.status_code == 200
    out = _post(seeded, "t.xlsx", r.content).json()
    assert out["applied"] and out["updated"] == 1 and out["unknown_columns"] == []
    assert seeded.get("/api/v1/products/by-barcode/6291041500213").json()["sku"] == "MILK-1L"
