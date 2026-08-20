# 📚 Coaching Center Attendance & Guardian Notification Telegram Bot

একটি সম্পূর্ণ Production-Ready Telegram Bot — Class-wise দৈনিক হাজিরা এবং
Absent হলে অভিভাবককে automatic Telegram নোটিফিকেশন।

## ✨ Features

- Class Management (Add / Edit / Activate / Deactivate / Delete)
- Student Management (Add / Edit / Change Class / Mark Inactive / Delete /
  Regenerate Guardian Access Code)
- Class-wise Daily Attendance (Present/Absent টগল, "সবাইকে Present করুন",
  Overwrite confirmation)
- Guardian Auto-Notification on Absence (শুধু Linked guardian-দের কাছে)
- Guardian Self-Linking System (Access Code দিয়ে)
- Teacher sub-admin role (শুধু নিজের assign করা Class-এর হাজিরা)
- Reports: আজকের সামারি, Student History, Class-wise Monthly Sheet, Low
  Attendance List
- Broadcast (সব Linked Guardian-কে মেসেজ)
- Activity Logs
- Atomic attendance save + duplicate-date protection

## 🏗️ Architecture

```
Telegram Bot API
      │
      ▼
python-telegram-bot (async, ConversationHandler-based multi-step flows)
      │
      ▼
handlers/ (nav, admin, attendance, guardian)
      │
      ▼
services/ (attendance_service — atomic save, notification_service — guardian alerts)
      │
      ▼
database/ (SQLAlchemy async ORM models + session factory)
      │
      ▼
SQLite (local/dev) বা PostgreSQL/Neon (production)
```

**মূল ডিজাইন সিদ্ধান্ত:**
- মূল নেভিগেশন সবসময় **Reply Keyboard**-এ (Classes/Students/Attendance/...),
  কারণ এগুলো id-নির্ভর নয় এবং সবসময় visible থাকা দরকার।
- Item-ভিত্তিক সিলেকশন (নির্দিষ্ট Class/Student/Teacher, pagination,
  confirm/cancel) সব **Inline Keyboard**-এ, কারণ প্রতিটার পেছনে ডাটাবেস আইডি
  বহন করতে হয়।
- Multi-step ফর্ম (Add Class/Student/Teacher, Take Attendance,
  Guardian Linking) `ConversationHandler` দিয়ে বানানো, প্রতিটা ধাপে
  `❌ Cancel` করার সুযোগসহ।
- Attendance Submit **atomic transaction** — সব entry একসাথে সেভ হয় অথবা
  কিছুই হয় না। Notification পাঠানো হয় সেভের *পরে*, যাতে notification
  ব্যর্থ হলেও attendance সেভ আটকে না যায়।

## 🗄️ Database Schema

`database/models.py`-এ সংজ্ঞায়িত (SQLAlchemy async ORM):

- `classes` — id, name, schedule_note, is_active, created_at
- `students` — id, class_id (FK), name, roll_number, guardian_phone, address,
  admission_date, is_active, guardian_access_code (unique), created_at
  — `(class_id, roll_number)` unique constraint
- `teachers` — id (Telegram user id), name, created_at
- `teacher_class_assignments` — teacher_id (FK), class_id (FK)
- `guardians` — id (Telegram user id), created_at
- `guardian_student_links` — guardian_id (FK), student_id (FK), linked_at
- `attendance_records` — id, class_id (FK), attendance_date, created_by,
  created_at, updated_at — `(class_id, attendance_date)` unique constraint
- `attendance_entries` — id, attendance_record_id (FK), student_id (FK),
  status (PRESENT/ABSENT), notified (bool)
- `activity_logs` — id, actor_id, action, details, created_at
- `settings` — key, value

## 📁 Folder Structure

```
project/
├── main.py
├── config.py
├── database/
│   ├── models.py
│   └── database.py
├── handlers/
│   ├── nav.py
│   ├── admin.py
│   ├── attendance.py
│   └── guardian.py
├── keyboards/
│   ├── admin.py
│   └── guardian.py
├── services/
│   ├── attendance_service.py
│   └── notification_service.py
├── utils/
│   ├── helpers.py
│   └── states.py
├── requirements.txt
├── .env.example
└── README.md
```

## ⚙️ Configuration (.env)

`.env.example` কপি করে `.env` বানান এবং পূরণ করুন:

```
BOT_TOKEN=your_bot_token_from_botfather
ADMIN_IDS=111111111,222222222
DATABASE_URL=sqlite+aiosqlite:///./coaching_bot.db
WEBHOOK_BASE_URL=
```

কোনো secret code হার্ড-কোড করা নেই — সবকিছু `.env` থেকে আসে।

## 🚀 Local Setup (Polling Mode)

```bash
cd project
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # এরপর .env এ BOT_TOKEN ও ADMIN_IDS বসান
python main.py
```

`WEBHOOK_BASE_URL` খালি রাখলে বট নিজে থেকেই **polling mode**-এ চলবে —
লোকাল ডেভেলপমেন্টের জন্য এটাই সবচেয়ে সহজ।

## 🌐 Production Deployment (Neon PostgreSQL + Render, Webhook Mode)

1. **Neon-এ ডাটাবেস বানান** → neon.tech এ প্রজেক্ট তৈরি করুন, connection
   string কপি করুন (`postgresql://user:pass@host/dbname` ফরম্যাটে)।
2. **Render-এ নতুন Web Service বানান** → এই রিপো/ফোল্ডার connect করুন।
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`
3. **Environment Variables (Render Dashboard-এ)**:
   ```
   BOT_TOKEN=...
   ADMIN_IDS=...
   DATABASE_URL=postgresql://user:pass@host/dbname   (অটো asyncpg-এ কনভার্ট হবে)
   WEBHOOK_BASE_URL=https://your-app-name.onrender.com
   PORT=8080   (Render নিজেই এটা env var হিসেবে দেয়, না দিলেও চলবে)
   ```
4. Deploy করার পর বট নিজে থেকেই webhook mode ধরে নেবে (`WEBHOOK_BASE_URL`
   সেট থাকায়) এবং `main.py` এর `run_webhook()` কল হবে।
5. প্রথমবার চালু হলে `post_init()` স্বয়ংক্রিয়ভাবে সব টেবিল তৈরি করে দেবে
   (`init_db()`), তাই আলাদা migration করার দরকার নেই।

## 🧭 প্রথম ব্যবহার — ধাপে ধাপে

### ১. প্রথম Class তৈরি
Admin `/start` দিলে মূল মেনু আসবে → **📚 Classes** → **➕ Add Class** →
Class-এর নাম লিখুন (যেমন "Class 9") → Schedule Note দিন বা `-` লিখে
স্কিপ করুন → ✅ Class তৈরি হয়ে যাবে।

### ২. প্রথম Student যোগ করা
**👨‍🎓 Students** → **➕ Add Student** → তৈরি করা Class বেছে নিন → নাম,
Roll Number, অভিভাবকের নম্বর দিন → ঠিকানা ও ভর্তির তারিখ ঐচ্ছিক (`-` দিয়ে
স্কিপ করা যায়) → Student তৈরি হবে এবং একটা **Guardian Access Code**
দেখানো হবে — এটা অভিভাবককে জানিয়ে দিন।

### ৩. প্রথম Attendance নেওয়া
মূল মেনু থেকে **✅ Take Attendance** → Class বেছে নিন → তারিখ কনফার্ম করুন
(আজকের/অন্য তারিখ) → প্রতিটা Student ডিফল্টভাবে 🟢 Present, Absent হলে
ট্যাপ করে বদলান → **📤 Submit Attendance** চাপুন। Absent Student-দের
Linked guardian-রা সাথে সাথে নোটিফিকেশন পাবেন; যাদের guardian এখনো link
করেননি, তাদের Access Code আবার admin-কে দেখানো হবে।

### ৪. Guardian Linking (ধাপে ধাপে)
1. অভিভাবক নিজে বটে গিয়ে `/start` দেন।
2. বট তাকে Guardian হিসেবে চিনে **🔗 Link My Child** / **👨‍🎓 আমার
   সন্তানেরা** — দুইটা বাটনসহ মেনু দেখায়।
3. **🔗 Link My Child** চাপলে বট Access Code চায়।
4. অভিভাবক Admin-এর দেওয়া কোড (যেমন `X7K2P9QR`) লিখে পাঠান।
5. কোড সঠিক হলে: *"✅ সফলভাবে link হয়েছে! ছাত্র: [নাম], Class: [class]"*
6. একাধিক সন্তান থাকলে প্রতিটার আলাদা কোড দিয়ে আবার **🔗 Link My Child**
   চেপে link করা যায়।
7. এরপর থেকে **👨‍🎓 আমার সন্তানেরা** চেপে Attendance History ও শতাংশ
   দেখা যাবে, এবং Absent হলে automatic নোটিফিকেশন পাবেন।

⚠️ **গুরুত্বপূর্ণ Telegram সীমাবদ্ধতা:** Telegram bot policy অনুযায়ী কোনো
ইউজারকে মেসেজ পাঠাতে হলে সেই ইউজারকে অবশ্যই আগে নিজে বট চালু (`/start`)
করতে হবে — এটা bypass করার কোনো উপায় নেই। তাই ধাপ ১-২ বাধ্যতামূলক।

## ✅ Testing Checklist

- [ ] `/start` দিলে Admin ID-এর জন্য সঠিক মেনু আসে
- [ ] নতুন Class তৈরি করা যায়, ডিফল্ট Active থাকে
- [ ] একই Class-এ দুইটা Student একই Roll Number দিয়ে যোগ করার চেষ্টা করলে
      error দেখায়
- [ ] Student তৈরি হলে Unique Access Code জেনারেট হয়
- [ ] Take Attendance-এ Present/Absent টগল ঠিকভাবে কাজ করে
- [ ] "সবাইকে Present করুন" চাপলে সব Present হয়ে যায়
- [ ] একই Class + তারিখে দ্বিতীয়বার Attendance নিতে গেলে Overwrite
      confirmation আসে, এবং Confirm করলে duplicate record তৈরি না হয়ে
      existing record update হয়
- [ ] Absent + Linked guardian থাকলে guardian-এর কাছে মেসেজ যায়
- [ ] Absent + Guardian Linked না থাকলে Admin-কে Access Code সহ সতর্কবার্তা
      দেখায়
- [ ] Guardian ভুল Access Code দিলে error দেখায়, সঠিক দিলে link হয়
- [ ] Guardian একাধিক সন্তান link করতে পারে
- [ ] Guardian অন্য কারো সন্তানের তথ্য দেখতে পারে না
- [ ] Teacher শুধু নিজের assign করা Class-এর attendance নিতে পারে
- [ ] Teacher Class/Student তৈরি বা মুছতে পারে না
- [ ] Reports-এর প্রতিটা সাব-সেকশন সঠিক তথ্য দেখায়
- [ ] Class delete করতে গেলে, Student থাকলে আটকায়
- [ ] সব admin action Activity Logs-এ দেখা যায়
- [ ] Broadcast সব Linked guardian-কে মেসেজ পাঠায়, ব্যর্থ হলে গণনা করে
      দেখায় কিন্তু পুরো প্রক্রিয়া আটকায় না

## 🔒 Security Notes

- Admin ID env var থেকে, Teacher ID ডাটাবেসে — কোনো hard-coded ID নেই
- Guardian Access Code 8-ক্যারেক্টারের random alphanumeric (ambiguous
  ক্যারেক্টার বাদ দিয়ে)
- Guardian শুধু নিজের `guardian_student_links`-এ থাকা Student-এর তথ্য
  দেখতে পারে (প্রতিটা query-তে link ভেরিফাই করা হয়)
- সব sensitive admin action Activity Log-এ যায়
