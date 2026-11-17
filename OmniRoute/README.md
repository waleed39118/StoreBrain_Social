# OmniRoute

[English](#english) | [العربية](#العربية)

---

## English

A standalone folder for running **OmniRoute**. It is not integrated with StoreBrain_Social, and no part of StoreBrain_Social depends on it.

- Official source: <https://github.com/cheaper-inference/OmniRoute>
- License: MIT
- Pinned version: `3.8.54` (Docker image: `diegosouzapw/omniroute`)

### What is it?
A gateway that exposes a single OpenAI-compatible API endpoint and routes requests to many AI model providers, with automatic fallback on failure, plus a web dashboard.

### Why isn't the source code included?
The project is very large (about 29,000 files). Copying it into this repository would bloat it and make updates hard. It runs from the official Docker image at a pinned version instead.

### Files
| File | Purpose |
| --- | --- |
| `docker-compose.yml` | Runs the official image, pinned and hardened |
| `.env.example` | Template for the required secrets |
| `.gitignore` | Keeps `.env` and `data/` out of git |
| `README.md` | This file |

### Setup
Requirements: Docker and Docker Compose.

```bash
cd OmniRoute
cp .env.example .env
```

Fill in `JWT_SECRET` with the output of:

```bash
openssl rand -base64 48
```

Fill in `API_KEY_SECRET` with the output of:

```bash
openssl rand -hex 32
```

On Windows without `openssl`, use Python instead (run once for each secret):

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Start it:

```bash
docker compose up -d
```

Check that it is running (the image has a built-in health check; wait until the status shows `healthy`):

```bash
docker compose ps
```

Open the dashboard: <http://127.0.0.1:20128>

### Using the API
After adding a provider and creating an OmniRoute API key in the dashboard, point any OpenAI-compatible client at:

- Base URL: `http://127.0.0.1:20128/v1`
- API key: the key created in the dashboard (not a provider key)

Stop it:

```bash
docker compose down
```

### Security settings in `docker-compose.yml`
| Setting | Reason |
| --- | --- |
| Bound to `127.0.0.1` only | The dashboard and API are not reachable from other devices on the network |
| Pinned version instead of `latest` | The version never changes without you knowing |
| `cap_drop: ALL` and `no-new-privileges` | The container has no extra system privileges |
| Runs inside Docker | MITM mode cannot install a root certificate or edit `/etc/hosts` on your machine |

### ⚠️ Warnings — read before use
1. **Do not enable MITM mode** directly on your machine (outside Docker). It installs a root certificate and edits `/etc/hosts` with `sudo`, which lets it decrypt network traffic.
2. **Avoid "free models" that rely on impersonating other tools** or reusing subscription tokens. They violate provider terms, can get your accounts banned, and may stop working at any time. Use official API keys from your own accounts.
3. **Every request and API key passes through this gateway.** Do not expose it to the internet, and do not use copies from unofficial repositories (such as `free_omiroute`).
4. Never commit the `.env` file (it is excluded in `.gitignore`).

### Updating
1. Read `CHANGELOG.md` in the official repository.
2. Change the version number in `docker-compose.yml`.
3. Run:

```bash
docker compose pull && docker compose up -d
```

---

<div dir="rtl">

## العربية

مجلد مستقل لتشغيل **OmniRoute**. غير مدمج مع StoreBrain_Social، ولا يعتمد عليه أي جزء منه.

- المصدر الرسمي: <https://github.com/cheaper-inference/OmniRoute>
- الرخصة: MIT
- النسخة المثبّتة: `3.8.54` (صورة Docker: `diegosouzapw/omniroute`)

### ما هو؟
بوابة (Gateway) تعرض عنوان API واحداً متوافقاً مع OpenAI، وتوزّع الطلبات على مزوّدين كثيرين لنماذج الذكاء الاصطناعي، مع انتقال تلقائي عند الفشل، ومعها لوحة تحكم ويب.

### لماذا لا يُحفظ الكود المصدري هنا؟
المشروع ضخم (حوالي 29 ألف ملف). نسخه داخل هذا المستودع يضخّمه ويجعل تحديثه صعباً. لذلك يُشغَّل من صورة Docker الرسمية بنسخة مثبّتة.

### الملفات
| الملف | الغرض |
| --- | --- |
| `docker-compose.yml` | تشغيل الصورة الرسمية بنسخة مثبّتة وإعدادات أمان |
| `.env.example` | قالب المفاتيح السرية المطلوبة |
| `.gitignore` | يمنع رفع `.env` و`data/` إلى git |
| `README.md` | هذا الملف |

### التشغيل
المتطلبات: Docker و Docker Compose.

</div>

```bash
cd OmniRoute
cp .env.example .env
```

<div dir="rtl">

ضع في `JWT_SECRET` ناتج الأمر:

</div>

```bash
openssl rand -base64 48
```

<div dir="rtl">

وضع في `API_KEY_SECRET` ناتج الأمر:

</div>

```bash
openssl rand -hex 32
```

<div dir="rtl">

على Windows إذا لم يكن `openssl` متوفراً، استخدم Python بدلاً منه (نفّذه مرة لكل مفتاح):

</div>

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

<div dir="rtl">

ثم شغّل:

</div>

```bash
docker compose up -d
```

<div dir="rtl">

تأكد أنه يعمل (الصورة فيها فحص صحة مدمج؛ انتظر حتى تظهر الحالة `healthy`):

</div>

```bash
docker compose ps
```

<div dir="rtl">

افتح لوحة التحكم: <http://127.0.0.1:20128>

### استخدام الـ API
بعد إضافة مزوّد وإنشاء مفتاح API خاص بـ OmniRoute من لوحة التحكم، وجّه أي برنامج متوافق مع OpenAI إلى:

- العنوان الأساسي: `http://127.0.0.1:20128/v1`
- مفتاح API: المفتاح الذي أنشأته في اللوحة (وليس مفتاح المزوّد)

الإيقاف:

</div>

```bash
docker compose down
```

<div dir="rtl">

### إعدادات الأمان في `docker-compose.yml`
| الإعداد | السبب |
| --- | --- |
| الربط على `127.0.0.1` فقط | اللوحة والـ API لا تظهر لأي جهاز آخر على الشبكة |
| نسخة مثبّتة بدل `latest` | لا تتغير النسخة دون علمك |
| `cap_drop: ALL` و `no-new-privileges` | الحاوية بلا صلاحيات نظام إضافية |
| التشغيل داخل Docker | ميزة MITM لا تستطيع تثبيت شهادة جذرية أو تعديل `/etc/hosts` على جهازك |

### ⚠️ تحذيرات — اقرأها قبل الاستخدام
1. **لا تفعّل وضع MITM** على جهازك مباشرة (خارج Docker). يثبّت شهادة جذرية في النظام ويعدّل `/etc/hosts` بصلاحيات `sudo`، ما يسمح بفك تشفير حركة الشبكة.
2. **تجنّب "الموديلات المجانية" المعتمدة على انتحال هوية أدوات أخرى** أو إعادة استخدام توكنات الاشتراكات. تخالف شروط المزوّدين وقد تؤدي لحظر حساباتك، وقد تتوقف في أي لحظة. استخدم مفاتيح API رسمية من حساباتك.
3. **كل الطلبات ومفاتيح API تمر عبر هذه البوابة.** لا تكشفها على الإنترنت، ولا تستخدم نسخاً من مستودعات غير رسمية (مثل `free_omiroute`).
4. لا ترفع ملف `.env` إلى git (مستثنى في `.gitignore`).

### التحديث
1. راجع `CHANGELOG.md` في المستودع الرسمي.
2. غيّر رقم النسخة في `docker-compose.yml`.
3. نفّذ:

</div>

```bash
docker compose pull && docker compose up -d
```
