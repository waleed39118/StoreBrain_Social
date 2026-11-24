# دليل تشغيل أثير (Atheer) على جهازك

## الطريقة السهلة (موصى بها للتجربة)

1. ثبّت **Python 3.11 أو أحدث** من https://www.python.org/downloads/ (في ويندوز فعّل خيار *Add Python to PATH* أثناء التثبيت).
2. فك ضغط `atheer.zip`.
3. **التثبيت (مرة واحدة):**
   - **ويندوز:** انقر نقرًا مزدوجًا على `install.bat`.
   - **ماك / لينكس:** افتح الطرفية داخل المجلد ونفّذ `./install.sh`.

   يسألك البرنامج عن إضافة بيانات تجريبية (طبيب ومريضان وموعدان اليوم)؛ أجب بنعم للتجربة. ثم يطبع **مفتاح الطاقم**، وهو محفوظ أيضًا في ملف `.env`.
4. **التشغيل:**
   - **ويندوز:** انقر نقرًا مزدوجًا على `start.bat`.
   - **ماك / لينكس:** نفّذ `./start.sh`.

   تفتح الصفحة الرئيسية في المتصفح تلقائيًا على `http://127.0.0.1:8000/`. أبقِ نافذة التشغيل مفتوحة، وأغلقها لإيقاف أثير.

### الشاشات
| الشاشة | الرابط | لمن |
|---|---|---|
| **لوحة الاستقبال** | `http://127.0.0.1:8000/reception` | للطاقم: نداء المراجعين، والمواعيد، والحجز، وتسجيل الحضور، والتنبيهات. تطلب مفتاح الطاقم مرة واحدة. |
| **شاشة الانتظار** | `http://127.0.0.1:8000/display` | لتلفاز الصالة: الرقم المنادى والغرفة. اضغط «تفعيل الصوت» ليُنادى الرقم بصوت المتصفح. |
| **جهاز تسجيل الحضور** | `http://127.0.0.1:8000/kiosk` | للمراجعين: تسجيل الحضور برقم الموعد ورقم الملف، أو أخذ رقم بدون موعد. |

**جرّب هذا السيناريو:** افتح الشاشات الثلاث في ثلاث نوافذ. من جهاز تسجيل الحضور سجّل حضور الموعد رقم `1` برقم الملف `DEMO-1`. ثم اضغط «نداء التالي» في لوحة الاستقبال، وشاهد الرقم يظهر على شاشة الانتظار.

**لفتح الشاشات من أجهزة أخرى في العيادة** (تلفاز أو جهاز لوحي): غيّر `ATHEER_API_HOST` في `.env` إلى `0.0.0.0`، وافتح الشاشات بعنوان جهاز الخادم في الشبكة، مثل `http://192.168.1.10:8000/display`. استخدم ذلك داخل شبكة العيادة فقط.

---

## الطريقة اليدوية

## 1) المتطلبات
- **Python 3.11 أو أحدث**: من https://www.python.org/downloads/ (في ويندوز فعّل خيار *Add Python to PATH* أثناء التثبيت).

## 2) التثبيت
فك ضغط الملف `atheer.zip`، ثم افتح الطرفية (Terminal / PowerShell) داخل مجلد `atheer`.

**ويندوز (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

**ماك / لينكس:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

افتح ملف `.env` وعدّل اسم العيادة والمنطقة الزمنية (مثال: `Asia/Riyadh`).

## 3) التأكد من سلامة التثبيت
```bash
pytest
```
يجب أن تظهر النتيجة `76 passed`.

## 4) إدخال البيانات
```bash
atheer-admin seed-demo                                   # بيانات تجريبية (اختياري)
atheer-admin add-doctor --name "Khalid Omar" --specialty "Pediatrics" --slot 20
atheer-admin add-shift --doctor-id 2 --weekday sun --start 09:00 --end 13:00
atheer-admin add-patient --mrn P-1001 --first Mohammed --last Saleh --phone 0500000000
atheer-admin book --patient-id 3 --doctor-id 2 --start "2026-11-22 09:00"
atheer-admin list-doctors
atheer-admin list-appointments --date 2026-11-22
atheer-admin alerts
atheer-admin --help
```

## 5) تشغيل المساعد
```bash
atheer
```
اكتب بعد `You>` (بالعربية أو الإنجليزية)، مثل: `مرحبا` أو `أريد تذكرة` أو `كم الانتظار للرقم 2` أو `مواعيد الدكتور 1 غدا` أو `نادِ التالي غرفة 3`. وللخروج اكتب `خروج`.

## 6) تشغيل الخادم (واجهة API)
1. أنشئ مفتاحًا لطاقم العيادة:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
2. ضع المفتاح الناتج في `.env`:
```
ATHEER_STAFF_API_KEY=المفتاح_الناتج
```
3. شغّل الخادم:
```bash
atheer-server
```
4. افتح في المتصفح `http://127.0.0.1:8000/docs` لتجربة كل الواجهات. لاستخدام واجهات الطاقم اضغط **Authorize** أو أرسل المفتاح في الترويسة `X-API-Key`.

بدون المفتاح تبقى واجهات الطاقم معطّلة، وتعمل الواجهات العامة فقط (المحادثة، وتسجيل الحضور، وأرقام الدور).

## 7) تفعيل الصوت (اختياري، يعمل بدون إنترنت)
```bash
pip install -e ".[voice]"
```
أضف في `.env`:
```
ATHEER_VOICE_ENABLED=true
ATHEER_TTS_ENGINE=pyttsx3
ATHEER_STT_MODEL=medium
```
- **pyttsx3** يستخدم أصوات نظام التشغيل مباشرة دون تنزيل أي نموذج. في ويندوز ثبّت **حزمة اللغة العربية** (الإعدادات ← الوقت واللغة ← اللغة ← إضافة العربية مع خيار تحويل النص إلى كلام) ليظهر صوت عربي مثل Naayf أو Hoda.
- **لصوت أكثر طبيعية** استخدم Piper: حمّل نموذج صوت عربي وآخر إنجليزي (ملفات `.onnx` مع ملفات `.onnx.json` المرافقة) من https://huggingface.co/rhasspy/piper-voices ثم اضبط:
```
ATHEER_TTS_ENGINE=piper
ATHEER_VOICE_MODEL_AR=C:/atheer/voices/ar_JO-kareem-medium.onnx
ATHEER_VOICE_MODEL_EN=C:/atheer/voices/en_US-amy-medium.onnx
```
- عند أول تشغيل يُحمَّل نموذج Whisper تلقائيًا (حوالي 1.5 جيجابايت للنموذج `medium`). استخدم `small` للأجهزة الأضعف.

## 8) التحديث الذاتي للمحتوى (اختياري)
```bash
atheer-admin update-keygen --out signing-key.pem          # احفظ هذا الملف بأمان ولا تضعه على أجهزة العيادة
atheer-admin update-build --src my-content --version 2026.11.22.1 --base-url https://your-server/atheer --key signing-key.pem --out release
```
ارفع محتويات مجلد `release` إلى خادمك، ثم ضع في `.env` على جهاز العيادة قيمتي `ATHEER_UPDATE_PUBLIC_KEY` و `ATHEER_UPDATE_MANIFEST_URL` اللتين يطبعهما الأمر.

يمكن أن يحتوي مجلد المحتوى على:
- `terminology/*.json`: مصطلحات طبية، مثل `{"BP": {"ar": "ضغط الدم", "en": "Blood pressure"}}`
- `formulary.json`: دليل الجرعات المعتمد في العيادة، مثل `[{"drug_name": "...", "min_mg_per_kg": 10, "max_mg_per_kg": 15, "max_single_dose_mg": 1000}]`

يُفعَّل المحتوى الجديد فورًا دون إعادة تشغيل. وإذا فشل تحميله يعود أثير تلقائيًا إلى النسخة السابقة.

## 9) الترخيص (للمورّد فقط)
هذه الخطوات تنفّذها أنت على جهازك، وليس على جهاز العيادة.

**مرة واحدة فقط:** أنشئ مفتاح التوقيع الخاص بك.
```bash
atheer-admin license-keygen --out vendor-license-key.pem
```
احفظ ملف `vendor-license-key.pem` بأمان واعمل له نسخة احتياطية، ولا تعطه لأي عميل. سيطبع الأمر سطرًا يبدأ بـ `VENDOR_PUBLIC_KEY`؛ ضعه في الملف `src/atheer/licensing/vendor_key.py` قبل تجهيز نسخ العملاء.

**لكل عيادة ولكل تجديد:** أصدر ملف الترخيص.
```bash
atheer-admin license-issue --key vendor-license-key.pem --customer "عيادة النور" --plan clinic --days 365 --max-doctors 2 --out license.json
```
انسخ `license.json` إلى مجلد أثير في جهاز العيادة. للتحقق من حالة الترخيص هناك:
```bash
atheer-admin license-status
```

- قبل انتهاء الاشتراك بـ 14 يومًا تظهر تنبيهات للطاقم.
- بعد الانتهاء يستمر العمل 14 يومًا (فترة سماح)، ثم تتوقف الأعمال اليومية برسالة واضحة.
- التجديد: ضع ملف الترخيص الجديد مكان القديم، دون إعادة تشغيل.

## ملاحظات مهمة
- **حدود الجرعات** تُدخلها العيادة من دليلها الدوائي المعتمد، ويجب أن يراجع الطبيب كل نتيجة.
- **السماعات العامة** تعلن رقم الدور والغرفة فقط. أما الترحيب عند تسجيل الحضور فبالاسم الأول فقط، ويمكن إيقافه بالإعداد `ATHEER_GREET_BY_NAME=false`.
- **الخادم يستمع على هذا الجهاز فقط** (`127.0.0.1`). لفتحه لأجهزة أخرى في العيادة استخدم HTTPS عبر خادم وسيط، ولا تكشفه على الإنترنت مباشرة.
- **للإنتاج مع عدة أجهزة** يُنصح باستخدام PostgreSQL: ثبّت الحزمة بالأمر `pip install -e ".[postgres]"` ثم غيّر `ATHEER_DATABASE_URL`.
