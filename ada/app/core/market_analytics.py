"""MarketAnalytics: Pandas-based trend, condition, reorder and diversification analysis.

All methods are read-only and work on a single snapshot (products + sales in window),
so results are internally consistent.
"""
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Product, ProductCondition, Sale, SaleItem, utcnow


@dataclass
class Snapshot:
    products: pd.DataFrame
    sales: pd.DataFrame       # one row per sale line in the analysis window
    window_days: int


class MarketAnalytics:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.s = settings

    # ---------- data loading ----------
    def snapshot(self, window_days: int | None = None) -> Snapshot:
        days = window_days or self.s.analytics_window_days
        since = utcnow() - timedelta(days=max(days, self.s.obsolete_after_days))
        prod_rows = self.db.execute(select(
            Product.id, Product.sku, Product.name_en, Product.name_ar, Product.category,
            Product.price, Product.cost, Product.stock_qty, Product.reorder_level,
            Product.lead_time_days, Product.condition, Product.expiry_date,
            Product.is_active, Product.created_at)).all()
        sale_rows = self.db.execute(
            select(SaleItem.product_id, SaleItem.quantity, SaleItem.unit_price, Sale.created_at)
            .join(Sale, Sale.id == SaleItem.sale_id).where(Sale.created_at >= since)).all()

        products = pd.DataFrame(prod_rows, columns=[
            "product_id", "sku", "name_en", "name_ar", "category", "price", "cost", "stock_qty",
            "reorder_level", "lead_time_days", "condition", "expiry_date", "is_active",
            "created_at"])
        sales = pd.DataFrame(sale_rows, columns=["product_id", "quantity", "unit_price", "sold_at"])
        for col in ("price", "cost"):
            products[col] = pd.to_numeric(products[col], errors="coerce").astype(float)
        if not sales.empty:
            sales["unit_price"] = sales["unit_price"].astype(float)
            sales["revenue"] = sales["quantity"] * sales["unit_price"]
            sales["sold_at"] = pd.to_datetime(sales["sold_at"], utc=True)
        else:
            sales = sales.assign(revenue=pd.Series(dtype=float))
        products["created_at"] = pd.to_datetime(products["created_at"], utc=True)
        return Snapshot(products, sales, days)

    # ---------- velocity ----------
    def _velocity(self, snap: Snapshot) -> pd.DataFrame:
        """Units/day in window + last sale timestamp, merged onto products."""
        cutoff = pd.Timestamp(utcnow() - timedelta(days=snap.window_days))
        win = snap.sales[snap.sales["sold_at"] >= cutoff] if not snap.sales.empty else snap.sales
        agg = (win.groupby("product_id").agg(units=("quantity", "sum"), revenue=("revenue", "sum"))
               if not win.empty else pd.DataFrame(columns=["units", "revenue"]))
        last = (snap.sales.groupby("product_id")["sold_at"].max().rename("last_sold_at")
                if not snap.sales.empty else pd.Series(name="last_sold_at", dtype="datetime64[ns, UTC]"))
        df = snap.products.merge(agg, left_on="product_id", right_index=True, how="left")
        df = df.merge(last, left_on="product_id", right_index=True, how="left")
        df[["units", "revenue"]] = df[["units", "revenue"]].fillna(0).astype(float)
        df["velocity"] = df["units"] / snap.window_days
        return df

    # ---------- public API ----------
    def best_sellers(self, top_n: int = 10, window_days: int | None = None) -> list[dict]:
        """Top products by units, with trend = second-half vs first-half of the window."""
        snap = self.snapshot(window_days)
        df = self._velocity(snap)
        df = df[df["units"] > 0]
        if df.empty:
            return []
        half = pd.Timestamp(utcnow() - timedelta(days=snap.window_days / 2))
        start = pd.Timestamp(utcnow() - timedelta(days=snap.window_days))
        s = snap.sales[snap.sales["sold_at"] >= start]
        recent = s[s["sold_at"] >= half].groupby("product_id")["quantity"].sum()
        older = s[s["sold_at"] < half].groupby("product_id")["quantity"].sum()
        df["trend_pct"] = df["product_id"].map(
            lambda pid: _pct_change(older.get(pid, 0), recent.get(pid, 0)))
        out = df.sort_values(["units", "revenue"], ascending=False).head(top_n)
        return _records(out, ["sku", "name_en", "name_ar", "category", "units", "revenue",
                              "velocity", "trend_pct"])

    def evaluate_conditions(self) -> list[dict]:
        """Score every active product 0–100 (higher = healthier) with human-readable flags."""
        df = self._velocity(self.snapshot())
        df = df[df["is_active"]]
        today = date.today()
        now = pd.Timestamp(utcnow())
        rows = []
        for r in df.itertuples():
            score, flags = 100, []
            if r.condition in (ProductCondition.DAMAGED, ProductCondition.EXPIRED):
                score -= 60; flags.append(f"condition:{r.condition}")
            if r.expiry_date is not None:
                days_left = (r.expiry_date - today).days
                if days_left < 0:
                    score -= 60; flags.append("expired")
                elif days_left <= 14:
                    score -= 25; flags.append(f"expires_in_{days_left}d")
            idle_days = ((now - r.last_sold_at).days if pd.notna(r.last_sold_at)
                         else (now - r.created_at).days)
            if idle_days >= self.s.obsolete_after_days:
                score -= 40; flags.append(f"no_sales_{idle_days}d")
            if r.velocity > 0 and r.stock_qty / r.velocity > 120:
                score -= 15; flags.append("overstocked")
            if pd.notna(r.cost) and r.cost and r.price <= r.cost:
                score -= 10; flags.append("negative_margin")
            rows.append({"sku": r.sku, "name_en": r.name_en, "score": max(score, 0),
                         "flags": flags, "idle_days": int(idle_days)})
        return sorted(rows, key=lambda x: x["score"])

    def obsolete_items(self) -> list[dict]:
        """Items to clear/discontinue: expired, damaged, discontinued or idle beyond threshold."""
        return [r for r in self.evaluate_conditions()
                if any(f.startswith(("expired", "condition:", "no_sales_")) for f in r["flags"])]

    def reorder_list(self) -> list[dict]:
        """Order-up-to policy: target = velocity × (lead_time + safety_days); exclude obsolete."""
        df = self._velocity(self.snapshot())
        obsolete = {r["sku"] for r in self.obsolete_items()}
        df = df[df["is_active"] & ~df["sku"].isin(obsolete)
                & ~df["condition"].isin([ProductCondition.DISCONTINUED])]
        cover = df["lead_time_days"] + self.s.safety_stock_days
        df["target_stock"] = np.maximum(np.ceil(df["velocity"] * cover), df["reorder_level"] + 1)
        df["order_qty"] = (df["target_stock"] - df["stock_qty"]).clip(lower=0).astype(int)
        df["days_of_cover"] = np.where(df["velocity"] > 0, df["stock_qty"] / df["velocity"], np.inf)
        need = df[(df["stock_qty"] <= df["reorder_level"]) |
                  (df["days_of_cover"] <= df["lead_time_days"])]
        need = need[need["order_qty"] > 0].sort_values("days_of_cover")
        need["est_cost"] = need["order_qty"] * need["cost"].fillna(need["price"])
        return _records(need, ["sku", "name_en", "stock_qty", "velocity", "days_of_cover",
                               "order_qty", "est_cost"])

    def diversification(self) -> dict:
        """Category concentration (HHI on revenue) + gaps: categories with demand but thin range."""
        df = self._velocity(self.snapshot())
        df = df[df["is_active"]]
        by_cat = df.groupby("category").agg(skus=("sku", "count"), revenue=("revenue", "sum"),
                                            units=("units", "sum"))
        total = by_cat["revenue"].sum()
        if total <= 0:
            return {"hhi": None, "concentration": "no_sales_data", "categories": [],
                    "recommendations": ["Record sales to enable diversification analysis."]}
        by_cat["share"] = by_cat["revenue"] / total
        hhi = float((by_cat["share"] ** 2).sum())                 # 1/N (even) .. 1.0 (mono)
        level = "high" if hhi > 0.25 else "moderate" if hhi > 0.15 else "healthy"
        by_cat["rev_per_sku"] = by_cat["revenue"] / by_cat["skus"]
        median_rps = by_cat["rev_per_sku"].median()
        recs = []
        for cat, r in by_cat.iterrows():
            if r["rev_per_sku"] > 1.5 * median_rps and r["skus"] <= 3:
                recs.append(f"Expand range in '{cat}': strong demand on only {int(r['skus'])} SKU(s).")
            if r["share"] < 0.03 and r["skus"] >= 5:
                recs.append(f"Rationalise '{cat}': {int(r['skus'])} SKUs earn <3% of revenue.")
        if level == "high":
            top = by_cat["share"].idxmax()
            recs.append(f"Revenue is concentrated in '{top}' ({by_cat.loc[top, 'share']:.0%}); "
                        "add adjacent categories to reduce risk.")
        cats = by_cat.reset_index().sort_values("share", ascending=False)
        return {"hhi": round(hhi, 4), "concentration": level,
                "categories": _records(cats, ["category", "skus", "units", "revenue", "share"]),
                "recommendations": recs}


def _pct_change(old: float, new: float) -> float | None:
    if old == 0:
        return None if new == 0 else 100.0
    return round((new - old) / old * 100, 1)


def _records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    """JSON-safe records (inf/NaN -> None, numpy -> python, floats rounded)."""
    out = df[cols].replace([np.inf, -np.inf], np.nan).astype(object)
    out = out.where(pd.notna(out), None)
    recs = out.to_dict("records")
    for r in recs:
        for k, v in r.items():
            if isinstance(v, (np.integer,)):
                r[k] = int(v)
            elif isinstance(v, (float, np.floating)):
                r[k] = round(float(v), 3)
    return recs
