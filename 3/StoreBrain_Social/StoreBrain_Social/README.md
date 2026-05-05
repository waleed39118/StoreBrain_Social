# 🧠 StoreBrain Social — أتمتة التسويق الذكي

> نشر تلقائي على **8 منصات تواصل اجتماعي** بمحتوى مُولَّد بالذكاء الاصطناعي — مخصص لكل منصة وكل دولة.

---

## 🚀 التشغيل السريع

```bash
# 1. تثبيت المتطلبات
pip install -r requirements.txt

# 2. إعداد المفاتيح
cp .env.example .env
# افتح .env وأدخل مفاتيحك

# 3. التشغيل
python main.py
```

---

## 📋 المتطلبات

- Python 3.11 أو أحدث
- متجر Shopify فعّال
- مفتاح Groq AI (مجاني من [console.groq.com](https://console.groq.com))
- مفاتيح المنصات التي تريد النشر عليها

---

## 🗂️ هيكل المشروع

```
StoreBrain_Social/
├── main.py                          # نقطة الانطلاق
├── requirements.txt                 # المكتبات
├── .env.example                     # قالب الإعدادات
├── .gitignore
├── assets/
│   ├── logo.png
│   └── bg.png
├── core/
│   ├── config.py                    # محمّل الإعدادات المركزي
│   ├── exceptions.py                # استثناءات مخصصة
│   └── logger.py                    # نظام التسجيل
├── services/
│   ├── shopify_service.py           # سحب المنتجات
│   ├── ai_content.py                # توليد المحتوى بالذكاء الاصطناعي
│   ├── image_service.py             # تحميل وتوليد الصور
│   ├── campaign_manager.py          # المنسّق الرئيسي
│   └── publishers/
│       ├── base.py                  # الواجهة الأساسية
│       ├── facebook.py              # Facebook Graph API
│       ├── instagram.py             # Instagram Business API
│       ├── telegram.py              # Telegram Bot API
│       ├── pinterest.py             # Pinterest API v5
│       ├── linkedin.py              # LinkedIn API v2
│       ├── twitter.py               # Twitter API v2
│       ├── reddit.py                # Reddit OAuth2
│       └── youtube.py               # YouTube Data API v3
└── gui/
    ├── app.py                       # النافذة الرئيسية
    └── wizard.py                    # معالج الإعداد الأولي
```

---

## 🔑 كيف تحصل على المفاتيح

### Groq AI (مجاني — مطلوب)
1. اذهب إلى [console.groq.com/keys](https://console.groq.com/keys)
2. أنشئ حساباً مجانياً
3. انسخ الـ API Key

### Shopify (مطلوب)
1. من لوحة Shopify: **Settings → Apps → Develop apps**
2. اضغط **Create an app**
3. من **Configuration → Admin API access scopes** فعّل: `read_products, write_products`
4. من **API credentials** انسخ **Admin API access token**

### Facebook + Instagram
1. اذهب إلى [developers.facebook.com](https://developers.facebook.com)
2. أنشئ App → اختر **Business**
3. أضف **Facebook Login** و **Instagram Graph API**
4. من **Graph API Explorer** احصل على Page Access Token

### Telegram
1. افتح Telegram وابحث عن **@BotFather**
2. أرسل `/newbot` واتبع التعليمات
3. انسخ التوكن
4. أضف البوت كـ Admin في قناتك

### Pinterest
1. اذهب إلى [developers.pinterest.com](https://developers.pinterest.com)
2. أنشئ App → احصل على Access Token
3. انسخ Board ID من رابط اللوحة

### LinkedIn
1. اذهب إلى [linkedin.com/developers](https://linkedin.com/developers)
2. أنشئ App → اطلب صلاحية `w_member_social`
3. احصل على Access Token

### Twitter/X
1. اذهب إلى [developer.twitter.com](https://developer.twitter.com)
2. أنشئ Project + App
3. فعّل **Read and Write** permissions
4. انسخ الـ 4 مفاتيح

### Reddit
1. اذهب إلى [reddit.com/prefs/apps](https://reddit.com/prefs/apps)
2. أنشئ **script** app
3. انسخ Client ID و Secret

---

## 🌍 المنصات المدعومة

| المنصة    | API         | الحالة    |
|-----------|-------------|-----------|
| Facebook  | Graph v19   | ✅ مجاني  |
| Instagram | Graph v19   | ✅ مجاني  |
| Telegram  | Bot API     | ✅ مجاني  |
| Pinterest | API v5      | ✅ مجاني  |
| LinkedIn  | API v2      | ✅ مجاني  |
| Twitter/X | API v2      | 💰 مدفوع  |
| Reddit    | OAuth2      | ✅ مجاني  |
| YouTube   | Data API v3 | ✅ مجاني  |

---

## 🛡️ الأمان

- ملف `.env` لا يُرفع على GitHub أبداً (مُدرج في `.gitignore`)
- المفاتيح مُشفَّرة في السجلات (أول 4 أحرف فقط تظهر)
- كل مستخدم يستخدم مفاتيحه الخاصة

---

## 📅 أفضل أوقات النشر

| الدولة    | الأوقات (UTC)      | المنصات الأولى         |
|-----------|--------------------|------------------------|
| السعودية  | 06:00, 10:00, 17:00| Instagram, Telegram    |
| مصر       | 07:00, 11:00, 18:00| Facebook, YouTube      |
| أمريكا    | 14:00, 17:00, 21:00| Facebook, Pinterest    |
| أوروبا    | 08:00, 12:00, 16:00| Instagram, LinkedIn    |
