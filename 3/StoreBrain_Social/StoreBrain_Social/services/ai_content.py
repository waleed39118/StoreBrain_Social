"""
services/ai_content.py
محرك توليد المحتوى الإعلاني بالذكاء الاصطناعي.
يُنتج محتوى مخصصاً لكل منصة ودولة بشكل منفصل.
"""
from __future__ import annotations
import json
import logging
import time
from dataclasses import dataclass, field
import requests
from core.config     import AppConfig
from core.exceptions import AIError
from services.shopify_service import ShopifyProduct

logger = logging.getLogger(__name__)
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# قواعد كل منصة
PLATFORM_RULES: dict[str, dict] = {
    "Facebook":  {"max_chars": 500,  "style": "ودي مُقنع يشجع التفاعل",                   "hashtags": 5,  "emoji": True},
    "Instagram": {"max_chars": 300,  "style": "بصري جذاب يركز على الإلهام",               "hashtags": 15, "emoji": True},
    "Pinterest": {"max_chars": 200,  "style": "وصفي يركز على الفائدة",                     "hashtags": 5,  "emoji": False},
    "LinkedIn":  {"max_chars": 400,  "style": "احترافي يُبرز القيمة التجارية",             "hashtags": 3,  "emoji": False},
    "Telegram":  {"max_chars": 600,  "style": "مباشر وواضح مع تفاصيل كافية",              "hashtags": 3,  "emoji": True},
    "Twitter":   {"max_chars": 260,  "style": "مختصر مباشر يضغط على الفضول",              "hashtags": 3,  "emoji": True},
    "Reddit":    {"max_chars": 800,  "style": "طبيعي غير إعلاني يُثير نقاشاً ويُقدم قيمة","hashtags": 0,  "emoji": False},
    "YouTube":   {"max_chars": 500,  "style": "وصفي SEO-محسَّن لمحرك بحث YouTube",        "hashtags": 8,  "emoji": False},
}

# أكثر المنصات استخداماً لكل دولة
COUNTRY_TOP_PLATFORMS: dict[str, list[str]] = {
    "السعودية":  ["Instagram", "Telegram", "Twitter", "YouTube", "Facebook"],
    "الإمارات":  ["Instagram", "Facebook", "Twitter", "LinkedIn"],
    "مصر":       ["Facebook", "YouTube", "Instagram", "Telegram"],
    "المغرب":    ["Facebook", "Instagram", "YouTube"],
    "الكويت":    ["Instagram", "Telegram", "Twitter"],
    "قطر":       ["Instagram", "Twitter", "LinkedIn"],
    "أمريكا":    ["Facebook", "Instagram", "Pinterest", "Twitter", "Reddit"],
    "أوروبا":    ["Facebook", "Instagram", "Pinterest", "LinkedIn"],
    "آسيا":      ["Facebook", "Instagram", "YouTube"],
    "عالمي":     ["Facebook", "Instagram", "Telegram", "Pinterest", "LinkedIn", "Twitter"],
}

# أفضل أوقات النشر (ساعات UTC) لكل دولة
COUNTRY_BEST_HOURS: dict[str, list[int]] = {
    "السعودية": [6, 10, 17, 18],
    "الإمارات": [6, 9,  17, 18],
    "مصر":      [7, 11, 18, 19],
    "المغرب":   [7, 11, 18, 19],
    "الكويت":   [6, 10, 17, 18],
    "أمريكا":   [14, 17, 21, 22],
    "أوروبا":   [8,  12, 16, 17],
    "عالمي":    [8,  12, 16, 20],
}


@dataclass
class PlatformContent:
    platform: str
    title:    str
    caption:  str
    hashtags: list
    cta_url:  str
    country:  str
    language: str


@dataclass
class CampaignContent:
    product:  ShopifyProduct
    country:  str
    contents: list = field(default_factory=list)

    def for_platform(self, platform: str):
        for c in self.contents:
            if c.platform == platform:
                return c
        return None


class AIContentEngine:
    def __init__(self, config: AppConfig) -> None:
        self._cfg     = config
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {config.groq_api_key}",
            "Content-Type":  "application/json",
        })

    def generate_campaign(
        self,
        product:   ShopifyProduct,
        platforms: list,
        country:   str = "عالمي",
        language:  str = "العربية",
    ) -> CampaignContent:
        contents   = []
        batch_size = 3
        for i in range(0, len(platforms), batch_size):
            batch  = platforms[i:i + batch_size]
            prompt = self._build_prompt(product, batch, country, language)
            try:
                raw    = self._call_groq(prompt)
                parsed = self._parse(raw, batch)
                for platform, data in parsed.items():
                    contents.append(PlatformContent(
                        platform = platform,
                        title    = data.get("title", product.title),
                        caption  = data.get("caption", ""),
                        hashtags = data.get("hashtags", []),
                        cta_url  = product.product_url,
                        country  = country,
                        language = language,
                    ))
            except AIError as exc:
                logger.error("AI batch failed %s: %s", batch, exc)
                for platform in batch:
                    contents.append(self._fallback(product, platform, country, language))
        return CampaignContent(product=product, country=country, contents=contents)

    def _build_prompt(self, product, platforms, country, language) -> str:
        lines = []
        for p in platforms:
            r = PLATFORM_RULES.get(p, {})
            lines.append(
                f'"{p}": أسلوب [{r.get("style","")}]، '
                f'حد {r.get("max_chars", 300)} حرف، '
                f'{r.get("hashtags", 5)} هاشتاق، '
                f'{"استخدم إيموجي" if r.get("emoji") else "بدون إيموجي"}'
            )
        return (
            f"أنت خبير تسويق رقمي متخصص في التجارة الإلكترونية.\n\n"
            f"المنتج: {product.title}\n"
            f"الوصف: {product.short_desc[:250]}\n"
            f"السعر: {product.price_display}\n"
            f"الفئة: {product.product_type or 'عام'}\n"
            f"الدولة المستهدفة: {country}\n"
            f"اللغة: {language}\n\n"
            f"المطلوب: محتوى إعلاني مختلف لكل منصة:\n"
            + "\n".join(lines)
            + "\n\nالرد بصيغة JSON فقط:\n"
            '{\n'
            '  "Facebook": {"title": "...", "caption": "...", "hashtags": ["..."]},\n'
            '  "Instagram": {"title": "...", "caption": "...", "hashtags": ["..."]}\n'
            '}\n'
            "القواعد: كل منصة لها أسلوب مختلف تماماً — لا تنسخ نفس النص."
        )

    def _call_groq(self, prompt: str) -> str:
        for model in (self._cfg.groq_primary_model, self._cfg.groq_fallback_model):
            for attempt in range(3):
                try:
                    res = self._session.post(
                        _GROQ_URL,
                        json={
                            "model":           model,
                            "messages":        [{"role": "user", "content": prompt}],
                            "response_format": {"type": "json_object"},
                            "temperature":     0.75,
                            "max_tokens":      1500,
                        },
                        timeout=45,
                    )
                except requests.exceptions.Timeout:
                    raise AIError("انتهت مهلة الاتصال بـ Groq.")
                except requests.exceptions.ConnectionError:
                    raise AIError("لا يوجد اتصال بالإنترنت.")
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
                if res.status_code == 429:
                    time.sleep([5, 15, 30][min(attempt, 2)])
                    continue
                if res.status_code in (400, 404):
                    break  # جرب الموديل الثاني
                raise AIError(f"خطأ Groq {res.status_code}: {res.text[:150]}")
        raise AIError("كل موديلات Groq فشلت.")

    def _parse(self, raw: str, platforms: list) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise AIError(f"رد Groq ليس JSON صالحاً: {e}")
        result = {}
        for p in platforms:
            if p in data:
                result[p] = data[p]
            else:
                for k in data:
                    if k.lower() == p.lower():
                        result[p] = data[k]
                        break
        return result

    def _fallback(self, product, platform, country, language) -> PlatformContent:
        return PlatformContent(
            platform = platform,
            title    = product.title,
            caption  = f"🛍️ {product.title}\n💰 السعر: {product.price_display}\n👇 اطلب الآن",
            hashtags = ["تسوق_الآن", "عروض", "متجرنا"],
            cta_url  = product.product_url,
            country  = country,
            language = language,
        )
