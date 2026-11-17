# دليل تشغيل أثير (Atheer) على جهازك

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
يجب أن تظهر النتيجة `40 passed`.

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

## 6) تفعيل الصوت (اختياري، يعمل بدون إنترنت)
```bash
pip install -e ".[voice]"
```
1. حمّل نموذج صوت Piper عربي وآخر إنجليزي (ملفات `.onnx` مع ملفات `.onnx.json` المرافقة لها) من https://huggingface.co/rhasspy/piper-voices
2. أضف في `.env`:
```
ATHEER_VOICE_ENABLED=true
ATHEER_VOICE_MODEL_AR=C:/atheer/voices/ar_JO-kareem-medium.onnx
ATHEER_VOICE_MODEL_EN=C:/atheer/voices/en_US-amy-medium.onnx
ATHEER_STT_MODEL=medium
```
عند أول تشغيل يُحمَّل نموذج Whisper تلقائيًا (حوالي 1.5 جيجابايت للنموذج `medium`). استخدم `small` للأجهزة الأضعف.

## 7) التحديث الذاتي للمحتوى (اختياري)
```bash
atheer-admin update-keygen --out signing-key.pem          # احفظ هذا الملف بأمان ولا تضعه على أجهزة العيادة
atheer-admin update-build --src my-content --version 2026.11.22.1 --base-url https://your-server/atheer --key signing-key.pem --out release
```
ارفع محتويات مجلد `release` إلى خادمك، ثم ضع في `.env` على جهاز العيادة قيمتي `ATHEER_UPDATE_PUBLIC_KEY` و `ATHEER_UPDATE_MANIFEST_URL` اللتين يطبعهما الأمر.

## ملاحظات مهمة
- **حدود الجرعات** تُدخلها العيادة من دليلها الدوائي المعتمد، ويجب أن يراجع الطبيب كل نتيجة.
- **السماعات العامة** تعلن رقم الدور والغرفة فقط، ولا تعلن اسم المريض أبدًا.
- **للإنتاج مع عدة أجهزة** يُنصح باستخدام PostgreSQL: ثبّت الحزمة بالأمر `pip install -e ".[postgres]"` ثم غيّر `ATHEER_DATABASE_URL`.
