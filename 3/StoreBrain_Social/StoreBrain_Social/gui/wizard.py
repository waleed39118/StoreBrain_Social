"""
gui/wizard.py — معالج الإعداد الأولي (خطوة بخطوة)
يجمع مفاتيح Shopify و Groq وكل منصات التواصل الاجتماعي.
"""
from __future__ import annotations
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable
import requests
from core.config import save_env_values, ENV_PATH

# ألوان
BG    = "#1e1e2e"
BG2   = "#2a2a3e"
BG3   = "#313145"
GREEN = "#2ecc71"
BLUE  = "#3498db"
RED   = "#e74c3c"
AMBER = "#f59e0b"
FG    = "#ecf0f1"
MUTED = "#7f8c8d"
FONT  = ("Segoe UI", 10)
BOLD  = ("Segoe UI", 10, "bold")


# ============================================================
# اختبارات الاتصال (خيط خلفي)
# ============================================================
def _test_shopify(token: str, shop_url: str) -> tuple:
    clean = shop_url.replace("https://", "").replace("http://", "").rstrip("/")
    if not token or not clean:
        return False, "أدخل التوكن ورابط المتجر."
    try:
        res = requests.get(
            f"https://{clean}/admin/api/2025-01/shop.json",
            headers={"X-Shopify-Access-Token": token}, timeout=12,
        )
        if res.ok:
            return True, f"✅ Shopify — {res.json().get('shop',{}).get('name','')}"
        return False, f"❌ Shopify — خطأ {res.status_code}"
    except Exception as e:
        return False, f"❌ {e}"


def _test_groq(key: str) -> tuple:
    if not key:
        return False, "أدخل مفتاح Groq."
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 3},
            timeout=12,
        )
        if res.ok:    return True, "✅ Groq AI — مفتاح صالح"
        if res.status_code == 401: return False, "❌ Groq — مفتاح غير صالح"
        if res.status_code == 429: return True,  "✅ Groq — صالح (حد مؤقت)"
        return False, f"❌ Groq — خطأ {res.status_code}"
    except Exception as e:
        return False, f"❌ {e}"


def _test_facebook(page_id: str, token: str) -> tuple:
    if not page_id or not token:
        return False, "أدخل Page ID والتوكن."
    try:
        res = requests.get(
            f"https://graph.facebook.com/v19.0/{page_id}?fields=name&access_token={token}",
            timeout=10,
        )
        if res.ok:
            return True, f"✅ Facebook — {res.json().get('name','')}"
        return False, f"❌ Facebook — خطأ {res.status_code}"
    except Exception as e:
        return False, f"❌ {e}"


def _test_telegram(bot_token: str) -> tuple:
    if not bot_token:
        return False, "أدخل توكن البوت."
    try:
        res = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=8)
        if res.ok:
            return True, f"✅ Telegram — @{res.json().get('result',{}).get('username','')}"
        return False, f"❌ Telegram — توكن خاطئ"
    except Exception as e:
        return False, f"❌ {e}"


# ============================================================
# معالج الإعداد
# ============================================================
class SetupWizard(tk.Toplevel):

    _STEPS = ["مرحبًا", "Shopify", "Groq AI", "Facebook/IG",
              "Telegram", "المنصات الأخرى", "اكتمل"]

    def __init__(self, parent=None, on_complete: Callable | None = None) -> None:
        super().__init__(parent)
        self.on_complete = on_complete
        self._step       = 0
        self._tests: dict[str, tuple] = {}

        self.title("StoreBrain Social — الإعداد الأولي")
        self.geometry("640x620")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.grab_set()

        self._vars: dict[str, tk.StringVar] = {k: tk.StringVar() for k in [
            "SHOP_URL", "SHOPIFY_API_TOKEN", "GROQ_API_KEY",
            "META_PAGE_ID", "META_PAGE_TOKEN", "INSTAGRAM_ACCOUNT_ID",
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID",
            "PINTEREST_TOKEN", "PINTEREST_BOARD_ID",
            "LINKEDIN_TOKEN", "LINKEDIN_ORG_ID",
            "TWITTER_API_KEY", "TWITTER_API_SECRET",
            "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET",
            "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
            "REDDIT_USERNAME", "REDDIT_PASSWORD", "REDDIT_SUBREDDITS",
            "YOUTUBE_API_KEY", "YOUTUBE_CHANNEL_ID",
        ]}
        self._load_existing()
        self._build_shell()
        self._show_step(0)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------------------------------------------------
    def _load_existing(self) -> None:
        if not ENV_PATH.exists():
            return
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k in self._vars and v:
                            self._vars[k].set(v)
        except Exception:
            pass

    def _build_shell(self) -> None:
        # شريط التقدم
        top = tk.Frame(self, bg="#13131f", height=48)
        top.pack(fill="x")
        top.pack_propagate(False)
        inner = tk.Frame(top, bg="#13131f")
        inner.pack(expand=True, fill="both")
        self._step_lbls: list[tk.Label] = []
        for name in self._STEPS:
            lbl = tk.Label(inner, text=name, bg="#13131f", fg="#3a3a5c",
                           font=("Segoe UI", 8))
            lbl.pack(side="left", expand=True, pady=14)
            self._step_lbls.append(lbl)

        # محتوى
        self._content = tk.Frame(self, bg=BG)
        self._content.pack(fill="both", expand=True, padx=36, pady=14)

        # أزرار
        nav = tk.Frame(self, bg=BG)
        nav.pack(fill="x", padx=36, pady=(0, 14))

        self._btn_back = tk.Button(nav, text="← السابق", bg=BG3, fg=FG,
                                   font=FONT, relief="flat", cursor="hand2",
                                   padx=14, pady=7, command=self._go_back)
        self._btn_test = tk.Button(nav, text="🔗 اختبار", bg=BLUE, fg="white",
                                   font=FONT, relief="flat", cursor="hand2",
                                   padx=14, pady=7, command=self._run_test)
        self._btn_next = tk.Button(nav, text="التالي →", bg=GREEN, fg="white",
                                   font=BOLD, relief="flat", cursor="hand2",
                                   padx=14, pady=7, command=self._go_next)
        self._btn_next.pack(side="right")

    def _show_step(self, step: int) -> None:
        self._step = step
        for i, lbl in enumerate(self._step_lbls):
            if i == step:
                lbl.config(fg=GREEN, font=("Segoe UI", 8, "bold"))
            elif i < step:
                lbl.config(fg="#5a7a6a", font=("Segoe UI", 8))
            else:
                lbl.config(fg="#3a3a5c", font=("Segoe UI", 8))

        for w in self._content.winfo_children():
            w.destroy()

        renders = [self._r_welcome, self._r_shopify, self._r_groq,
                   self._r_facebook, self._r_telegram, self._r_others, self._r_done]
        renders[step]()

        is_last   = step == len(self._STEPS) - 1
        show_test = step in (1, 2, 3, 4)
        show_back = step > 0

        for b in (self._btn_back, self._btn_test):
            b.pack_forget()
        if show_back:
            self._btn_back.pack(side="left")
        if show_test:
            self._btn_test.pack(side="right", padx=(0, 8))
        self._btn_next.config(text="إنهاء وحفظ ✓" if is_last else "التالي →")

    # ----------------------------------------------------------
    # محتوى الخطوات
    # ----------------------------------------------------------
    def _lbl(self, text, fg=MUTED, font=("Segoe UI", 9)):
        tk.Label(self._content, text=text, bg=BG, fg=fg, font=font,
                 justify="left", wraplength=530).pack(anchor="w", pady=(0, 3))

    def _head(self, title, desc=""):
        tk.Label(self._content, text=title, bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 4))
        if desc:
            tk.Label(self._content, text=desc, bg=BG, fg=MUTED,
                     font=("Segoe UI", 9), justify="left", wraplength=530).pack(anchor="w", pady=(0, 12))

    def _entry(self, label, var_key, secret=False, placeholder=""):
        tk.Label(self._content, text=label, bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
        ent = ttk.Entry(self._content, textvariable=self._vars[var_key],
                        show="•" if secret else "", width=60)
        ent.pack(fill="x", pady=(2, 8))
        if placeholder and not self._vars[var_key].get():
            ent.insert(0, placeholder)
            ent.config(foreground="gray")
            def _in(e, w=ent, p=placeholder, s=secret):
                if w.get() == p:
                    w.delete(0, "end")
                    w.config(foreground="black", show="•" if s else "")
            def _out(e, w=ent, p=placeholder):
                if not w.get():
                    w.insert(0, p)
                    w.config(foreground="gray", show="")
            ent.bind("<FocusIn>",  _in)
            ent.bind("<FocusOut>", _out)

    def _status(self, attr):
        lbl = tk.Label(self._content, text="", bg=BG, fg=MUTED, font=FONT)
        lbl.pack(anchor="w", pady=(2, 0))
        setattr(self, f"_{attr}", lbl)

    def _r_welcome(self):
        tk.Label(self._content, text="👑", font=("Segoe UI", 52), bg=BG, fg=GREEN).pack(pady=(10,4))
        tk.Label(self._content, text="StoreBrain Social", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=GREEN).pack()
        tk.Label(self._content, text="أتمتة التسويق على جميع منصات التواصل الاجتماعي",
                 font=("Segoe UI", 11), bg=BG, fg=MUTED).pack(pady=6)
        tk.Label(self._content,
                 text="سنُعدّ مفاتيح الاتصال في خطوات بسيطة.\n"
                      "المفاتيح غير الموجودة لديك؟ اتركها فارغة وأضفها لاحقاً.",
                 font=("Segoe UI", 10), bg=BG, fg=MUTED, justify="center").pack(pady=14)
        links_f = tk.Frame(self._content, bg=BG2)
        links_f.pack(fill="x", pady=6, ipady=8)
        for text, url in [
            ("🔑 Groq AI (مجاني)", "https://console.groq.com/keys"),
            ("🏪 Shopify Admin",    "https://accounts.shopify.com"),
            ("📘 Facebook Developers", "https://developers.facebook.com"),
            ("🤖 Telegram BotFather",  "https://t.me/BotFather"),
            ("📌 Pinterest Developers","https://developers.pinterest.com"),
        ]:
            lbl = tk.Label(links_f, text=text, bg=BG2, fg=BLUE,
                           font=("Segoe UI", 10), cursor="hand2")
            lbl.pack(anchor="w", padx=14, pady=2)
            lbl.bind("<Button-1>", lambda e, u=url: self._open(u))

    def _r_shopify(self):
        self._head("🏪 إعداد Shopify",
                   "من لوحة Shopify: Settings → Apps → Develop apps\n"
                   "→ Create app → Configure Admin API → read+write products, orders, inventory")
        self._entry("رابط المتجر:", "SHOP_URL", placeholder="your-store.myshopify.com")
        self._entry("Access Token:", "SHOPIFY_API_TOKEN", secret=True, placeholder="shpca_...")
        self._status("shopify_lbl")

    def _r_groq(self):
        self._head("🤖 Groq AI — محرك المحتوى",
                   "مجاني تماماً — احصل على مفتاحك من console.groq.com/keys")
        self._entry("Groq API Key:", "GROQ_API_KEY", secret=True, placeholder="gsk_...")
        self._status("groq_lbl")

    def _r_facebook(self):
        self._head("📘 Facebook + Instagram",
                   "من Facebook Developers → My Apps → أنشئ App\n"
                   "→ Graph API Explorer → احصل على Page Access Token بصلاحية pages_manage_posts")
        self._entry("Facebook Page ID:", "META_PAGE_ID", placeholder="123456789")
        self._entry("Page Access Token:", "META_PAGE_TOKEN", secret=True, placeholder="EAA...")
        self._entry("Instagram Account ID:", "INSTAGRAM_ACCOUNT_ID", placeholder="123456789 (اختياري)")
        self._status("facebook_lbl")

    def _r_telegram(self):
        self._head("✈️ Telegram",
                   "من @BotFather في Telegram: /newbot → احصل على التوكن\n"
                   "أضف البوت كـ Admin في قناتك")
        self._entry("Bot Token:", "TELEGRAM_BOT_TOKEN", secret=True, placeholder="1234:AAA...")
        self._entry("Channel ID:", "TELEGRAM_CHANNEL_ID", placeholder="@your_channel أو -1001234567890")
        self._status("telegram_lbl")

    def _r_others(self):
        self._head("🌐 منصات إضافية (كلها اختيارية)",
                   "اتركها فارغة إن لم تكن لديك — يمكن إضافتها لاحقاً من الإعدادات.")
        # Pinterest
        self._lbl("📌 Pinterest:", fg=FG, font=BOLD)
        self._entry("Access Token:", "PINTEREST_TOKEN", secret=True)
        self._entry("Board ID:", "PINTEREST_BOARD_ID")
        # LinkedIn
        self._lbl("💼 LinkedIn:", fg=FG, font=BOLD)
        self._entry("Access Token:", "LINKEDIN_TOKEN", secret=True)
        self._entry("Organization ID:", "LINKEDIN_ORG_ID")
        # Twitter
        self._lbl("🐦 Twitter/X:", fg=FG, font=BOLD)
        self._entry("API Key:", "TWITTER_API_KEY", secret=True)
        self._entry("API Secret:", "TWITTER_API_SECRET", secret=True)
        self._entry("Access Token:", "TWITTER_ACCESS_TOKEN", secret=True)
        self._entry("Access Secret:", "TWITTER_ACCESS_SECRET", secret=True)
        # Reddit
        self._lbl("👽 Reddit:", fg=FG, font=BOLD)
        self._entry("Client ID:", "REDDIT_CLIENT_ID")
        self._entry("Client Secret:", "REDDIT_CLIENT_SECRET", secret=True)
        self._entry("Username:", "REDDIT_USERNAME")
        self._entry("Password:", "REDDIT_PASSWORD", secret=True)
        self._entry("Subreddits (مفصولة بفاصلة):", "REDDIT_SUBREDDITS",
                    placeholder="ecommerce,entrepreneur")
        # YouTube
        self._lbl("▶️ YouTube:", fg=FG, font=BOLD)
        self._entry("API Key:", "YOUTUBE_API_KEY", secret=True)
        self._entry("Channel ID:", "YOUTUBE_CHANNEL_ID")

    def _r_done(self):
        tk.Label(self._content, text="🎉", font=("Segoe UI", 52), bg=BG, fg=GREEN).pack(pady=(10,4))
        tk.Label(self._content, text="الإعداد مكتمل!", font=("Segoe UI", 16, "bold"),
                 bg=BG, fg=GREEN).pack()
        tk.Label(self._content, text="تم حفظ الإعدادات — اضغط 'إنهاء وحفظ' للبدء.",
                 font=("Segoe UI", 11), bg=BG, fg=MUTED).pack(pady=12)
        for svc, (ok, msg) in self._tests.items():
            tk.Label(self._content, text=f"  {msg}", bg=BG,
                     fg=GREEN if ok else RED, font=("Segoe UI", 10)).pack(anchor="w")

    # ----------------------------------------------------------
    # اختبار الاتصال
    # ----------------------------------------------------------
    def _run_test(self):
        self._btn_test.config(state="disabled", text="⏳...")

        def _bg():
            step = self._step
            if step == 1:
                ok, msg = _test_shopify(self._vars["SHOPIFY_API_TOKEN"].get(),
                                        self._vars["SHOP_URL"].get())
                self._tests["shopify"] = (ok, msg)
                self.after(0, lambda: self._upd("shopify_lbl", ok, msg))
            elif step == 2:
                ok, msg = _test_groq(self._vars["GROQ_API_KEY"].get())
                self._tests["groq"] = (ok, msg)
                self.after(0, lambda: self._upd("groq_lbl", ok, msg))
            elif step == 3:
                ok, msg = _test_facebook(self._vars["META_PAGE_ID"].get(),
                                          self._vars["META_PAGE_TOKEN"].get())
                self._tests["facebook"] = (ok, msg)
                self.after(0, lambda: self._upd("facebook_lbl", ok, msg))
            elif step == 4:
                ok, msg = _test_telegram(self._vars["TELEGRAM_BOT_TOKEN"].get())
                self._tests["telegram"] = (ok, msg)
                self.after(0, lambda: self._upd("telegram_lbl", ok, msg))
            self.after(0, lambda: self._btn_test.config(state="normal", text="🔗 اختبار"))

        threading.Thread(target=_bg, daemon=True).start()

    def _upd(self, attr, ok, msg):
        lbl = getattr(self, f"_{attr}", None)
        if lbl:
            lbl.config(text=msg, fg=GREEN if ok else RED)

    # ----------------------------------------------------------
    def _save(self) -> bool:
        BAD = {"", "اتركها فارغة", "your-store.myshopify.com", "shpca_...", "gsk_...",
               "EAA...", "1234:AAA...", "@your_channel", "123456789", "ecommerce,entrepreneur"}
        vals = {k: v.get().strip() for k, v in self._vars.items()
                if v.get().strip() not in BAD}
        try:
            save_env_values(vals)
            return True
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("خطأ", f"فشل الحفظ:\n{e}", parent=self)
            return False

    def _go_next(self):
        if self._step == len(self._STEPS) - 1:
            if self._save():
                if self.on_complete:
                    self.on_complete()
                self.destroy()
        else:
            self._show_step(self._step + 1)

    def _go_back(self):
        if self._step > 0:
            self._show_step(self._step - 1)

    def _on_close(self):
        from tkinter import messagebox
        if messagebox.askyesno("إغلاق", "إغلاق بدون حفظ؟", parent=self):
            self.destroy()

    @staticmethod
    def _open(url):
        import webbrowser
        webbrowser.open(url)
