"""Ada (أدا) conversational layer: language detection, intent parsing and persona replies.

Deterministic rule-based NLU keeps the stack dependency-free and auditable — Ada never
hallucinates a stock figure: every number she speaks comes from the database.
An LLM can later be slotted in behind ``parse_intent`` without touching the managers.
"""
import re
from dataclasses import dataclass, field

from app.core.inventory_manager import InventoryError, InventoryManager, LineRequest
from app.core.market_analytics import MarketAnalytics

_AR = re.compile(r"[؀-ۿ]")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_AR_NUMBERS = {"واحد": 1, "واحدة": 1, "اثنين": 2, "اثنان": 2, "ثلاثة": 3, "ثلاث": 3, "اربعة": 4,
               "أربعة": 4, "خمسة": 5, "ستة": 6, "سبعة": 7, "ثمانية": 8, "تسعة": 9, "عشرة": 10}
_EN_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
               "eight": 8, "nine": 9, "ten": 10, "a": 1, "an": 1}

# (intent, regex) — first match wins; order matters.
_RULES: list[tuple[str, re.Pattern]] = [
    ("reorder", re.compile(r"reorder|what should i (order|buy)|اطلب|إعادة الطلب|قائمة الطلب", re.I)),
    ("best_sellers", re.compile(r"best.?sell|top sell|trending|الأكثر مبيع|الاكثر مبيع|الرائج", re.I)),
    ("low_stock", re.compile(r"low stock|running (low|out)|نفد|ناقص|قارب على النفاد|المخزون المنخفض", re.I)),
    ("obsolete", re.compile(r"obsolete|dead stock|expired|راكد|منتهي", re.I)),
    ("diversify", re.compile(r"diversif|categor|تنويع|الفئات", re.I)),
    ("restock", re.compile(r"^(restock|add|received)\b|^(أضف|اضف|استلمت|وصل)", re.I)),
    ("sell", re.compile(r"^(sell|sold|checkout|ring up)\b|^(بيع|بع|بعت|اشترى)", re.I)),
    ("stock", re.compile(r"how many|stock of|in stock|do you have|كم (باقي|متبقي|عندك|يوجد)|هل (يوجد|عندك|عندكم)", re.I)),
    ("greet", re.compile(r"^(hi|hello|hey|good (morning|evening))\b|مرحبا|السلام|أهلا|اهلا|صباح", re.I)),
]

_T = {  # persona strings: warm, concise, like a real shop assistant
    "greet": {"en": "Hi! I'm Ada, your store assistant. Ask me about stock, sales or what to reorder.",
              "ar": "أهلاً! أنا أدا، مساعدتك في المتجر. اسألني عن المخزون أو المبيعات أو ما يجب طلبه."},
    "unknown": {"en": "Sorry, I didn't catch that. Try: 'sell 2 milk', 'how many eggs', or 'reorder list'.",
                "ar": "عذراً، لم أفهم. جرّب: «بيع 2 حليب» أو «كم باقي من البيض» أو «قائمة الطلب»."},
    "not_found": {"en": "I couldn't find '{q}' on our shelves.", "ar": "لم أجد «{q}» في المتجر."},
    "ambiguous": {"en": "Did you mean: {opts}?", "ar": "هل تقصد: {opts}؟"},
    "stock": {"en": "We have {n} of {name} left.", "ar": "متبقي {n} من {name}."},
    "sold": {"en": "Done — sold {q} × {name}. Total {total}. {n} left.",
             "ar": "تم — بيع {q} × {name}. الإجمالي {total}. المتبقي {n}."},
    "restocked": {"en": "Added {q} × {name}. Now {n} in stock.", "ar": "أضفت {q} × {name}. المخزون الآن {n}."},
    "none_low": {"en": "Good news — nothing is running low.", "ar": "خبر جيد — لا يوجد منتج قارب على النفاد."},
    "low": {"en": "Running low: {items}.", "ar": "قارب على النفاد: {items}."},
    "best": {"en": "Best sellers lately: {items}.", "ar": "الأكثر مبيعاً مؤخراً: {items}."},
    "no_sales": {"en": "No sales recorded in this period yet.", "ar": "لا توجد مبيعات مسجلة في هذه الفترة."},
    "reorder": {"en": "I'd reorder: {items}.", "ar": "أقترح طلب: {items}."},
    "no_reorder": {"en": "Stock levels look fine; nothing to reorder.", "ar": "المخزون جيد؛ لا حاجة للطلب."},
    "obsolete": {"en": "Consider clearing: {items}.", "ar": "يُنصح بتصفية: {items}."},
    "no_obsolete": {"en": "No obsolete items found.", "ar": "لا توجد منتجات راكدة."},
    "diversify": {"en": "Category concentration is {level}. {recs}", "ar": "تركّز الفئات: {level}. {recs}"},
    "error": {"en": "I couldn't do that: {msg}", "ar": "تعذّر ذلك: {msg}"},
    "forbidden": {"en": "Sorry, only a manager or the owner can do that.",
                  "ar": "عذراً، هذا الإجراء متاح للمدير أو صاحب المحل فقط."},
}


@dataclass
class Intent:
    name: str
    product_query: str | None = None
    quantity: int = 1


@dataclass
class Reply:
    text: str
    language: str
    intent: str
    data: dict | list | None = field(default=None)


def detect_language(text: str, hint: str | None = None) -> str:
    if hint in ("ar", "en"):
        return hint
    return "ar" if _AR.search(text) else "en"


def parse_intent(text: str) -> Intent:
    t = text.translate(_AR_DIGITS).strip().rstrip("?.!؟")
    name = next((n for n, rx in _RULES if rx.search(t)), "unknown")
    if name not in ("sell", "restock", "stock"):
        return Intent(name)
    qty, words = 1, t.split()
    for i, w in enumerate(words):
        lw = w.lower()
        # <=5 digits = quantity; longer digit runs are barcodes/SKUs, not quantities.
        if (lw.isdigit() and len(lw) <= 5) or lw in _EN_NUMBERS or w in _AR_NUMBERS:
            qty = int(lw) if lw.isdigit() else _EN_NUMBERS.get(lw) or _AR_NUMBERS[w]
            words[i] = ""
            break
    stop = {"sell", "sold", "checkout", "ring", "up", "restock", "add", "received", "how", "many",
            "stock", "of", "in", "do", "you", "have", "we", "any", "the", "units", "x", "left",
            "بيع", "بع", "بعت", "اشترى", "أضف", "اضف", "استلمت", "وصل", "كم", "باقي", "متبقي",
            "عندك", "يوجد", "هل", "عندكم", "من", "حبة", "حبات", "قطعة"}
    query = " ".join(w for w in words if w and w.lower() not in stop).strip()
    return Intent(name, query or None, max(qty, 1))


# Intents a cashier may trigger by chat/voice; everything else needs manager/owner.
CASHIER_INTENTS = frozenset({"greet", "unknown", "sell", "stock", "low_stock", "best_sellers"})


class AdaAssistant:
    def __init__(self, inventory: InventoryManager, analytics: MarketAnalytics) -> None:
        self.inv = inventory
        self.an = analytics

    def handle(self, text: str, language_hint: str | None = None, channel: str = "text",
               allowed: frozenset[str] | None = None) -> Reply:
        """``allowed`` = intents permitted for the caller's role (None = all)."""
        lang = detect_language(text, language_hint)
        intent = parse_intent(text)
        say = lambda key, **kw: _T[key][lang].format(**kw)  # noqa: E731
        sep = "، " if lang == "ar" else ", "
        if allowed is not None and intent.name not in allowed:
            return Reply(say("forbidden"), lang, intent.name)
        try:
            match intent.name:
                case "greet":
                    return Reply(say("greet"), lang, intent.name)
                case "sell" | "restock" | "stock":
                    return self._product_action(intent, lang, say, channel)
                case "low_stock":
                    items = self.inv.low_stock()
                    if not items:
                        return Reply(say("none_low"), lang, intent.name, [])
                    names = sep.join(f"{self._name(p, lang)} ({p.stock_qty})" for p in items[:8])
                    return Reply(say("low", items=names), lang, intent.name,
                                 [{"sku": p.sku, "stock_qty": p.stock_qty} for p in items])
                case "best_sellers":
                    rows = self.an.best_sellers(top_n=5)
                    if not rows:
                        return Reply(say("no_sales"), lang, intent.name, [])
                    names = sep.join(f"{self._row_name(r, lang)} ({int(r['units'])})" for r in rows)
                    return Reply(say("best", items=names), lang, intent.name, rows)
                case "reorder":
                    rows = self.an.reorder_list()
                    if not rows:
                        return Reply(say("no_reorder"), lang, intent.name, [])
                    names = sep.join(f"{r['name_en']} × {r['order_qty']}" for r in rows[:8])
                    return Reply(say("reorder", items=names), lang, intent.name, rows)
                case "obsolete":
                    rows = self.an.obsolete_items()
                    if not rows:
                        return Reply(say("no_obsolete"), lang, intent.name, [])
                    return Reply(say("obsolete", items=sep.join(r["name_en"] for r in rows[:8])),
                                 lang, intent.name, rows)
                case "diversify":
                    d = self.an.diversification()
                    return Reply(say("diversify", level=d["concentration"],
                                     recs=" ".join(d["recommendations"][:3])), lang, intent.name, d)
                case _:
                    return Reply(say("unknown"), lang, intent.name)
        except InventoryError as exc:
            return Reply(say("error", msg=str(exc)), lang, intent.name)

    def _product_action(self, intent: Intent, lang: str, say, channel: str) -> Reply:
        if not intent.product_query:
            return Reply(say("unknown"), lang, intent.name)
        matches = self.inv.find(intent.product_query)
        if not matches:
            return Reply(say("not_found", q=intent.product_query), lang, intent.name)
        exact = [p for p in matches if intent.product_query.lower() in
                 (p.sku.lower(), p.name_en.lower(), (p.name_ar or ""))]
        if len(matches) > 1 and len(exact) != 1:
            opts = " / ".join(self._name(p, lang) for p in matches[:4])
            return Reply(say("ambiguous", opts=opts), lang, intent.name,
                         [{"sku": p.sku, "name_en": p.name_en} for p in matches])
        p = exact[0] if exact else matches[0]
        if intent.name == "stock":
            return Reply(say("stock", n=p.stock_qty, name=self._name(p, lang)), lang, intent.name,
                         {"sku": p.sku, "stock_qty": p.stock_qty})
        if intent.name == "restock":
            p = self.inv.restock(p.sku, intent.quantity, ref=channel)
            return Reply(say("restocked", q=intent.quantity, name=self._name(p, lang), n=p.stock_qty),
                         lang, intent.name, {"sku": p.sku, "stock_qty": p.stock_qty})
        sale = self.inv.record_sale([LineRequest(p.sku, intent.quantity)], channel=channel)
        return Reply(say("sold", q=intent.quantity, name=self._name(p, lang),
                         total=f"{sale.total:.2f}", n=p.stock_qty),
                     lang, intent.name, {"sale_id": sale.id, "total": str(sale.total)})

    @staticmethod
    def _name(p, lang: str) -> str:
        return p.name_ar if lang == "ar" and p.name_ar else p.name_en

    @staticmethod
    def _row_name(r: dict, lang: str) -> str:
        return r["name_ar"] if lang == "ar" and r.get("name_ar") else r["name_en"]
