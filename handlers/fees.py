"""
handlers/fees.py
Fee/বেতন সিস্টেম: Record Payment, Fee Status by Class, Student Fee
History, Due List, এবং JobQueue-চালিত Automatic Due Reminder।
"""
import datetime as dt

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, CommandHandler,
    MessageHandler, filters,
)

from config import FEE_REMINDER_DAYS, PAYMENT_METHODS, logger
from database.database import get_session
from database.models import ClassRoom, FeePayment, Student
from keyboards import admin as akb
from services.fee_service import (
    get_due_students_for_month, get_fee_status, record_payment,
)
from services.notification_service import notify_guardian_fee_due
from utils import states as st
from utils.helpers import current_month_str, format_month, is_admin, log_activity


async def _require_admin(update: Update) -> bool:
    uid = update.effective_user.id
    if not is_admin(uid):
        if update.callback_query:
            await update.callback_query.answer("দুঃখিত, শুধু Admin এই কাজ করতে পারবে।", show_alert=True)
        else:
            await update.message.reply_text("দুঃখিত, শুধু Admin এই কাজ করতে পারবে।")
        return False
    return True


async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("fee_pay", None)
    from keyboards.admin import admin_main_menu
    uid = update.effective_user.id
    await update.effective_message.reply_text(
        "বাতিল করা হয়েছে।", reply_markup=admin_main_menu(is_admin(uid))
    )
    return ConversationHandler.END


# =========================================================
# RECORD PAYMENT
# =========================================================

async def fee_pay_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not await _require_admin(update):
        return ConversationHandler.END
    async with get_session() as session:
        result = await session.execute(select(ClassRoom).order_by(ClassRoom.name))
        classes = result.scalars().all()
    if not classes:
        await q.message.reply_text("কোনো Class নেই।")
        return ConversationHandler.END
    context.user_data["fee_pay"] = {}
    await q.message.reply_text(
        "কোন Class-এর Student-এর Payment রেকর্ড করবেন?",
        reply_markup=akb.class_pick_inline(classes, prefix="feepay:class"),
    )
    return st.FEE_PAY_CLASS


async def fee_pay_class(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    class_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        result = await session.execute(
            select(Student).where(
                Student.class_id == class_id, Student.is_active == True  # noqa: E712
            ).order_by(Student.roll_number)
        )
        students = result.scalars().all()
    if not students:
        await q.message.reply_text("এই Class-এ কোনো Active Student নেই।")
        return ConversationHandler.END
    await q.edit_message_text(
        "কোন Student-এর পেমেন্ট?",
        reply_markup=akb.fee_student_list_inline(students, class_id, current_month_str()),
    )
    return st.FEE_PAY_STUDENT


async def fee_pay_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    student_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        student = await session.get(Student, student_id)
        month = current_month_str()
        status = await get_fee_status(session, student, month)
    context.user_data["fee_pay"]["student_id"] = student_id
    context.user_data["fee_pay"]["student_name"] = student.name
    await q.message.reply_text(
        f"{student.name}\n"
        f"মাসিক ফি: {student.monthly_fee} টাকা\n"
        f"{format_month(month)}: পরিশোধিত {status['paid']}, বকেয়া {status['due']}\n\n"
        f"এখন কত টাকা পেমেন্ট নিচ্ছেন? (শুধু সংখ্যা লিখুন)",
        reply_markup=akb.cancel_keyboard(),
    )
    return st.FEE_PAY_AMOUNT


async def fee_pay_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("শুধু একটা পজিটিভ সংখ্যা দিন (যেমন 1500):")
        return st.FEE_PAY_AMOUNT
    context.user_data["fee_pay"]["amount"] = int(text)
    await update.message.reply_text(
        f"কোন মাসের বেতন? চলতি মাস ({format_month(current_month_str())})-এর জন্য - লিখুন, "
        f"নাহলে YYYY-MM ফরম্যাটে লিখুন (যেমন 2026-07):"
    )
    return st.FEE_PAY_MONTH


async def fee_pay_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    if text == "-":
        month = current_month_str()
    else:
        try:
            y, m = text.split("-")
            dt.date(int(y), int(m), 1)
            month = "{:04d}-{:02d}".format(int(y), int(m))
        except (ValueError, IndexError):
            await update.message.reply_text("ফরম্যাট ভুল। YYYY-MM দিন (যেমন 2026-07), অথবা - লিখুন:")
            return st.FEE_PAY_MONTH
    context.user_data["fee_pay"]["month"] = month
    await update.message.reply_text(
        "Payment Method বেছে নিন:", reply_markup=akb.payment_method_inline()
    )
    return st.FEE_PAY_METHOD


async def fee_pay_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    method = q.data.split(":")[-1]
    if method not in PAYMENT_METHODS:
        method = "Other"
    fp = context.user_data.pop("fee_pay", None)
    if not fp:
        await q.edit_message_text("সেশন শেষ হয়ে গেছে, আবার শুরু করুন।")
        return ConversationHandler.END

    async with get_session() as session:
        await record_payment(
            session, fp["student_id"], fp["amount"], fp["month"], method, update.effective_user.id
        )
        student = await session.get(Student, fp["student_id"])
        status = await get_fee_status(session, student, fp["month"])

    remaining_line = "সম্পূর্ণ পরিশোধিত" if status["status"] == "PAID" else "বাকি আছে: {} টাকা".format(status["due"])

    from keyboards.admin import admin_main_menu
    await q.edit_message_text(
        "Payment রেকর্ড হয়েছে।\n\n"
        "{}\n"
        "মাস: {}\n"
        "জমা: {} টাকা ({})\n"
        "এই মাসের সর্বমোট পরিশোধিত: {} / {} টাকা\n"
        "{}".format(
            fp["student_name"], format_month(fp["month"]), fp["amount"], method,
            status["paid"], status["monthly_fee"], remaining_line,
        )
    )
    await q.message.reply_text(
        "মূল মেনু:", reply_markup=admin_main_menu(is_admin(update.effective_user.id))
    )
    return ConversationHandler.END


fee_pay_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(fee_pay_start, pattern=r"^fee:pay:start$")],
    states={
        st.FEE_PAY_CLASS: [CallbackQueryHandler(fee_pay_class, pattern=r"^feepay:class:\d+$")],
        st.FEE_PAY_STUDENT: [CallbackQueryHandler(fee_pay_student, pattern=r"^feepay:student:\d+$")],
        st.FEE_PAY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, fee_pay_amount)],
        st.FEE_PAY_MONTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, fee_pay_month)],
        st.FEE_PAY_METHOD: [CallbackQueryHandler(fee_pay_method, pattern=r"^feepay:method:")],
    },
    fallbacks=[
        MessageHandler(filters.Regex("^{}$".format(akb.BTN_CANCEL)), cancel_flow),
        CommandHandler("cancel", cancel_flow),
    ],
    name="fee_pay_conv",
)


# =========================================================
# FEE STATUS BY CLASS
# =========================================================

async def fee_status_class_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await _require_admin(update):
        return
    async with get_session() as session:
        result = await session.execute(select(ClassRoom).order_by(ClassRoom.name))
        classes = result.scalars().all()
    await q.message.reply_text(
        "কোন Class?", reply_markup=akb.class_pick_inline(classes, prefix="feestatcls")
    )


async def fee_status_class_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    class_id = int(q.data.split(":")[-1])
    await q.message.reply_text(
        "কোন মাস?", reply_markup=akb.month_pick_inline("feestatmonth:{}".format(class_id))
    )


async def fee_status_month_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    class_id, month = int(parts[1]), parts[2]
    async with get_session() as session:
        classroom = await session.get(ClassRoom, class_id)
        result = await session.execute(
            select(Student).where(
                Student.class_id == class_id, Student.is_active == True  # noqa: E712
            ).order_by(Student.roll_number)
        )
        students = result.scalars().all()
        lines = ["{} — {} ফি সামারি\n".format(classroom.name, format_month(month))]
        icons = {"NO_FEE": "⚪", "PAID": "🟢", "PARTIAL": "🟡", "DUE": "🔴"}
        for s in students:
            status = await get_fee_status(session, s, month)
            icon = icons[status["status"]]
            if status["status"] == "NO_FEE":
                lines.append("{} {} - {}: ফি নেই".format(icon, s.roll_number, s.name))
            else:
                lines.append(
                    "{} {} - {}: {}/{} টাকা".format(
                        icon, s.roll_number, s.name, status["paid"], status["monthly_fee"]
                    )
                )
    await q.edit_message_text("\n".join(lines))


# =========================================================
# STUDENT FEE HISTORY
# =========================================================

async def fee_history_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("Student-এর নাম বা Roll লিখুন:", reply_markup=akb.cancel_keyboard())
    return st.FEE_REPORT_STUDENT_SEARCH


async def fee_history_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.message.text.strip()
    if query == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    async with get_session() as session:
        result = await session.execute(
            select(Student).where(
                (Student.name.ilike("%{}%".format(query))) | (Student.roll_number.ilike("%{}%".format(query)))
            ).limit(10)
        )
        students = result.scalars().all()
    from keyboards.admin import admin_main_menu
    if not students:
        await update.message.reply_text(
            "কোনো Student পাওয়া যায়নি।",
            reply_markup=admin_main_menu(is_admin(update.effective_user.id)),
        )
        return ConversationHandler.END
    buttons = [
        [InlineKeyboardButton("{} - {}".format(s.roll_number, s.name), callback_data="feehist:view:{}".format(s.id))]
        for s in students
    ]
    await update.message.reply_text("ফলাফল বেছে নিন:", reply_markup=InlineKeyboardMarkup(buttons))
    await update.message.reply_text(
        "মূল মেনু:", reply_markup=admin_main_menu(is_admin(update.effective_user.id))
    )
    return ConversationHandler.END


async def fee_history_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    student_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        student = await session.get(Student, student_id)
        result = await session.execute(
            select(FeePayment).where(FeePayment.student_id == student_id)
            .order_by(FeePayment.paid_at.desc()).limit(30)
        )
        payments = result.scalars().all()
    if not payments:
        await q.edit_message_text("{} — এখনো কোনো Payment রেকর্ড নেই।".format(student.name))
        return
    lines = ["{} — Payment History (সাম্প্রতিক {}টি):\n".format(student.name, len(payments))]
    for p in payments:
        lines.append(
            "• {}: {} টাকা ({}) — {}".format(
                format_month(p.month), p.amount, p.payment_method, p.paid_at.strftime("%d-%m-%Y")
            )
        )
    await q.edit_message_text("\n".join(lines))


fee_history_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(fee_history_search_start, pattern=r"^fee:history:search$")],
    states={
        st.FEE_REPORT_STUDENT_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, fee_history_search_query)],
    },
    fallbacks=[
        MessageHandler(filters.Regex("^{}$".format(akb.BTN_CANCEL)), cancel_flow),
        CommandHandler("cancel", cancel_flow),
    ],
    name="fee_history_conv",
)


# =========================================================
# DUE LIST (এই মাস)
# =========================================================

async def fee_due_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    month = current_month_str()
    async with get_session() as session:
        due_list = await get_due_students_for_month(session, month)
        lines = ["{} — বকেয়া/আংশিক পরিশোধিত Student লিস্ট:\n".format(format_month(month))]
        if not due_list:
            lines.append("কোনো Student-এর ফি বকেয়া নেই।")
        else:
            for s, status in due_list:
                classroom = await session.get(ClassRoom, s.class_id)
                icon = "🟡" if status["status"] == "PARTIAL" else "🔴"
                lines.append("{} {} ({}) — বকেয়া: {} টাকা".format(icon, s.name, classroom.name, status["due"]))
    await q.edit_message_text("\n".join(lines))


def get_fee_callback_handlers():
    return [
        CallbackQueryHandler(fee_status_class_start, pattern=r"^fee:status:class$"),
        CallbackQueryHandler(fee_status_class_chosen, pattern=r"^feestatcls:\d+$"),
        CallbackQueryHandler(fee_status_month_chosen, pattern=r"^feestatmonth:\d+:"),
        CallbackQueryHandler(fee_history_view, pattern=r"^feehist:view:\d+$"),
        CallbackQueryHandler(fee_due_list, pattern=r"^fee:due:list$"),
    ]


def get_fee_conversations():
    return [fee_pay_conv, fee_history_conv]


# =========================================================
# AUTOMATIC FEE DUE REMINDER (JobQueue দিয়ে প্রতিদিন চেক হয়, শুধু
# config.FEE_REMINDER_DAYS-এ থাকা তারিখে guardian-দের কাছে পাঠানো হয়)
# =========================================================

async def fee_due_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    today = dt.date.today()
    if today.day not in FEE_REMINDER_DAYS:
        return

    month = current_month_str()
    logger.info("Running fee due reminder job for {} (day={})".format(month, today.day))

    sent, skipped = 0, 0
    async with get_session() as session:
        due_list = await get_due_students_for_month(session, month)
        for student, status in due_list:
            await session.refresh(student, attribute_names=["classroom"])
            ok = await notify_guardian_fee_due(context.bot, session, student, month, status["due"])
            if ok:
                sent += 1
            else:
                skipped += 1
        if due_list:
            await log_activity(
                session, 0, "fee_due_reminder_job",
                "month={} day={} notified={} skipped={}".format(month, today.day, sent, skipped),
            )
    logger.info("Fee due reminder job done: notified={}".format(sent))
