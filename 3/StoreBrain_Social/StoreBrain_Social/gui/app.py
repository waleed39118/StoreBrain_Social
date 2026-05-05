"""
gui/app.py — النافذة الرئيسية الكاملة لـ StoreBrain Social
"""
from __future__ import annotations

import sys
import datetime
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import Callable

from core.config     import load_config, is_configured, AppConfig, save_env_values
from core.exceptions import MissingKeyError, StoreBrainError
from core.logger     import get_logger, setup_logging
from services.campaign_manager import CampaignManager, BatchReport
from services.ai_content       import COUNTRY_TOP_PLATFORMS, COUNTRY_BEST_HOURS
from gui.wizard      import SetupWizard

logger = get_logger(__name__)

# ============================================================
# الألوان والثوابت
# ============================================================
BG       = "#1e1e2e"
BG2      = "#2a2a3e"
BG3      = "#313145"
BG4      = "#252535"
GREEN    = "#2ecc71"
BLUE     = "#3498db"
RED      = "#e74c3c"
AMBER    = "#f59e0b"
PURPLE   = "#9b59b6"
FG       = "#ecf0f1"
MUTED    = "#7f8c8d"
CONSOLE  = "#00ff41"
FONT     = ("Segoe UI", 10)
BOLD     = ("Segoe UI", 10, "bold")
TITLE    = ("Segoe UI", 19, "bold")
SMALL    = ("Segoe UI", 9)
MONO     = ("Consolas", 10)

ASSETS   = Path(__file__).parent.parent / "assets"
COUNTRIES = list(COUNTRY_TOP_PLATFORMS.keys())
LANGUAGES = ["العربية", "English", "Français", "Español", "Deutsch"]


# ============================================================
# الواجهة الرئيسية
# ============================================================
class StoreBrainApp:

    def __init__(self, root: tk.Tk) -> None:
        self.root    = root
        self._config: AppConfig | None      = None
        self._manager: CampaignManager | None = None
        self._running = False

        self._setup_window()
        self._apply_ttk_style()
        self._build_ui()

        # تحميل الإعدادات أو فتح الإعداد الأولي
        if not is_configured():
            self.root.after(300, self._open_wizard)
        else:
            self._load_services()

    # ----------------------------------------------------------
    # إعداد النافذة
    # ----------------------------------------------------------
    def _setup_window(self) -> None:
        self.root.title("StoreBrain Social — أتمتة التسويق الذكي")
        self.root.geometry("980x980")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        icon = ASSETS / "logo.png"
        if icon.exists():
            try:
                img = tk.PhotoImage(file=str(icon))
                self.root.iconphoto(True, img)
                self._icon_ref = img
            except Exception:
                pass

    def _apply_ttk_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TEntry",      fieldbackground=BG3, foreground=FG,
                        insertcolor=FG, font=FONT)
        style.configure("TCombobox",   fieldbackground=BG3, foreground=FG,
                        selectbackground=BG3, font=FONT)
        style.map("TCombobox",         fieldbackground=[("readonly", BG3)])
        style.configure("TProgressbar", troughcolor=BG3, background=GREEN, thickness=6)
        style.configure("TNotebook",   background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG2, foreground=MUTED,
                        padding=[14, 6], font=FONT)
        style.map("TNotebook.Tab",
                  background=[("selected", BG3)],
                  foreground=[("selected", FG)])

    # ----------------------------------------------------------
    # بناء الواجهة
    # ----------------------------------------------------------
    def _build_ui(self) -> None:
        # ترويسة
        self._build_header()
        # Notebook رئيسي
        self._nb = ttk.Notebook(self.root)
        self._nb.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        # تبويبات
        self._tab_campaign = tk.Frame(self._nb, bg=BG)
        self._tab_status   = tk.Frame(self._nb, bg=BG)
        self._tab_schedule = tk.Frame(self._nb, bg=BG)
        self._tab_settings = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_campaign, text="🚀 حملة جديدة")
        self._nb.add(self._tab_status,   text="📊 حالة المنصات")
        self._nb.add(self._tab_schedule, text="📅 الجدول الزمني")
        self._nb.add(self._tab_settings, text="⚙️ الإعدادات")
        self._build_tab_campaign()
        self._build_tab_status()
        self._build_tab_schedule()
        self._build_tab_settings()
        # شريط الحالة السفلي
        self._build_statusbar()

    def _build_header(self) -> None:
        hdr = tk.Frame(self.root, bg="#13131f", height=64)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        # لوجو
        logo_path = ASSETS / "logo.png"
        if logo_path.exists():
            try:
                raw = tk.PhotoImage(file=str(logo_path))
                # تصغير اللوجو 4x
                self._logo_img = raw.subsample(max(raw.width() // 48, 1),
                                               max(raw.height() // 48, 1))
                tk.Label(hdr, image=self._logo_img, bg="#13131f").pack(
                    side="left", padx=(18, 6), pady=8)
            except Exception:
                pass
        tk.Label(hdr, text="StoreBrain", font=("Segoe UI", 18, "bold"),
                 bg="#13131f", fg=GREEN).pack(side="left", pady=10)
        tk.Label(hdr, text="Social", font=("Segoe UI", 18),
                 bg="#13131f", fg=BLUE).pack(side="left", pady=10)
        tk.Label(hdr, text="أتمتة التسويق الذكي",
                 font=SMALL, bg="#13131f", fg=MUTED).pack(side="left", padx=10, pady=16)
        # أزرار الترويسة
        for text, cmd, color in [
            ("⚙️ الإعدادات", self._open_wizard, MUTED),
            ("🔗 اختبار الكل", self._test_all, BLUE),
        ]:
            tk.Button(hdr, text=text, font=SMALL, bg="#13131f", fg=color,
                      relief="flat", cursor="hand2",
                      activebackground="#13131f", activeforeground=FG,
                      command=cmd).pack(side="right", padx=8)

    # ----------------------------------------------------------
    # تبويب الحملة
    # ----------------------------------------------------------
    def _build_tab_campaign(self) -> None:
        pad = {"padx": 20, "pady": (0, 10)}

        # --- قسم الإعدادات العامة ---
        sec1 = self._card(self._tab_campaign, "🌍 إعدادات الحملة")
        sec1.pack(fill="x", **pad)

        row1 = tk.Frame(sec1, bg=BG2)
        row1.pack(fill="x")

        # الدولة
        col1 = tk.Frame(row1, bg=BG2)
        col1.pack(side="left", fill="x", expand=True, padx=(0, 10))
        tk.Label(col1, text="الدولة المستهدفة:", font=SMALL, bg=BG2, fg=MUTED).pack(anchor="w")
        self._country_var = tk.StringVar(value="عالمي")
        self._country_cb  = ttk.Combobox(col1, textvariable=self._country_var,
                                          values=COUNTRIES, state="readonly", width=20)
        self._country_cb.pack(fill="x", pady=(2, 0))
        self._country_cb.bind("<<ComboboxSelected>>", self._on_country_change)

        # اللغة
        col2 = tk.Frame(row1, bg=BG2)
        col2.pack(side="left", fill="x", expand=True, padx=(0, 10))
        tk.Label(col2, text="لغة المحتوى:", font=SMALL, bg=BG2, fg=MUTED).pack(anchor="w")
        self._lang_var = tk.StringVar(value="العربية")
        ttk.Combobox(col2, textvariable=self._lang_var,
                     values=LANGUAGES, state="readonly", width=20).pack(fill="x", pady=(2, 0))

        # عدد المنتجات
        col3 = tk.Frame(row1, bg=BG2)
        col3.pack(side="left", fill="x", expand=True)
        tk.Label(col3, text="عدد المنتجات:", font=SMALL, bg=BG2, fg=MUTED).pack(anchor="w")
        self._limit_var = tk.StringVar(value="5")
        ttk.Combobox(col3, textvariable=self._limit_var,
                     values=["1", "3", "5", "10", "20", "50"],
                     state="readonly", width=10).pack(fill="x", pady=(2, 0))

        # --- قسم المنصات ---
        sec2 = self._card(self._tab_campaign, "📢 المنصات المستهدفة")
        sec2.pack(fill="x", **pad)

        self._platform_vars: dict[str, tk.BooleanVar] = {}
        platforms_all = ["Facebook", "Instagram", "Telegram", "Pinterest",
                         "LinkedIn", "Twitter", "Reddit", "YouTube"]

        plat_grid = tk.Frame(sec2, bg=BG2)
        plat_grid.pack(fill="x")

        icons = {"Facebook":"📘","Instagram":"📸","Telegram":"✈️","Pinterest":"📌",
                 "LinkedIn":"💼","Twitter":"🐦","Reddit":"👽","YouTube":"▶️"}

        for i, p in enumerate(platforms_all):
            var = tk.BooleanVar(value=True)
            self._platform_vars[p] = var
            cb = tk.Checkbutton(
                plat_grid, text=f"{icons.get(p,'')} {p}",
                variable=var, bg=BG2, fg=FG, selectcolor=BG3,
                activebackground=BG2, activeforeground=FG,
                font=SMALL, cursor="hand2",
            )
            cb.grid(row=i // 4, column=i % 4, sticky="w", padx=12, pady=4)

        # زر "حدد الأنسب حسب الدولة"
        tk.Button(sec2, text="✨ اختر الأنسب للدولة تلقائياً",
                  bg=BG3, fg=BLUE, font=SMALL, relief="flat", cursor="hand2",
                  command=self._auto_select_platforms).pack(anchor="w", pady=(6, 0))

        # --- قسم التأخير ---
        sec3 = self._card(self._tab_campaign, "⏱️ إعدادات الوقت")
        sec3.pack(fill="x", **pad)

        row3 = tk.Frame(sec3, bg=BG2)
        row3.pack(fill="x")

        for label, var_name, default, opts in [
            ("تأخير بين المنصات (ثانية):", "_delay_plat", "3",
             ["1","2","3","5","10"]),
            ("تأخير بين المنتجات (ثانية):", "_delay_prod", "10",
             ["5","10","15","20","30","60"]),
        ]:
            col = tk.Frame(row3, bg=BG2)
            col.pack(side="left", fill="x", expand=True, padx=(0, 10))
            tk.Label(col, text=label, font=SMALL, bg=BG2, fg=MUTED).pack(anchor="w")
            var = tk.StringVar(value=default)
            setattr(self, var_name + "_var", var)
            ttk.Combobox(col, textvariable=var, values=opts,
                         state="readonly", width=14).pack(fill="x", pady=(2, 0))

        # --- زر الإطلاق ---
        self._launch_btn = tk.Button(
            self._tab_campaign,
            text="🚀 إطلاق الحملة الآن",
            font=("Segoe UI", 14, "bold"),
            bg=GREEN, fg="white",
            activebackground="#27ae60",
            relief="flat", cursor="hand2",
            command=self._launch_campaign,
        )
        self._launch_btn.pack(pady=14, ipadx=60, ipady=10)

        # شريط التقدم
        self._prog_lbl = tk.Label(self._tab_campaign, text="",
                                   font=SMALL, bg=BG, fg=MUTED)
        self._prog_lbl.pack()
        self._prog_bar = ttk.Progressbar(self._tab_campaign, mode="determinate", length=500)
        self._prog_bar.pack(pady=(0, 8))

        # --- السجل ---
        log_hdr = tk.Frame(self._tab_campaign, bg=BG)
        log_hdr.pack(fill="x", padx=20)
        tk.Label(log_hdr, text="🖥️ سجل العمليات:",
                 font=SMALL, bg=BG, fg=MUTED).pack(side="left")
        tk.Button(log_hdr, text="🗑 مسح", font=SMALL, bg=BG, fg=MUTED,
                  relief="flat", cursor="hand2",
                  command=self._clear_log).pack(side="right")

        console_frame = tk.Frame(self._tab_campaign, bg=BG)
        console_frame.pack(fill="x", padx=20, pady=(2, 10))
        sb = tk.Scrollbar(console_frame)
        sb.pack(side="right", fill="y")
        self._console = tk.Text(
            console_frame, height=12,
            bg="#0d1117", fg=CONSOLE,
            font=MONO, padx=12, pady=8,
            state="disabled", yscrollcommand=sb.set,
            wrap="word",
        )
        self._console.pack(fill="x")
        sb.config(command=self._console.yview)
        # ألوان النص
        self._console.tag_config("ok",   foreground=GREEN)
        self._console.tag_config("err",  foreground=RED)
        self._console.tag_config("warn", foreground=AMBER)
        self._console.tag_config("info", foreground=CONSOLE)
        self._console.tag_config("ts",   foreground="#444466")

    # ----------------------------------------------------------
    # تبويب حالة المنصات
    # ----------------------------------------------------------
    def _build_tab_status(self) -> None:
        tk.Label(self._tab_status, text="اضغط 'اختبار الكل' للتحقق من جميع الاتصالات",
                 font=SMALL, bg=BG, fg=MUTED).pack(pady=(14, 6))

        self._status_frame = tk.Frame(self._tab_status, bg=BG)
        self._status_frame.pack(fill="both", expand=True, padx=20)

        self._platform_status_lbls: dict[str, tk.Label] = {}
        all_platforms = ["Shopify", "Facebook", "Instagram", "Telegram",
                         "Pinterest", "LinkedIn", "Twitter", "Reddit", "YouTube"]
        icons = {"Shopify":"🛍️","Facebook":"📘","Instagram":"📸","Telegram":"✈️",
                 "Pinterest":"📌","LinkedIn":"💼","Twitter":"🐦",
                 "Reddit":"👽","YouTube":"▶️"}

        for i, name in enumerate(all_platforms):
            row = tk.Frame(self._status_frame, bg=BG2, pady=1)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"  {icons.get(name,'')} {name}",
                     font=BOLD, bg=BG2, fg=FG, width=20, anchor="w").pack(side="left", padx=8)
            lbl = tk.Label(row, text="⬜ لم يُختبر بعد",
                           font=FONT, bg=BG2, fg=MUTED, anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            self._platform_status_lbls[name] = lbl

        tk.Button(self._tab_status, text="🔗 اختبار جميع الاتصالات",
                  font=BOLD, bg=BLUE, fg="white", relief="flat",
                  cursor="hand2", pady=8, padx=20,
                  command=self._test_all).pack(pady=16)

    # ----------------------------------------------------------
    # تبويب الجدول الزمني
    # ----------------------------------------------------------
    def _build_tab_schedule(self) -> None:
        tk.Label(self._tab_schedule,
                 text="📅 أفضل أوقات النشر حسب الدولة",
                 font=("Segoe UI", 13, "bold"), bg=BG, fg=FG).pack(pady=(16, 4))
        tk.Label(self._tab_schedule,
                 text="الأوقات بتوقيت UTC — احسب فارق التوقيت حسب دولتك",
                 font=SMALL, bg=BG, fg=MUTED).pack(pady=(0, 12))

        frame = tk.Frame(self._tab_schedule, bg=BG)
        frame.pack(fill="both", expand=True, padx=20)

        # رأس الجدول
        headers = ["الدولة", "أفضل الأوقات (UTC)", "المنصات المفضلة"]
        widths  = [16, 28, 45]
        for col, (h, w) in enumerate(zip(headers, widths)):
            tk.Label(frame, text=h, font=BOLD, bg=BG3, fg=BLUE,
                     width=w, anchor="w", pady=6).grid(
                row=0, column=col, padx=2, pady=2, sticky="ew")

        for row_i, (country, hours) in enumerate(COUNTRY_BEST_HOURS.items(), start=1):
            platforms = ", ".join(COUNTRY_TOP_PLATFORMS.get(country, [])[:4])
            hours_str = "  |  ".join(f"{h:02d}:00" for h in hours)
            bg_row    = BG2 if row_i % 2 == 0 else BG4
            for col, (val, w) in enumerate(zip(
                [country, hours_str, platforms], widths
            )):
                tk.Label(frame, text=val, font=FONT, bg=bg_row, fg=FG,
                         width=w, anchor="w", pady=5).grid(
                    row=row_i, column=col, padx=2, pady=1, sticky="ew")

        # --- قسم الجدولة التلقائية ---
        sched_card = self._card(self._tab_schedule, "⏰ جدولة تلقائية يومية")
        sched_card.pack(fill="x", padx=20, pady=16)

        row_s = tk.Frame(sched_card, bg=BG2)
        row_s.pack(fill="x")

        tk.Label(row_s, text="تشغيل تلقائي كل:", font=SMALL, bg=BG2, fg=MUTED).pack(side="left")
        self._sched_interval_var = tk.StringVar(value="24 ساعة")
        ttk.Combobox(row_s, textvariable=self._sched_interval_var,
                     values=["6 ساعات", "12 ساعة", "24 ساعة", "48 ساعة"],
                     state="readonly", width=14).pack(side="left", padx=8)

        self._sched_btn = tk.Button(
            sched_card,
            text="▶ تفعيل الجدولة التلقائية",
            font=BOLD, bg=PURPLE, fg="white",
            relief="flat", cursor="hand2", pady=6,
            command=self._toggle_scheduler,
        )
        self._sched_btn.pack(pady=(10, 0))
        self._sched_active  = False
        self._sched_thread: threading.Thread | None = None

    # ----------------------------------------------------------
    # تبويب الإعدادات
    # ----------------------------------------------------------
    def _build_tab_settings(self) -> None:
        tk.Label(self._tab_settings,
                 text="⚙️ إعدادات مفاتيح API",
                 font=("Segoe UI", 13, "bold"), bg=BG, fg=FG).pack(pady=(16, 4))
        tk.Label(self._tab_settings,
                 text="يمكنك تعديل أي مفتاح هنا مباشرة أو فتح معالج الإعداد الكامل.",
                 font=SMALL, bg=BG, fg=MUTED).pack(pady=(0, 10))

        # أزرار سريعة
        btns = tk.Frame(self._tab_settings, bg=BG)
        btns.pack(pady=(0, 16))
        tk.Button(btns, text="🧙 فتح معالج الإعداد الكامل",
                  font=BOLD, bg=BLUE, fg="white", relief="flat",
                  cursor="hand2", padx=16, pady=8,
                  command=self._open_wizard).pack(side="left", padx=6)
        tk.Button(btns, text="🔗 اختبار الكل",
                  font=FONT, bg=BG3, fg=FG, relief="flat",
                  cursor="hand2", padx=16, pady=8,
                  command=self._test_all).pack(side="left", padx=6)

        # حقول المفاتيح السريعة
        scroll_frame = tk.Frame(self._tab_settings, bg=BG)
        scroll_frame.pack(fill="both", expand=True, padx=20)

        fields = [
            ("SHOP_URL",            "🛍️ رابط المتجر",         False),
            ("SHOPIFY_API_TOKEN",   "🔑 Shopify Token",        True),
            ("GROQ_API_KEY",        "🤖 Groq API Key",         True),
            ("META_PAGE_ID",        "📘 Facebook Page ID",     False),
            ("META_PAGE_TOKEN",     "📘 Facebook Token",       True),
            ("INSTAGRAM_ACCOUNT_ID","📸 Instagram Account ID", False),
            ("TELEGRAM_BOT_TOKEN",  "✈️ Telegram Bot Token",   True),
            ("TELEGRAM_CHANNEL_ID", "✈️ Telegram Channel",     False),
            ("PINTEREST_TOKEN",     "📌 Pinterest Token",      True),
            ("PINTEREST_BOARD_ID",  "📌 Pinterest Board ID",   False),
            ("LINKEDIN_TOKEN",      "💼 LinkedIn Token",       True),
            ("LINKEDIN_ORG_ID",     "💼 LinkedIn Org ID",      False),
            ("TWITTER_API_KEY",     "🐦 Twitter API Key",      True),
            ("TWITTER_API_SECRET",  "🐦 Twitter API Secret",   True),
            ("TWITTER_ACCESS_TOKEN","🐦 Twitter Access Token", True),
            ("TWITTER_ACCESS_SECRET","🐦 Twitter Access Secret",True),
            ("REDDIT_CLIENT_ID",    "👽 Reddit Client ID",     False),
            ("REDDIT_CLIENT_SECRET","👽 Reddit Secret",        True),
            ("REDDIT_USERNAME",     "👽 Reddit Username",      False),
            ("REDDIT_PASSWORD",     "👽 Reddit Password",      True),
            ("REDDIT_SUBREDDITS",   "👽 Subreddits",           False),
            ("YOUTUBE_API_KEY",     "▶️ YouTube API Key",      True),
            ("YOUTUBE_CHANNEL_ID",  "▶️ YouTube Channel ID",   False),
        ]

        self._settings_vars: dict[str, tk.StringVar] = {}
        self._load_settings_vars(fields)

        canvas   = tk.Canvas(scroll_frame, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
        inner    = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for env_key, label, secret in fields:
            row = tk.Frame(inner, bg=BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, font=SMALL, bg=BG, fg=MUTED,
                     width=26, anchor="w").pack(side="left")
            ent = ttk.Entry(row, textvariable=self._settings_vars[env_key],
                            show="•" if secret else "", width=48)
            ent.pack(side="left", fill="x", expand=True)

        tk.Button(self._tab_settings, text="💾 حفظ التغييرات",
                  font=BOLD, bg=GREEN, fg="white",
                  relief="flat", cursor="hand2", pady=8, padx=20,
                  command=self._save_settings).pack(pady=12)

    def _load_settings_vars(self, fields: list) -> None:
        from core.config import ENV_PATH
        from dotenv import load_dotenv
        import os
        load_dotenv(ENV_PATH, override=True)
        for env_key, _, _ in fields:
            self._settings_vars[env_key] = tk.StringVar(
                value=os.getenv(env_key, "")
            )

    def _save_settings(self) -> None:
        vals = {k: v.get().strip() for k, v in self._settings_vars.items() if v.get().strip()}
        save_env_values(vals)
        self._load_services()
        self._log("✅ تم حفظ الإعدادات وإعادة تحميل الخدمات.")
        messagebox.showinfo("تم", "تم حفظ الإعدادات بنجاح!", parent=self.root)

    # ----------------------------------------------------------
    # شريط الحالة
    # ----------------------------------------------------------
    def _build_statusbar(self) -> None:
        bar = tk.Frame(self.root, bg="#13131f", height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._status_lbl = tk.Label(bar, text="جاهز.", font=SMALL,
                                     bg="#13131f", fg=MUTED, anchor="w")
        self._status_lbl.pack(side="left", padx=14, fill="x", expand=True)
        self._time_lbl = tk.Label(bar, text="", font=SMALL,
                                   bg="#13131f", fg=MUTED)
        self._time_lbl.pack(side="right", padx=14)
        self._update_clock()

    def _update_clock(self) -> None:
        now = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        self._time_lbl.config(text=now)
        self.root.after(1000, self._update_clock)

    def _set_status(self, msg: str, color: str = MUTED) -> None:
        self.root.after(0, lambda: self._status_lbl.config(text=msg, fg=color))

    # ----------------------------------------------------------
    # تحميل الخدمات
    # ----------------------------------------------------------
    def _load_services(self) -> None:
        try:
            self._config  = load_config()
            self._manager = CampaignManager(self._config, log_callback=self._log)
            active = self._config.active_platforms()
            self._log(f"✅ الخدمات جاهزة | المنصات المُفعَّلة: {', '.join(active) if active else 'لا شيء'}")
            self._set_status("جاهز.", GREEN)
        except MissingKeyError as e:
            self._log(f"❌ مفتاح مفقود: {e.key_name} — افتح الإعدادات.")
            self._set_status(f"مفتاح مفقود: {e.key_name}", RED)
        except Exception as e:
            self._log(f"❌ خطأ في التهيئة: {e}")
            self._set_status("خطأ في التهيئة", RED)

    # ----------------------------------------------------------
    # إطلاق الحملة
    # ----------------------------------------------------------
    def _launch_campaign(self) -> None:
        if self._running:
            return
        if not self._manager:
            self._log("❌ الإعدادات غير مكتملة — افتح الإعدادات أولاً.")
            return

        selected = [p for p, v in self._platform_vars.items() if v.get()]
        if not selected:
            messagebox.showwarning("تنبيه", "اختر منصة واحدة على الأقل!", parent=self.root)
            return

        try:
            limit    = int(self._limit_var.get())
            delay_p  = int(getattr(self, "_delay_plat_var").get())
            delay_pr = int(getattr(self, "_delay_prod_var").get())
        except ValueError:
            self._log("❌ قيم الوقت غير صحيحة.")
            return

        country  = self._country_var.get()
        language = self._lang_var.get()

        self._running = True
        self._set_launch_btn(False)
        self._console_clear()
        self._prog_bar.config(maximum=limit, value=0)
        self._prog_lbl.config(text="")

        self._log(f"🚀 بدء الحملة | الدولة: {country} | اللغة: {language} | المنتجات: {limit}")
        self._log(f"📢 المنصات: {', '.join(selected)}")

        def _run():
            def _prog(cur, tot):
                self.root.after(0, self._prog_bar.config, {"value": cur})
                self.root.after(0, self._prog_lbl.config,
                                {"text": f"المنتج {cur} من {tot}"})

            self._manager.run_batch(
                product_limit  = limit,
                country        = country,
                language       = language,
                platforms      = selected,
                delay_between  = delay_pr,
                progress_cb    = _prog,
            )
            self.root.after(0, self._on_campaign_done)

        threading.Thread(target=_run, daemon=True).start()

    def _on_campaign_done(self) -> None:
        self._running = False
        self._set_launch_btn(True)
        self._prog_lbl.config(text="✅ اكتملت الحملة")
        self._set_status("اكتملت الحملة", GREEN)

    def _set_launch_btn(self, enabled: bool) -> None:
        if enabled:
            self._launch_btn.config(state="normal", bg=GREEN,
                                     text="🚀 إطلاق الحملة الآن")
        else:
            self._launch_btn.config(state="disabled", bg="#4d6272",
                                     text="⏳ جاري التنفيذ...")

    # ----------------------------------------------------------
    # السجل (thread-safe)
    # ----------------------------------------------------------
    def _log(self, message: str) -> None:
        def _write():
            ts  = datetime.datetime.now().strftime("%H:%M:%S")
            tag = ("ok"   if any(c in message for c in ("✅","🎉","💾")) else
                   "err"  if any(c in message for c in ("❌","فشل","خطأ")) else
                   "warn" if any(c in message for c in ("⚠️","تخطي")) else "info")
            self._console.config(state="normal")
            self._console.insert(tk.END, f"[{ts}] ", "ts")
            self._console.insert(tk.END, f"{message}\n", tag)
            self._console.see(tk.END)
            self._console.config(state="disabled")
        self.root.after(0, _write)
        logger.info(message)

    def _clear_log(self) -> None:
        self._console.config(state="normal")
        self._console.delete("1.0", tk.END)
        self._console.config(state="disabled")

    def _console_clear(self) -> None:
        self.root.after(0, self._clear_log)

    # ----------------------------------------------------------
    # اختبار الاتصالات
    # ----------------------------------------------------------
    def _test_all(self) -> None:
        if not self._manager:
            self._log("❌ حمّل الإعدادات أولاً.")
            return

        # تبديل للتبويب الثاني
        self._nb.select(1)
        for lbl in self._platform_status_lbls.values():
            lbl.config(text="⏳ جاري الفحص...", fg=AMBER)

        def _run():
            results = self._manager.test_all_connections()
            def _update():
                for name, (ok, msg) in results.items():
                    lbl = self._platform_status_lbls.get(name)
                    if lbl:
                        lbl.config(text=msg, fg=GREEN if ok else RED)
            self.root.after(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    # ----------------------------------------------------------
    # معالج الإعداد
    # ----------------------------------------------------------
    def _open_wizard(self) -> None:
        def _done():
            self._load_services()
            self._load_settings_vars([
                (k, "", False) for k in self._settings_vars
            ])
            self._log("✅ تم تحديث الإعدادات.")
        SetupWizard(parent=self.root, on_complete=_done)

    # ----------------------------------------------------------
    # اختيار المنصات حسب الدولة
    # ----------------------------------------------------------
    def _on_country_change(self, event=None) -> None:
        self._auto_select_platforms()

    def _auto_select_platforms(self) -> None:
        from services.ai_content import COUNTRY_TOP_PLATFORMS
        country    = self._country_var.get()
        preferred  = COUNTRY_TOP_PLATFORMS.get(country, [])
        for p, var in self._platform_vars.items():
            var.set(p in preferred)

    # ----------------------------------------------------------
    # الجدولة التلقائية
    # ----------------------------------------------------------
    def _toggle_scheduler(self) -> None:
        if self._sched_active:
            self._sched_active = False
            self._sched_btn.config(text="▶ تفعيل الجدولة التلقائية", bg=PURPLE)
            self._log("⏹  تم إيقاف الجدولة التلقائية.")
        else:
            self._sched_active = True
            self._sched_btn.config(text="⏹ إيقاف الجدولة", bg=RED)
            interval_text = self._sched_interval_var.get()
            hours         = int(interval_text.split()[0])
            self._log(f"⏰ الجدولة التلقائية مُفعَّلة — كل {hours} ساعة.")
            self._sched_thread = threading.Thread(
                target=self._scheduler_loop, args=(hours,), daemon=True
            )
            self._sched_thread.start()

    def _scheduler_loop(self, every_hours: int) -> None:
        import time
        interval = every_hours * 3600
        while self._sched_active:
            self._log(f"⏰ الجدولة التلقائية: بدء تشغيل الحملة...")
            if self._manager and not self._running:
                self._running = True
                self.root.after(0, self._set_launch_btn, False)
                selected = [p for p, v in self._platform_vars.items() if v.get()]
                self._manager.run_batch(
                    product_limit=int(self._limit_var.get()),
                    country=self._country_var.get(),
                    language=self._lang_var.get(),
                    platforms=selected,
                    delay_between=10,
                )
                self._running = False
                self.root.after(0, self._set_launch_btn, True)
            for _ in range(interval):
                if not self._sched_active:
                    return
                time.sleep(1)

    # ----------------------------------------------------------
    # مساعد: بطاقة قسم
    # ----------------------------------------------------------
    def _card(self, parent: tk.Widget, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=BG)
        tk.Label(outer, text=title, font=BOLD, bg=BG, fg=MUTED).pack(anchor="w", pady=(8,3))
        inner = tk.Frame(outer, bg=BG2, padx=14, pady=12)
        inner.pack(fill="x")
        return inner
