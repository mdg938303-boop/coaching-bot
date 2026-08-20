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

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("coaching_bot")
