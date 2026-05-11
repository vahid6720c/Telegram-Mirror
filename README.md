<div align="center">

<img src="https://img.shields.io/badge/version-2.0-blue?style=flat-square" alt="version"/>

# 📡 TELEGRAM MIRROR

### کانال‌های تلگرام را بدون فیلتر، مستقیم از GitHub بخوانید

[![GitHub Actions](https://img.shields.io/badge/Powered%20by-GitHub%20Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)
[![فارسی](https://img.shields.io/badge/زبان-فارسی-dc2626?style=for-the-badge)](README.md)

**بدون VPN · بدون نصب · بدون API Token**

</div>

---

## 🧠 چطور کار می‌کنه؟

یه GitHub Action داری که هر وقت بخوای اجراش کنی — نام کانال تلگرام رو بهش میدی، اون پیام‌ها و عکس‌ها رو می‌گیره و به شکل یه فایل Markdown داخل مخزن ذخیره می‌کنه. بعدش مستقیم از `github.com` قابل خوندنه.

```
تلگرام  ──►  GitHub Action  ──►  فایل .md داخل مخزن  ──►  کاربر روی github.com می‌خونه
```

---

## ✨ قابلیت‌ها

- 📨 دریافت تا **۲۰۰ پیام** از هر کانال عمومی
- 🖼 نمایش **عکس و آلبوم** مستقیم داخل صفحه
- 📊 نمایش **نظرسنجی‌ها**
- ↪ نمایش **پیام‌های فوروارد شده**
- 📄 نمایش **فایل‌ها و اسناد**
- 👁 نمایش **تعداد بازدید** و تاریخ هر پیام
- ⚡ بدون نیاز به هیچ‌گونه توکن یا ربات

---

## 🚀 راه‌اندازی (یک‌بار، ۲ دقیقه)

### ۱. Fork کردن مخزن

روی دکمه **Fork** در بالای صفحه کلیک کنید.

### ۲. دادن مجوز به Actions

وارد مخزن Fork شده‌تان بشید و برید به:

```
Settings → Actions → General → Workflow permissions
```

گزینه **Read and write permissions** را انتخاب و ذخیره کنید.

### ۳. تمام! حالا استفاده کنید ↓

---

## 📖 استفاده

به تب **Actions** مخزن خود بروید:

1. روی **📡 Fetch Telegram Channel** کلیک کنید
2. روی **Run workflow** کلیک کنید
3. نام کانال را **بدون @** وارد کنید



4. تعداد پیام را وارد کنید (پیش‌فرض: ۱۰۰)
5. **Run workflow** را بزنید

پس از چند ثانیه، فایل داخل پوشه `channels/` در مخزن ذخیره می‌شود و از همانجا قابل خواندن است.

---

## 📁 ساختار مخزن

```
telegram-reader/
├── .github/
│   └── workflows/
│       └── fetch.yml          ← GitHub Action اصلی
├── scripts/
│   └── fetch_channel.py       ← اسکریپت دریافت پیام‌ها
├── channels/
│   └── channel_username_2026-...md  ← فایل‌های ذخیره‌شده کانال‌ها
└── README.md
```

---

## ⚙️ پارامترها

| پارامتر | مقدار پیش‌فرض | توضیح |
|:-------:|:------------:|:------|
| `channel` | — | نام کانال بدون `@` (اجباری) |
| `count` | `100` | تعداد پیام — بین ۱۰ تا ۲۰۰ |

---

## ⚠️ محدودیت‌ها

- فقط کانال‌های **عمومی** تلگرام پشتیبانی می‌شوند
- ویدیوها به دلیل محدودیت‌های CDN تلگرام نمایش داده نمی‌شوند — فقط لینک دانلود دارند
- GitHub برای مخازن عمومی محدودیت حجم دارد — پوشه `channels/` را گاهی پاک‌سازی کنید

---

## 📄 لایسنس

MIT License — آزاد برای استفاده شخصی

---

<div align="center">

ساخته شده با ❤️

---

اگه این پروژه برات مفید بود، با یه ⭐ حمایت کن — انگیزه ادامه دادنمه!

[![Star on GitHub](https://img.shields.io/github/stars/FALKON-CODE/Telegram-Mirror?style=social)](https://github.com/FALKON-CODE/Telegram-Mirror)

</div>
