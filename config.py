"""
config.py
সব environment variable এখান থেকে লোড হয়।
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN .env ফাইলে সেট করা নেই।")

_raw_admin_ids = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = set()
if _raw_admin_ids:
    for part in _raw_admin_ids.split(","):
        part = part.strip()
        if part.isdigit():
            ADMIN_IDS.add(int(part))

if not ADMIN_IDS:
    raise RuntimeError("❌ ADMIN_IDS .env ফাইলে সেট করা নেই (কমা দিয়ে একাধিক আইডি দেওয়া যাবে)।")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./coaching_bot.db").strip()

# postgres:// বা postgresql:// দিয়ে দিলেও asyncpg driver-এ কনভার্ট করে নেওয়া হয়
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").strip()
PORT = int(os.getenv("PORT", "8080"))

# WEBHOOK_BASE_URL সেট থাকলে webhook মোডে চলবে (Render-এর মতো), নাহলে local polling
USE_WEBHOOK = bool(WEBHOOK_BASE_URL)

LOW_ATTENDANCE_THRESHOLD = float(os.getenv("LOW_ATTENDANCE_THRESHOLD", "75"))

# মাসের কোন তারিখে Fee Due Reminder পাঠানো হবে (কমা দিয়ে একাধিক তারিখ দেওয়া যায়,
# যেমন "5,15,25")। ডিফল্ট প্রতি মাসের ৫ তারিখ।
_raw_fee_days = os.getenv("FEE_REMINDER_DAYS", "5").strip()
FEE_REMINDER_DAYS = set()
for part in _raw_fee_days.split(","):
    part = part.strip()
    if part.isdigit():
        FEE_REMINDER_DAYS.add(int(part))
if not FEE_REMINDER_DAYS:
    FEE_REMINDER_DAYS = {5}

# প্রতিদিন কোন সময়ে (24-ঘন্টা, সার্ভারের timezone অনুযায়ী) Due Reminder চেক হবে
FEE_REMINDER_HOUR = int(os.getenv("FEE_REMINDER_HOUR", "10"))
FEE_REMINDER_MINUTE = int(os.getenv("FEE_REMINDER_MINUTE", "0"))

PAYMENT_METHODS = ["Cash", "bKash", "Nagad", "Rocket", "Bank Transfer", "Other"]

# --- Direct SMS Gateway (ঐচ্ছিক) ---
# SMS_PROVIDER: "bulksmsbd" অথবা "alphasms"। অন্য গেটওয়ে ব্যবহার করতে চাইলে
# services/sms_service.py-এ নতুন provider ফাংশন যোগ করুন।
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "bulksmsbd").strip().lower()
SMS_API_KEY = os.getenv("SMS_API_KEY", "").strip()
SMS_SENDER_ID = os.getenv("SMS_SENDER_ID", "").strip()
# আসল on/off টগল Admin > ⚙️ Settings মেনু থেকে হয় (database-এ সেভ থাকে);
# এই এনভ ভ্যারিয়েবল শুধু প্রথমবার ডিফল্ট মান হিসেবে ব্যবহৃত হয়।
SMS_ENABLED_DEFAULT = os.getenv("SMS_ENABLED_DEFAULT", "false").strip().lower() == "true"



logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("coaching_bot")
