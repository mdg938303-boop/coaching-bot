"""
handlers/nav.py
সর্বোচ্চ-অগ্রাধিকার Reply Keyboard নেভিগেশন: /start রোল চেনে এবং সঠিক মেনু
দেখায়। মূল মেনু বাটনগুলো (Classes/Students/...) চাপলে সংশ্লিষ্ট inline মেনু
দেখায় — এগুলো কোনো ConversationHandler-এর ভেতরে নয়, তাই সবসময় কাজ করবে,
কোনো ফর্মের মাঝখানে থাকলেও ব্যবহারকারীকে বের করে আনবে।
"""
import datetime as dt

from sqlalchemy import select, func
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from database.database import get_session
from database.models import AttendanceRecord, ClassRoom, Guardian, Teacher
from keyboards import admin as akb
from keyboards import guardian as gkb
from utils.helpers import is_admin, is_teacher, log_activity


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    user_id = update.effective_user.id
    async with get_session() as session:
        if is_admin(user_id):
            await update.message.reply_text(
                "👋 স্বাগতম, Admin!\nনিচের মেনু থেকে কাজ শুরু করুন।",
                reply_markup=akb.admin_main_menu(is_admin_user=True),
            )
            return ConversationHandler.END

        if await is_teacher(session, user_id):
            await update.message.reply_text(
                "👋 স্বাগতম, Teacher!\nআপনি শুধু নিজের assign করা Class-এর হাজিরা নিতে পারবেন।",
                reply_markup=akb.admin_main_menu(is_admin_user=False),
            )
            return ConversationHandler.END

        # নাহলে Guardian হিসেবে ধরে নেওয়া হবে
        result = await session.execute(select(Guardian).where(Guardian.id == user_id))
        guardian = result.scalar_one_or_none()
        if not guardian:
            guardian = Guardian(id=user_id)
            session.add(guardian)
            await session.commit()

        await update.message.reply_text(
            "👋 স্বাগতম!\n\n"
            "আপনি যদি একজন অভিভাবক হন, তাহলে আপনার সন্তানের Access Code দিয়ে "
            "'🔗 Link My Child' চেপে লিংক করুন।",
            reply_markup=gkb.guardian_main_menu(),
        )
    return ConversationHandler.END


async def show_classes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📚 Class Management", reply_markup=akb.classes_menu_inline())


async def show_students_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👨‍🎓 Student Management", reply_markup=akb.students_menu_inline())


async def show_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Attendance Reports", reply_markup=akb.reports_menu_inline())


async def show_teachers_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ শুধু Admin এই সেকশন ব্যবহার করতে পারবে।")
        return
    await update.message.reply_text("👨‍🏫 Teacher Management", reply_markup=akb.teachers_menu_inline())


async def show_fees_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ শুধু Admin এই সেকশন ব্যবহার করতে পারবে।")
        return
    await update.message.reply_text("💰 Fee Management", reply_markup=akb.fees_menu_inline())


async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ শুধু Admin এই সেকশন ব্যবহার করতে পারবে।")
        return
    from config import SMS_API_KEY
    from utils.helpers import is_sms_enabled

    async with get_session() as session:
        sms_enabled = await is_sms_enabled(session)
    status = "🟢 চালু" if sms_enabled else "🔴 বন্ধ"
    await update.message.reply_text(
        f"⚙️ Settings\n\n📩 Direct SMS নোটিফিকেশন: {status}\n\n"
        "Absent/Fee Due হলে Telegram-এর পাশাপাশি অভিভাবকের ফোনে সরাসরি SMS "
        "পাঠাতে চাইলে এখান থেকে চালু করুন।",
        reply_markup=akb.settings_menu_inline(sms_enabled, sms_configured=bool(SMS_API_KEY)),
    )


async def show_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ শুধু Admin এই সেকশন দেখতে পারবে।")
        return
    from database.models import ActivityLog

    async with get_session() as session:
        result = await session.execute(
            select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(20)
        )
        logs = result.scalars().all()

    if not logs:
        await update.message.reply_text("📝 কোনো Activity Log নেই।")
        return

    lines = ["📝 সাম্প্রতিক Activity Logs (শেষ ২০টি):\n"]
    for log in logs:
        ts = log.created_at.strftime("%d-%m-%Y %H:%M")
        lines.append(f"• [{ts}] {log.actor_id} → {log.action} {('- ' + log.details) if log.details else ''}")
    await update.message.reply_text("\n".join(lines))
