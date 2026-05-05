"""
services/shopify_service.py
سحب المنتجات من Shopify وإعدادها للنشر التسويقي.
"""
from __future__ import annotations
import logging
import re
import requests
from dataclasses import dataclass, field
from core.config     import AppConfig
from core.exceptions import ShopifyError

logger = logging.getLogger(__name__)


@dataclass
class ShopifyProduct:
    id:           int
    title:        str
    description:  str
    price:        str
    currency:     str
    image_url:    str
    product_url:  str
    tags:         list = field(default_factory=list)
    vendor:       str  = ""
    product_type: str  = ""

    @property
    def short_desc(self) -> str:
        clean = re.sub(r"<[^>]+>", "", self.description)
        return clean.strip()[:200]

    @property
    def price_display(self) -> str:
        return f"{self.price} {self.currency}"


class ShopifyService:
    def __init__(self, config: AppConfig) -> None:
        self._cfg     = config
        self._session = requests.Session()
        self._session.headers.update({
            "X-Shopify-Access-Token": config.shopify_token,
            "Content-Type": "application/json",
        })

    def fetch_products(self, limit: int = 20, status: str = "active") -> list[ShopifyProduct]:
        url = (
            f"https://{self._cfg.clean_shop_url}/admin/api/"
            f"{self._cfg.shopify_api_version}/products.json"
            f"?limit={min(limit, 250)}&status={status}"
        )
        try:
            res = self._session.get(url, timeout=20)
        except requests.exceptions.Timeout:
            raise ShopifyError("انتهت مهلة الاتصال بـ Shopify.")
        except requests.exceptions.ConnectionError:
            raise ShopifyError("لا يوجد اتصال بالإنترنت.")
        if res.status_code == 401:
            raise ShopifyError("توكن Shopify غير صالح.", 401)
        if res.status_code != 200:
            raise ShopifyError(f"خطأ Shopify {res.status_code}", res.status_code)

        products = []
        domain   = self._cfg.clean_shop_url
        for p in res.json().get("products", []):
            variants  = p.get("variants", [{}])
            price     = variants[0].get("price", "0.00") if variants else "0.00"
            images    = p.get("images", [])
            image_url = images[0].get("src", "") if images else ""
            handle    = p.get("handle", "")
            products.append(ShopifyProduct(
                id           = p.get("id", 0),
                title        = p.get("title", "").strip(),
                description  = p.get("body_html", ""),
                price        = price,
                currency     = "USD",
                image_url    = image_url,
                product_url  = f"https://{domain}/products/{handle}",
                tags         = [t.strip() for t in p.get("tags", "").split(",") if t.strip()],
                vendor       = p.get("vendor", ""),
                product_type = p.get("product_type", ""),
            ))
        logger.info("Fetched %d products from Shopify", len(products))
        return products

    def test_connection(self) -> dict:
        url = (
            f"https://{self._cfg.clean_shop_url}/admin/api/"
            f"{self._cfg.shopify_api_version}/shop.json"
        )
        try:
            res = self._session.get(url, timeout=12)
        except requests.exceptions.ConnectionError:
            raise ShopifyError("لا يوجد اتصال بالإنترنت.")
        if res.status_code == 200:
            s = res.json().get("shop", {})
            return {"name": s.get("name"), "currency": s.get("currency"), "domain": s.get("domain")}
        raise ShopifyError(f"خطأ {res.status_code}", res.status_code)
