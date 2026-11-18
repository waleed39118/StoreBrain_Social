"""Sample catalog so a merchant can try Ada in one tap.

Barcodes use the GS1 "restricted circulation" prefix 200 (in-store numbers), so they can
never collide with real manufacturer barcodes once the merchant adds real products.
"""
from decimal import Decimal

from app.models import MovementReason, Product, StockMovement

_ITEMS = [  # sku, en, ar, category, price, cost, stock, reorder
    ("MILK-1L", "Fresh Milk 1L", "حليب طازج 1 لتر", "dairy", "6.50", "4.80", 40, 12),
    ("LABAN-1L", "Laban 1L", "لبن 1 لتر", "dairy", "5.75", "4.10", 30, 10),
    ("EGGS-30", "Eggs 30 pcs", "بيض 30 حبة", "dairy", "22.00", "17.50", 18, 6),
    ("CHEESE-500", "White Cheese 500g", "جبنة بيضاء 500 جم", "dairy", "14.95", "10.90", 15, 5),
    ("BREAD-ARB", "Arabic Bread", "خبز عربي", "bakery", "2.50", "1.60", 60, 20),
    ("CROIS-6", "Croissant 6 pcs", "كرواسون 6 حبات", "bakery", "9.00", "6.20", 4, 6),
    ("RICE-5KG", "Basmati Rice 5kg", "أرز بسمتي 5 كجم", "pantry", "38.00", "29.00", 25, 8),
    ("SUGAR-2KG", "Sugar 2kg", "سكر 2 كجم", "pantry", "11.50", "8.70", 20, 8),
    ("OIL-1.5L", "Sunflower Oil 1.5L", "زيت دوار الشمس 1.5 لتر", "pantry", "16.25", "12.40", 14, 6),
    ("TEA-100", "Black Tea 100 bags", "شاي أسود 100 كيس", "pantry", "17.95", "12.80", 22, 6),
    ("DATES-1KG", "Sukkari Dates 1kg", "تمر سكري 1 كجم", "pantry", "35.00", "24.00", 12, 4),
    ("WATER-12", "Water 12 x 330ml", "مياه 12 × 330 مل", "drinks", "9.50", "6.60", 50, 15),
    ("JUICE-1L", "Orange Juice 1L", "عصير برتقال 1 لتر", "drinks", "7.25", "5.10", 3, 8),
    ("COLA-6", "Cola 6 cans", "مشروب غازي 6 علب", "drinks", "15.00", "11.00", 28, 8),
    ("SOAP-4", "Hand Soap 4 pcs", "صابون يدين 4 حبات", "care", "12.00", "8.00", 16, 5),
    ("TISSUE-5", "Tissues 5 boxes", "مناديل 5 علب", "care", "19.50", "14.00", 10, 4),
]


def _ean13(n: int) -> str:
    body = f"200{n:09d}"
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


def load_demo(db) -> int:
    for i, (sku, en, ar, cat, price, cost, stock, reorder) in enumerate(_ITEMS, start=1):
        p = Product(sku=sku, barcode=_ean13(i), name_en=en, name_ar=ar, category=cat,
                    price=Decimal(price), cost=Decimal(cost), stock_qty=stock, reorder_level=reorder)
        db.add(p)
        db.flush()
        db.add(StockMovement(product_id=p.id, delta=stock, reason=MovementReason.ADJUSTMENT, ref="demo"))
    return len(_ITEMS)
