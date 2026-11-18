# أدا (Ada) — مساعدة المتجر الذكية

**نقطة بيع + مخزون + تحليلات + ذكاء اصطناعي محلي، بالصوت والنص، بالعربية والإنجليزية.**
يعمل على الآيباد واللابتوب وأجهزة نقاط البيع والجوال، ويستمر البيع حتى دون إنترنت. بياناتك على خادمك أنت، ولا توجد أي خدمة سحابية خارجية.

---

## لماذا أدا؟

| | |
|---|---|
| 🛒 **نقطة بيع سريعة** | قارئ باركود (USB/Bluetooth) أو كاميرا الجهاز، أزرار كبيرة مناسبة للمس، إيصالات ضريبية للطابعات الحرارية 80 مم |
| 📴 **يعمل دون إنترنت** | البيع لا يتوقف؛ تُحفظ العمليات على الجهاز وتُزامَن تلقائياً عند عودة الاتصال، دون أي تكرار |
| 💬 **اسأل أدا** | «كم باقي من الحليب؟»، «بيع 2 بيض»، «ماذا أطلب من المورد؟»، بالكتابة أو بالصوت وباللهجة العامية |
| 🧠 **ذكاء اصطناعي محلي** | نموذج لغوي يعمل على خادمك (Ollama + Qwen)، فلا تخرج محادثات متجرك إلى أي جهة |
| 📊 **قرارات أذكى** | الأكثر مبيعاً واتجاهه، قائمة إعادة الطلب بالكميات، المنتجات الراكدة، وتوازن الفئات |
| 📦 **إدخال المنتجات بكل الطرق** | يدوياً، أو بمسح الباركود، أو من Excel/CSV بعناوين عربية أو إنجليزية مع معاينة قبل الحفظ |
| 🔐 **دخول برقم جوالك فقط** | رمز SMS يُرسَل من شريحة هاتفك (بوابة أدا)، ورمز PIN للموظفين، وصلاحيات: مالك/مدير/كاشير |
| 💾 **نسخ احتياطي تلقائي** | نسخة يومية مع إمكانية تنزيلها |

## التشغيل في 4 خطوات (للتاجر)

1. **خادم:** أي خادم Linux فيه Docker، ونطاق (Domain) يشير إليه. ثم شغّل:
   ```bash
   git clone <repo> && cd <repo>/ada && ./install.sh
   ```
   يسألك المثبّت عن النطاق ورقم جوالك، وينشئ كل الأسرار تلقائياً، ويفعّل HTTPS، ثم يعرض **رمز الإعداد**.
2. **هاتف الرسائل:** ثبّت تطبيق **«بوابة رسائل أدا»** (ملف APK من صفحة Releases) على هاتف أندرويد فيه شريحة. افتح رابط متجرك ← «الإعداد لأول مرة» ← أدخل رمز الإعداد ← امسح رمز QR من تطبيق البوابة.
3. **الدخول:** أدخل رقم جوالك؛ يصلك رمز التحقق برسالة. يظهر معالج سريع، ويمكنك تحميل منتجات تجريبية للتجربة فوراً.
4. **الأجهزة:** على كل آيباد أو لابتوب أو جهاز نقطة بيع افتح الرابط ← «تثبيت التطبيق». أضف الموظفين من «الموظفون»، فيدخل كل منهم برقمه ورمز PIN.

> التحديث لاحقاً: `git pull && ./install.sh`. تُحفظ البيانات والأسرار، وتُطبَّق ترحيلات قاعدة البيانات تلقائياً.

---

## Architecture (for developers)

```
 iPad / laptop / POS / phone ──HTTPS──► Caddy (auto TLS) ──► Ada (FastAPI, SQLite WAL)
   PWA: offline shell + IndexedDB outbox                       │  ├─ Alembic migrations (auto on boot)
                                                               │  ├─ InventoryManager / MarketAnalytics (Pandas)
 Android "Ada SMS Gateway" (owner's SIM) ◄─long-poll───────────┤  ├─ AuthService (SMS OTP owner, PIN staff)
                                                               │  ├─ AutoUpdater (HMAC-signed catalog patches)
                                                               └──► Ollama (local LLM, private network only)
```

| Path | Contents |
|---|---|
| `app/` | FastAPI app: `core/` (inventory, analytics, assistant, local LLM, voice, updater, security), `services/` (auth, SMS, import, backups, settings, demo), `api/` routes |
| `migrations/` | Alembic revisions `0001`–`0003` (batch mode, so they work on both SQLite and PostgreSQL) |
| `web/` | PWA: vanilla ES modules, no build step, no CDN, strict CSP; libraries vendored under `web/vendor` |
| `android-gateway/` | Kotlin SMS gateway app |
| `tests/` | pytest (API, auth, POS, import, migrations, LLM, security), Playwright E2E, real-LLM integration |
| `install.sh`, `docker-compose.yml`, `deploy/Caddyfile`, `Dockerfile` | Production deployment |

### Local development
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt            # add requirements-voice.txt for Whisper
export ADA_AUTH_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))") \
       ADA_OWNER_PHONE=+9665XXXXXXXX ADA_SMS_PROVIDER=console ADA_API_DOCS=true
uvicorn app.main:app --reload                  # http://127.0.0.1:8000  (OTP is printed in the log)
pytest -q
```

### Schema changes
```bash
alembic revision --autogenerate -m "describe change"   # then REVIEW the generated file
alembic upgrade head && alembic check
```
A test fails if `models.py` and the migrations drift apart.

### Catalog update methods
Manual (`POST/PATCH /api/v1/products`), barcode (`GET /products/by-barcode/{code}` with check-digit validation), Excel/CSV (`POST /products/import`, with `dry_run`, `stock_mode=set|add` and `skip_invalid`), downloadable template, and HMAC-signed patches (`POST /system/patches` or pull mode).

### Local AI
Rule-based parsing runs first. Only text the rules don't understand goes to the local model, which must return JSON in a fixed schema with a closed set of intents. Role checks are applied after the model runs. Stock figures and prices always come from the database. If the model is unavailable, Ada falls back to the rules. Set `ADA_LLM_MODEL` to change models: `qwen2.5:3b` is the default, `qwen2.5:7b` suits larger servers.

### CI (`.github/workflows/ada.yml`)
- pytest, `alembic check`, Bandit, pip-audit and Semgrep
- Playwright E2E (POS, offline sync, chat, dashboard, settings, offline app shell)
- A real Ollama model classifying Arabic dialects and English
- The signed APK build
- On an `ada-v*` tag, a GitHub release with the APK attached

See [SECURITY.md](SECURITY.md) for the threat model and protections.
