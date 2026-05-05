"""
services/campaign_manager.py
المنسّق الرئيسي للحملات الإعلانية — يُدير الدورة الكاملة.
"""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import Callable
from core.config     import AppConfig
from core.exceptions import StoreBrainError
from core.logger     import get_logger
from services.shopify_service  import ShopifyService, ShopifyProduct
from services.ai_content       import AIContentEngine, CampaignContent, COUNTRY_TOP_PLATFORMS
from services.image_service    import ImageService
from services.publishers.base  import BasePublisher, PublishResult
from services.publishers.facebook  import FacebookPublisher
from services.publishers.instagram import InstagramPublisher
from services.publishers.telegram  import TelegramPublisher
from services.publishers.pinterest import PinterestPublisher
from services.publishers.linkedin  import LinkedInPublisher
from services.publishers.twitter   import TwitterPublisher
from services.publishers.reddit    import RedditPublisher
from services.publishers.youtube   import YouTubePublisher

logger = get_logger(__name__)


@dataclass
class CampaignResult:
    product_title: str
    country:       str
    results:       list = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.success)

    def summary(self) -> str:
        return (f"📦 {self.product_title[:40]}\n"
                f"✅ نجح: {self.success_count} | ❌ فشل: {self.fail_count}")


@dataclass
class BatchReport:
    total_products:  int  = 0
    total_published: int  = 0
    total_failed:    int  = 0
    campaigns:       list = field(default_factory=list)

    def add(self, c: CampaignResult) -> None:
        self.campaigns.append(c)
        self.total_products  += 1
        self.total_published += c.success_count
        self.total_failed    += c.fail_count

    def summary(self) -> str:
        return (f"🏁 انتهت الجلسة\n"
                f"📦 منتجات: {self.total_products}\n"
                f"✅ منشورات ناجحة: {self.total_published}\n"
                f"❌ فاشلة: {self.total_failed}")


class CampaignManager:
    def __init__(self, config: AppConfig, log_callback: Callable | None = None) -> None:
        self._cfg     = config
        self._log     = log_callback or print
        self._shopify = ShopifyService(config)
        self._ai      = AIContentEngine(config)
        self._images  = ImageService()
        self._pubs    = self._build_publishers()

    def _build_publishers(self) -> dict:
        cfg = self._cfg
        pubs: dict[str, BasePublisher] = {}
        if cfg.has_facebook:  pubs["Facebook"]  = FacebookPublisher(cfg)
        if cfg.has_instagram: pubs["Instagram"] = InstagramPublisher(cfg)
        if cfg.has_telegram:  pubs["Telegram"]  = TelegramPublisher(cfg)
        if cfg.has_pinterest: pubs["Pinterest"] = PinterestPublisher(cfg)
        if cfg.has_linkedin:  pubs["LinkedIn"]  = LinkedInPublisher(cfg)
        if cfg.has_twitter:   pubs["Twitter"]   = TwitterPublisher(cfg)
        if cfg.has_reddit:    pubs["Reddit"]    = RedditPublisher(cfg)
        if cfg.has_youtube:   pubs["YouTube"]   = YouTubePublisher(cfg)
        return pubs

    @property
    def active_platforms(self) -> list:
        return list(self._pubs.keys())

    def reload_publishers(self, config: AppConfig) -> None:
        """يُعيد بناء الـ publishers بعد تحديث الإعدادات."""
        self._cfg  = config
        self._ai   = AIContentEngine(config)
        self._pubs = self._build_publishers()

    def test_all_connections(self) -> dict:
        results = {}
        try:
            info = self._shopify.test_connection()
            results["Shopify"] = (True, f"✅ Shopify — {info.get('name','')}")
        except Exception as e:
            results["Shopify"] = (False, f"❌ Shopify — {e}")
        for name, pub in self._pubs.items():
            try:
                results[name] = pub.test_connection()
            except Exception as e:
                results[name] = (False, str(e))
        return results

    def run_campaign(
        self,
        product:   ShopifyProduct,
        country:   str  = "عالمي",
        language:  str  = "العربية",
        platforms: list | None = None,
        delay_sec: int  = 3,
    ) -> CampaignResult:
        result           = CampaignResult(product_title=product.title, country=country)
        target_platforms = platforms or self._select_platforms(country)
        active           = [p for p in target_platforms if p in self._pubs]
        skipped          = [p for p in target_platforms if p not in self._pubs]

        if skipped:
            self._log(f"⚠️  منصات بدون مفاتيح: {', '.join(skipped)}")
        if not active:
            self._log("❌ لا توجد منصات مُفعَّلة.")
            return result

        self._log(f"🎯 المنصات: {', '.join(active)}")

        # توليد المحتوى
        self._log("🧠 توليد المحتوى بالذكاء الاصطناعي...")
        try:
            campaign: CampaignContent = self._ai.generate_campaign(
                product=product, platforms=active,
                country=country, language=language,
            )
        except Exception as e:
            self._log(f"❌ فشل توليد المحتوى: {e}")
            return result

        # توليد الصورة
        self._log("🎨 تحضير الصورة الإعلانية...")
        image_data = self._images.get_image_bytes(
            product_title=product.title,
            platform=active[0],
            source_url=product.image_url,
        )
        if image_data:
            self._log(f"💾 الصورة جاهزة ({len(image_data)//1024} KB)")
        else:
            self._log("⚠️  تعذر تحميل الصورة — سيُنشر بدونها.")

        # النشر
        for i, platform in enumerate(active):
            content = campaign.for_platform(platform)
            if not content:
                self._log(f"⚠️  لا يوجد محتوى لـ {platform}.")
                continue
            self._log(f"📤 النشر على {platform}...")
            try:
                pub_result = self._pubs[platform].publish(content, image_data)
                result.results.append(pub_result)
                self._log(str(pub_result))
            except StoreBrainError as e:
                result.results.append(PublishResult(platform=platform, success=False, error=str(e)))
                self._log(f"❌ {platform}: {e}")
            except Exception as e:
                logger.exception("Unexpected error on %s", platform)
                result.results.append(PublishResult(platform=platform, success=False, error=str(e)))
                self._log(f"❌ {platform}: {e}")

            if delay_sec > 0 and i < len(active) - 1:
                time.sleep(delay_sec)

        return result

    def run_batch(
        self,
        product_limit:  int  = 5,
        country:        str  = "عالمي",
        language:       str  = "العربية",
        platforms:      list | None = None,
        delay_between:  int  = 10,
        progress_cb:    Callable | None = None,
    ) -> BatchReport:
        report = BatchReport()
        self._log("🛍️  سحب المنتجات من Shopify...")
        try:
            products = self._shopify.fetch_products(limit=product_limit)
        except Exception as e:
            self._log(f"❌ فشل سحب المنتجات: {e}")
            return report

        if not products:
            self._log("⚠️  لا توجد منتجات.")
            return report

        self._log(f"✅ تم سحب {len(products)} منتج.")

        for i, product in enumerate(products, 1):
            self._log(f"\n── المنتج {i}/{len(products)}: {product.title[:50]} ──")
            if progress_cb:
                progress_cb(i, len(products))
            try:
                cr = self.run_campaign(
                    product=product, country=country,
                    language=language, platforms=platforms, delay_sec=3,
                )
                report.add(cr)
                self._log(cr.summary())
            except Exception as e:
                logger.exception("Campaign failed for %s", product.id)
                self._log(f"❌ فشلت حملة '{product.title[:40]}': {e}")

            if i < len(products) and delay_between > 0:
                self._log(f"⏳ انتظار {delay_between} ثانية...")
                time.sleep(delay_between)

        self._log(f"\n{report.summary()}")
        return report

    def _select_platforms(self, country: str) -> list:
        preferred = COUNTRY_TOP_PLATFORMS.get(country, COUNTRY_TOP_PLATFORMS["عالمي"])
        extra     = [p for p in self.active_platforms if p not in preferred]
        return preferred + extra
