# أثير · Atheer

**مساعد ذكي للعيادات الطبية · Smart Medical Clinic Assistant**

[العربية](#العربية) · [English](#english)

---

<div dir="rtl">

## العربية

**أثير** موظف استقبال ومساعد إداري افتراضي للعيادات والمستشفيات. يتحدث العربية والإنجليزية، ويتعامل مع المراجعين بالصوت والكتابة معًا. يستقبلهم بأسمائهم، وينادي أرقام الدور، ويدير المواعيد، ويجري الحسابات الطبية والمالية، ويحدّث محتواه تلقائيًا دون توقف.

### المكوّنات الأساسية

| المكوّن | دوره |
|---|---|
| **VoiceEngine** | محرك الصوت: تحويل الكلام إلى نص بـ Whisper (faster-whisper أو OpenAI Whisper)، ونطق الردود بـ pyttsx3 (أصوات النظام) أو Piper (أصوات طبيعية). يعمل دون إنترنت، وينطق الجمل بالترتيب دون تداخل. |
| **SecretaryCore** | السكرتير: تسجيل حضور المريض والترحيب به باسمه الأول، وإصدار أرقام الدور ومناداتها، والإعلان عن وصول الأطباء ومغادرتهم، وحجز المواعيد وكشف التعارضات. |
| **CalcEngine** | محرك الحسابات: التحقق من الجرعات حسب دليل العيادة الدوائي، ومساحة سطح الجسم، ووظائف الكلى، وتوزيع التكلفة بين المريض والتأمين، ومخزون المستلزمات، ووقت الانتظار. |
| **AutoUpdater** | التحديث الذاتي: تنزيل حزم محتوى موقّعة رقميًا (مصطلحات طبية، دليل دوائي، نماذج صوت) وتفعيلها فورًا دون إعادة تشغيل، مع التراجع التلقائي إذا فشلت. |
| **واجهة API** | خادم FastAPI مع Uvicorn: واجهات REST وWebSocket، وصفحة توثيق تفاعلية على `/docs`، ومفتاح خاص لطاقم العيادة. |

### التشغيل السريع

يحتاج **Python 3.11** أو أحدث. الطريقة الأسهل: شغّل `install.bat` ثم `start.bat` في ويندوز، أو `./install.sh` ثم `./start.sh` في ماك ولينكس. تفتح الصفحة الرئيسية في المتصفح تلقائيًا. التفاصيل في **[INSTALL_AR.md](INSTALL_AR.md)**.

### الشاشات المدمجة

- **لوحة الاستقبال** (`/reception`): للطاقم. نداء المراجعين، ومواعيد اليوم، والحجز، وإضافة المرضى، وتسجيل الحضور، والتنبيهات.
- **شاشة الانتظار** (`/display`): لتلفاز الصالة. الرقم المنادى والغرفة، مع نداء صوتي من المتصفح.
- **جهاز تسجيل الحضور** (`/kiosk`): للمراجعين، بالعربية والإنجليزية.

تعمل الشاشات دون إنترنت، وتعرض الأوقات بتوقيت العيادة.

الطريقة اليدوية:

</div>

```bash
cd atheer
python -m venv .venv
.venv\Scripts\activate             # Windows
source .venv/bin/activate          # macOS / Linux
pip install -e ".[dev]"
cp .env.example .env               # Windows: copy .env.example .env
pytest                             # 76 passed
atheer-admin seed-demo
atheer                             # staff console
atheer-server                      # screens: http://127.0.0.1:8000/  ·  API docs: /docs
```

<div dir="rtl">

### طرق الاستخدام

- **الطرفية (`atheer`):** لطاقم الاستقبال. اكتب مثلًا: `مرحبا`، `أريد تذكرة`، `كم الانتظار للرقم 2`، `مواعيد الدكتور 1 غدا`، `نادِ التالي غرفة 3`. للخروج اكتب `خروج`.
- **الخادم (`atheer-server`):** يشغّل الشاشات المدمجة على `http://127.0.0.1:8000/`، وواجهة الربط مع أنظمة العيادة الأخرى (توثيقها على `/docs`).
- **أداة الإدارة (`atheer-admin`):** لإضافة الأطباء ومناوباتهم والمرضى، والحجز، وعرض التنبيهات، وتجهيز حزم التحديث.

### قرارات السلامة والخصوصية

- **الجرعات:** أثير يتحقق من الجرعة ولا يصفها. لا يحتوي على بيانات أدوية؛ الحدود تأتي من دليل العيادة المعتمد (`formulary.json`)، وكل نتيجة تحتاج مراجعة الطبيب.
- **الترحيب بالاسم:** بالاسم الأول فقط عند تسجيل الحضور، ويمكن إيقافه بالإعداد `ATHEER_GREET_BY_NAME=false`. أما نداء الدور على السماعات فبالرقم والغرفة فقط، دون اسم أو سبب زيارة.
- **تسجيل الحضور:** يتطلب رقم الموعد مع رقم الملف الطبي، ويُوقف الجهاز بعد 5 محاولات خاطئة خلال 5 دقائق.
- **أوامر الطاقم:** نداء التالي، والحجز، والحسابات، والتنبيهات تتطلب المفتاح `X-API-Key`، وهي معطّلة تمامًا حتى يُضبط المفتاح. ولا تُقبل من ميكروفون الصالة العامة.
- **التحديث الذاتي للمحتوى فقط:** لا يُنزّل أي كود. كل حزمة موقّعة رقميًا ومفحوصة ملفًا ملفًا. تحديثات البرنامج نفسه تمر عبر الاختبار وموافقة شخص مسؤول.
- **الصوت يبقى داخل العيادة:** التعرّف على الكلام والنطق يعملان على الجهاز نفسه.
- **الخادم يستمع محليًا افتراضيًا** (`127.0.0.1`). لفتحه على الشبكة استخدم HTTPS عبر خادم وسيط.

### الترخيص والاشتراك

لكل عيادة ملف ترخيص `license.json` يوقّعه المورّد رقميًا، ويحدد اسم العيادة والباقة وعدد الأطباء المسموح وتاريخ الانتهاء. يُتحقَّق منه على جهاز العيادة دون إنترنت.

- **قبل الانتهاء بـ 14 يومًا** تظهر تنبيهات للطاقم.
- **بعد الانتهاء** يستمر العمل 14 يومًا (فترة سماح) مع تنبيهات.
- **بعد فترة السماح** تتوقف الأعمال اليومية (الحجز، وتسجيل الحضور، وأرقام الدور) برسالة واضحة. يبقى ممكنًا إنهاء الزيارات الجارية ورؤية حالة النظام.
- **التجديد دون إعادة تشغيل:** يكفي وضع ملف الترخيص الجديد مكان القديم.
- نسخة التطوير (دون مفتاح مورّد مدمج) لا تطلب ترخيصًا.

</div>

---

## English

**Atheer** is a virtual receptionist and administrative assistant for clinics and hospitals. It speaks Arabic and English, handles voice and typed input at the same time, greets patients by name, calls queue numbers, manages appointments, runs medical and billing calculations, and updates its content without downtime.

### Core components

| Component | Role |
|---|---|
| **VoiceEngine** | Speech-to-text with Whisper (faster-whisper or OpenAI Whisper) and text-to-speech with pyttsx3 (system voices) or Piper (natural neural voices). Fully offline; one ordered speaker queue so announcements never overlap. |
| **SecretaryCore** | Patient check-in with a first-name greeting, queue tickets and call-outs, doctor arrival/departure announcements, booking and conflict detection. |
| **CalcEngine** | Dose verification against the clinic formulary, body surface area, kidney function, patient/insurer cost split, supply stock levels and wait time. |
| **AutoUpdater** | Downloads digitally signed content bundles (terminology, formulary, voice models) and activates them without a restart, rolling back automatically if a release fails to load. |
| **API** | FastAPI + Uvicorn: REST and WebSocket endpoints, interactive docs at `/docs`, and a staff API key. |

### Quick start

Requires **Python 3.11+**. Easiest: run `install.bat` then `start.bat` on Windows, or `./install.sh` then `./start.sh` on macOS/Linux; the home page opens in the browser. Or run the manual commands above.

### Built-in screens

- **Reception panel** (`/reception`) for staff: call patients, today's appointments, booking, adding patients, check-in and alerts.
- **Waiting-room display** (`/display`) for the lobby TV: the called number and room, with optional browser speech.
- **Check-in kiosk** (`/kiosk`) for patients, in Arabic and English.

The screens need no internet and show times in the clinic's time zone.

- **Console (`atheer`)** for reception staff. Try `Hello`, `I need a ticket`, `available slots doctor 1 tomorrow` or `call next room 3`; `exit` quits.
- **Server (`atheer-server`)** serves the built-in screens at `http://127.0.0.1:8000/` and the integration API for other clinic systems (documented at `/docs`).
- **Admin CLI (`atheer-admin`)** to add doctors, shifts and patients, book appointments, view alerts and build update bundles. Run `atheer-admin --help` for all commands.

### API overview

| Access | Endpoints |
|---|---|
| Public (kiosk, lobby) | `GET /health` · `POST /chat` · `WS /ws/chat` · `POST /voice/transcribe` · `POST /checkin` · `POST /queue/tickets` · `GET /queue/tickets/{id}/wait` · `GET /doctors/{id}/slots` · `GET /terminology/{term}` |
| Staff (`X-API-Key`) | `POST /appointments` · `POST /appointments/reschedule` · `POST /appointments/{id}/status` · `GET /alerts` · `GET /reminders` · `GET /queue` · `POST /queue/call-next` · `POST /queue/tickets/{id}/{recall\|serve\|finish\|skip\|requeue}` · `POST /doctors/{id}/presence` · `/calc/*` · `/updates/*` |

### Voice setup (optional)

```bash
pip install -e ".[voice]"
```

```
ATHEER_VOICE_ENABLED=true
ATHEER_TTS_ENGINE=pyttsx3          # or piper / auto / console
ATHEER_STT_ENGINE=faster-whisper   # or openai-whisper (pip install -e ".[whisper]")
ATHEER_STT_MODEL=medium            # small for slower machines
```

pyttsx3 uses the operating system's voices: on Windows, install the Arabic language pack to get an Arabic voice. For more natural speech, download Piper voices from https://huggingface.co/rhasspy/piper-voices and set `ATHEER_VOICE_MODEL_AR` / `ATHEER_VOICE_MODEL_EN`.

### Safety and privacy decisions

- **Doses:** Atheer verifies doses; it never prescribes. No drug data ships with it. Limits come from the clinic's approved formulary (`formulary.json`), and every result is flagged for clinician review.
- **Greeting by name** uses the first name only, at check-in, and can be turned off with `ATHEER_GREET_BY_NAME=false`. Queue call-outs on the speakers give only the number and room, never a name or reason for visit.
- **Check-in** requires the appointment number plus the medical record number, and a device is blocked after 5 failed attempts in 5 minutes.
- **Staff actions** (calling patients, booking, calculations, alerts) need the `X-API-Key` header, are disabled until a key is configured, and are refused from the public lobby microphone.
- **Self-update is content only**, never code. Every bundle is signed and checked file by file. Application updates go through testing and a human-approved release.
- **Audio stays on-premises:** speech recognition and synthesis run on the local machine.
- **The server binds to `127.0.0.1` by default.** To expose it on the network, put it behind HTTPS with a reverse proxy.

### Licensing and subscriptions

Each clinic gets a `license.json` signed by the vendor (customer, plan, doctor limit, expiry), verified offline on the clinic machine.

- **14 days before expiry**, staff see warnings.
- **After expiry**, a 14-day grace period keeps the clinic running, with warnings.
- **After the grace period**, day-to-day operations (booking, check-in, queue tickets) are refused with a clear message (HTTP 402). Visits already under way can still be completed, and `/health` stays available.
- **Renewal needs no restart:** replace `license.json`.
- Development builds (no vendor key built in) are not license-checked.

Vendor workflow: `atheer-admin license-keygen` once (paste the printed public key into `src/atheer/licensing/vendor_key.py`), then `atheer-admin license-issue` per clinic and renewal. This backs the subscription contract; whoever can edit the Python source can remove it, so the contract remains the primary protection.

### Project structure

```
atheer/
├── README.md · INSTALL_AR.md · requirements.txt · pyproject.toml · .env.example
├── install.bat · start.bat · install.sh · start.sh   one-click install and start
├── docs/                ARCHITECTURE.md · schema.sql · PROGRESS.md
├── scripts/             dump_schema.py (regenerates docs/schema.sql)
├── src/atheer/
│   ├── runtime.py       builds all components; `atheer` console
│   ├── secretary.py     SecretaryCore
│   ├── admin.py         `atheer-admin`
│   ├── api/             FastAPI app, routes, staff auth, rate limiting, web routes (`atheer-server`)
│   ├── web/             reception panel, waiting-room display, check-in kiosk (HTML/CSS/JS, offline)
│   ├── directory.py     doctors and patients lookups
│   ├── voice/           VoiceEngine, Whisper / pyttsx3 / Piper engines, microphone
│   ├── calculations/    CalcEngine, dosage, billing, wait time, stock
│   ├── updater/         AutoUpdater, signed bundles, terminology store
│   ├── licensing/       signed subscription licenses, grace period, doctor limit
│   ├── appointments/    booking, lifecycle, reminders, alerts
│   ├── queue/           tickets, call-outs, wait estimates
│   ├── assistant/       bilingual request handling with staff/public gating
│   ├── db/              SQLAlchemy models and sessions (SQLite / PostgreSQL)
│   └── core/            settings, clock, event bus
└── tests/               76 automated tests
```

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (design), [docs/schema.sql](docs/schema.sql) (database), [docs/PROGRESS.md](docs/PROGRESS.md) (work log).
