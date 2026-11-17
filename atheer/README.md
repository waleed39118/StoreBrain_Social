# أثير · Atheer

**مساعد ذكي للعيادات الطبية · Smart Medical Clinic Assistant**

[العربية](#العربية) · [English](#english)

---

<div dir="rtl">

## العربية

**أثير** موظف استقبال ومساعد إداري افتراضي للعيادات والمستشفيات. يتحدث العربية والإنجليزية، ويتعامل مع المراجعين بالصوت والكتابة معًا، ويدير المواعيد وقائمة الانتظار، ويجري الحسابات الطبية والمالية، ويحدّث محتواه تلقائيًا وبأمان.

### المزايا

| الميزة | الوصف |
|---|---|
| **الصوت والكتابة** | تحويل الكلام إلى نص بـ faster-whisper ونطق الردود بـ Piper، ويعمل كلاهما محليًا دون إنترنت. يستقبل الكلام والكتابة في الوقت نفسه. |
| **المواعيد** | يمنع الحجز المزدوج، ويتحقق من مناوبات الأطباء، ويدير حالات الموعد (حضور، بدء، انتهاء، إلغاء، عدم حضور)، ويرسل التذكيرات. |
| **التنبيهات الاستباقية** | ينبّه الموظفين عند وصول كبار الشخصيات، وعند تأخر المواعيد، وعند وجود تعارض في الجدول. |
| **قائمة الانتظار** | أرقام دور تبدأ من جديد كل يوم، ونداء بالعربية والإنجليزية برقم الدور والغرفة فقط، وتقدير وقت الانتظار. |
| **الحسابات** | التحقق من الجرعات، ومساحة سطح الجسم، ووظائف الكلى (Cockcroft–Gault)، وتوزيع التكلفة بين المريض والتأمين (مبلغ ثابت، تحمّل، نسبة مشاركة، حد أقصى، ضريبة)، ومخزون المستلزمات. |
| **التحديث الذاتي** | حزم محتوى موقّعة رقميًا (مصطلحات، نماذج صوت)، مع تحقق من سلامة كل ملف، ورفض الإصدارات الأقدم، واستبدال فوري، وإمكانية التراجع. |
| **أداة الإدارة** | إضافة الأطباء ومناوباتهم والمرضى، والحجز، وعرض التنبيهات والتذكيرات، وتجهيز حزم التحديث. |

### التشغيل السريع

يحتاج **Python 3.11** أو أحدث. للتفاصيل الكاملة على ويندوز وماك ولينكس راجع **[INSTALL_AR.md](INSTALL_AR.md)**.

</div>

```bash
cd atheer
python -m venv .venv
.venv\Scripts\activate             # Windows
source .venv/bin/activate          # macOS / Linux
pip install -e ".[dev]"
cp .env.example .env               # Windows: copy .env.example .env
pytest                             # 40 passed
atheer-admin seed-demo
atheer
```

<div dir="rtl">

بعد تشغيل `atheer` اكتب مثلًا: `مرحبا`، `أريد تذكرة`، `كم الانتظار للرقم 2`، `مواعيد الدكتور 1 غدا`، `نادِ التالي غرفة 3`. للخروج اكتب `خروج`.

### قرارات السلامة والخصوصية

- **الجرعات:** أثير يتحقق من الجرعة ولا يصفها. لا يحتوي على بيانات أدوية؛ الحدود تُدخلها العيادة من دليلها المعتمد، وكل نتيجة تحتاج مراجعة الطبيب.
- **السماعات العامة:** تعلن رقم الدور والغرفة فقط، ولا تعلن اسم المريض أو سبب زيارته.
- **أوامر الموظفين** (مثل نداء التالي وتقارير التأخير) لا تُقبل من ميكروفون الصالة العامة.
- **التحديث الذاتي** للمحتوى فقط، ولا يُنزّل أي كود. تحديثات البرنامج نفسه تمر عبر الاختبار وموافقة شخص مسؤول.
- **الصوت يبقى داخل العيادة**، لأن التعرّف على الكلام والنطق يعملان على الجهاز نفسه.

</div>

---

## English

**Atheer** is a virtual receptionist and administrative assistant for clinics and hospitals. It speaks Arabic and English, handles voice and typed input at the same time, manages appointments and the waiting queue, runs medical and billing calculations, and updates its content safely.

### Features

| Feature | Description |
|---|---|
| **Voice & text** | faster-whisper speech-to-text and Piper text-to-speech, both local and offline. Voice and typed input run concurrently. |
| **Appointments** | Prevents double-booking, checks doctor shifts, runs the appointment lifecycle (check-in, start, complete, cancel, no-show), and sends reminders. |
| **Proactive alerts** | Notifies staff about VIP arrivals, late-running appointments and schedule conflicts. |
| **Queue** | Daily ticket numbers, Arabic and English call-outs that give only the number and room, and wait-time estimates. |
| **Calculations** | Dose verification, body surface area, kidney function (Cockcroft–Gault), patient/insurer cost split (copay, deductible, coinsurance, out-of-pocket cap, VAT) and supply stock levels. |
| **Self-update** | Digitally signed content bundles (terminology, voice models) with per-file integrity checks, downgrade refusal, atomic swap and rollback. |
| **Admin CLI** | Add doctors, shifts and patients, book appointments, view alerts and reminders, and build update bundles. |

### Quick start

Requires **Python 3.11+**. Run the commands above, then type at `You>`, for example `Hello`, `I need a ticket`, `available slots doctor 1 tomorrow` or `call next room 3`. Type `exit` to quit.

#### Voice mode (optional)

```bash
pip install -e ".[voice]"
```

Download an Arabic and an English Piper voice (`.onnx` plus its `.onnx.json`) from https://huggingface.co/rhasspy/piper-voices, then set these in `.env`:

```
ATHEER_VOICE_ENABLED=true
ATHEER_VOICE_MODEL_AR=/path/to/ar_JO-kareem-medium.onnx
ATHEER_VOICE_MODEL_EN=/path/to/en_US-amy-medium.onnx
```

#### Admin commands

```bash
atheer-admin add-doctor --name "Khalid Omar" --specialty Pediatrics --slot 20
atheer-admin add-shift --doctor-id 2 --weekday sun --start 09:00 --end 13:00
atheer-admin add-patient --mrn P-1001 --first Mohammed --last Saleh
atheer-admin book --patient-id 3 --doctor-id 2 --start "2026-11-22 09:00"
atheer-admin list-appointments --date 2026-11-22
atheer-admin alerts
atheer-admin --help
```

### Safety and privacy decisions

- **Doses:** Atheer verifies doses; it never prescribes. No drug data ships with it. Limits come from the clinic's approved formulary, and every result is flagged for clinician review.
- **Public speakers** announce only the ticket number and room, never a patient's name or reason for visit.
- **Staff-only commands** (calling the next patient, late reports) are refused from the public lobby microphone.
- **Self-update** delivers content only, never code. Application updates go through testing and a human-approved release.
- **Audio stays on-premises:** speech recognition and synthesis run on the local machine.

### Project structure

```
atheer/
├── README.md · INSTALL_AR.md · requirements.txt · pyproject.toml · .env.example
├── docs/                ARCHITECTURE.md · schema.sql · PROGRESS.md
├── scripts/             dump_schema.py (regenerates docs/schema.sql)
├── src/atheer/
│   ├── runtime.py       `atheer`: text, voice, speaker and updater loops
│   ├── admin.py         `atheer-admin`: data management, booking, alerts, update signing
│   ├── core/            settings, clock, event bus
│   ├── db/              database models and sessions (SQLite / PostgreSQL)
│   ├── appointments/    booking, lifecycle, reminders, alerts
│   ├── queue/           tickets, call-outs, wait estimates
│   ├── calculations/    dosage, billing, wait time, stock
│   ├── assistant/       bilingual request handling with staff/public gating
│   ├── voice/           microphone, speech-to-text, text-to-speech
│   └── updater/         signed content updates and rollback
└── tests/               40 automated tests
```

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (design), [docs/schema.sql](docs/schema.sql) (database), [docs/PROGRESS.md](docs/PROGRESS.md) (work log).
