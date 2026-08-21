"""
main.py
Bot এর entrypoint। Local-এ polling, Render-এর মতো জায়গায় WEBHOOK_BASE_URL
সেট থাকলে webhook মোডে চলে — আগের বটগুলোর মতোই auto-detect প্যাটার্ন।
"""
import asyncio
import datetime as dt

from telegram import BotCommand
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, filters,
)

from config import (
    BOT_TOKEN, FEE_REMINDER_HOUR, FEE_REMINDER_MINUTE, PORT, USE_WEBHOOK,
    WEBHOOK_BASE_URL, logger,
)
from database.database import init_db
from handlers import admin as admin_handlers
from handlers import attendance as attendance_handlers
from handlers import fees as fee_handlers
from handlers import guardian as guardian_handlers
from handlers import nav
from keyboards.admin import (
    BTN_CLASSES, BTN_STUDENTS, BTN_REPORTS, BTN_TEACHERS, BTN_FEES, BTN_SETTINGS, BTN_LOGS,
)
from keyboards.guardian import BTN_MY_CHILDREN


async def post_init(application: Application):
    await init_db()
    await application.bot.set_my_commands([
        BotCommand("start", "বট শুরু করুন / মেনু দেখুন"),
        BotCommand("cancel", "চলমান কাজ বাতিল করুন"),
    ])
    if application.job_queue is not None:
        application.job_queue.run_daily(
            fee_handlers.fee_due_reminder_job,
            time=dt.time(hour=FEE_REMINDER_HOUR, minute=FEE_REMINDER_MINUTE),
            name="fee_due_reminder_job",
        )
        logger.info(
            f"⏰ Fee due reminder job scheduled daily at {FEE_REMINDER_HOUR:02d}:{FEE_REMINDER_MINUTE:02d}"
        )
    else:
        logger.warning(
            "⚠️ JobQueue পাওয়া যায়নি — 'pip install \"python-telegram-bot[job-queue]\"' ইনস্টল করুন, "
            "নাহলে Automatic Fee Due Reminder কাজ করবে না।"
        )
    logger.info("✅ Bot initialized and ready.")


def build_application() -> Application:
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # --- /start ও নেভিগেশন ---
    application.add_handler(CommandHandler("start", nav.start))
    application.add_handler(CommandHandler("cancel", nav.start))

    # --- Conversation Handlers (ফর্ম-ভিত্তিক ফ্লো) — এগুলো আগে রেজিস্টার
    #     করতে হবে যাতে তাদের entry point callback/text প্রথমে match করে ---
    for conv in admin_handlers.get_admin_conversations():
        application.add_handler(conv)
    for conv in fee_handlers.get_fee_conversations():
        application.add_handler(conv)
    application.add_handler(attendance_handlers.attendance_conv)
    application.add_handler(guardian_handlers.link_conv)

    # --- মূল Reply Keyboard নেভিগেশন (Admin/Teacher) ---
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_CLASSES}$"), nav.show_classes_menu))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_STUDENTS}$"), nav.show_students_menu))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_REPORTS}$"), nav.show_reports_menu))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_TEACHERS}$"), nav.show_teachers_menu))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_FEES}$"), nav.show_fees_menu))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_LOGS}$"), nav.show_logs))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_SETTINGS}$"), nav.show_settings_menu))

    # --- Guardian Reply Keyboard ---
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_MY_CHILDREN}$"), guardian_handlers.my_children))

    # --- সাধারণ CallbackQueryHandlers ---
    for handler in admin_handlers.get_admin_callback_handlers():
        application.add_handler(handler)
    for handler in fee_handlers.get_fee_callback_handlers():
        application.add_handler(handler)
    for handler in guardian_handlers.get_guardian_callback_handlers():
        application.add_handler(handler)

    return application


def main():
    application = build_application()

    if USE_WEBHOOK:
        logger.info(f"🌐 Starting in WEBHOOK mode → {WEBHOOK_BASE_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_BASE_URL.rstrip('/')}/{BOT_TOKEN}",
        )
    else:
        logger.info("🖥️ Starting in POLLING mode (local development)")
        application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
