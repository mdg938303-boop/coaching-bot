"""
handlers/guardian.py
Guardian Self-Linking System এবং Guardian-side ভিউ (Attendance History,
Attendance Percentage, একাধিক সন্তান)।
"""
from sqlalchemy import select, func
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, CommandHandler,
    MessageHandler, filters,
)

from database.database import get_session
from database.models import (
    AttendanceEntry, AttendanceRecord, AttendanceStatus, ClassRoom, Guardian,
    GuardianStudentLink, Student,
)
from keyboards import guardian as gkb
from utils import states as st
from utils.helpers import format_date, log_activity, percentage


async def link_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔑 Student-এর Access Code লিখুন:", reply_markup=gkb.cancel_keyboard()
    )
    return st.GUARDIAN_LINK_CODE


async def link_code_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.strip()
    if code == gkb.BTN_CANCEL:
        context.user_data.clear()
        await update.message.reply_text("❌ বাতিল করা হয়েছে।", reply_markup=gkb.guardian_main_menu())
        return ConversationHandler.END

    uid = update.effective_user.id
    async with get_session() as session:
        result = await session.execute(select(Student).where(Student.guardian_access_code == code))
        student = result.scalar_one_or_none()
        if not student:
            await update.message.reply_text(
                "⚠️ কোড সঠিক নয়। আবার চেষ্টা করুন, অথবা Cancel চাপুন।"
            )
            return st.GUARDIAN_LINK_CODE

        guardian = await session.get(Guardian, uid)
        if not guardian:
            guardian = Guardian(id=uid)
            session.add(guardian)
            await session.flush()

        existing_link = await session.execute(
            select(GuardianStudentLink).where(
                GuardianStudentLink.guardian_id == uid, GuardianStudentLink.student_id == student.id
            )
        )
        if existing_link.scalar_one_or_none():
            await update.message.reply_text(
                "ℹ️ আপনি ইতিমধ্যে এই Student-এর সাথে link করা আছেন।",
                reply_markup=gkb.guardian_main_menu(),
            )
            return ConversationHandler.END

        session.add(GuardianStudentLink(guardian_id=uid, student_id=student.id))
        await session.commit()
        classroom = await session.get(ClassRoom, student.class_id)
        await log_activity(session, uid, "guardian_link", f"student_id={student.id}")

    await update.message.reply_text(
        f"✅ সফলভাবে link হয়েছে!\nছাত্র: {student.name}, Class: {classroom.name}",
        reply_markup=gkb.guardian_main_menu(),
    )
    return ConversationHandler.END


async def my_children(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    async with get_session() as session:
        result = await session.execute(
            select(Student)
            .join(GuardianStudentLink, GuardianStudentLink.student_id == Student.id)
            .where(GuardianStudentLink.guardian_id == uid)
        )
        students = result.scalars().all()
        for s in students:
            await session.refresh(s, attribute_names=["classroom"])

    if not students:
        await update.message.reply_text(
            "⚠️ এখনো কোনো Student link করা হয়নি। 🔗 Link My Child চেপে শুরু করুন।"
        )
        return

    await update.message.reply_text(
        "👨‍🎓 আপনার সন্তানেরা:", reply_markup=gkb.children_list_inline(students)
    )


async def child_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    student_id = int(q.data.split(":")[-1])
    uid = update.effective_user.id

    async with get_session() as session:
        link = await session.execute(
            select(GuardianStudentLink).where(
                GuardianStudentLink.guardian_id == uid, GuardianStudentLink.student_id == student_id
            )
        )
        if not link.scalar_one_or_none():
            await q.edit_message_text("⛔ এই Student আপনার সাথে Link করা নেই।")
            return
        student = await session.get(Student, student_id)
        classroom = await session.get(ClassRoom, student.class_id)
        total = await session.scalar(
            select(func.count()).select_from(AttendanceEntry).where(AttendanceEntry.student_id == student_id)
        )
        present = await session.scalar(
            select(func.count()).select_from(AttendanceEntry).where(
                AttendanceEntry.student_id == student_id, AttendanceEntry.status == AttendanceStatus.PRESENT
            )
        )
    pct = percentage(present or 0, total or 0)
    text = (
        f"👤 {student.name}\n📚 Class: {classroom.name}\n🔢 Roll: {student.roll_number}\n\n"
        f"📊 সামগ্রিক Attendance: {present or 0}/{total or 0} ({pct}%)"
    )
    await q.edit_message_text(text, reply_markup=gkb.child_detail_inline(student_id))


async def child_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    student_id = int(q.data.split(":")[-1])
    uid = update.effective_user.id

    async with get_session() as session:
        link = await session.execute(
            select(GuardianStudentLink).where(
                GuardianStudentLink.guardian_id == uid, GuardianStudentLink.student_id == student_id
            )
        )
        if not link.scalar_one_or_none():
            await q.edit_message_text("⛔ এই Student আপনার সাথে Link করা নেই।")
            return
        student = await session.get(Student, student_id)
        result = await session.execute(
            select(AttendanceRecord.attendance_date, AttendanceEntry.status)
            .join(AttendanceEntry, AttendanceEntry.attendance_record_id == AttendanceRecord.id)
            .where(AttendanceEntry.student_id == student_id)
            .order_by(AttendanceRecord.attendance_date.desc())
            .limit(30)
        )
        rows = result.all()

    if not rows:
        await q.edit_message_text(f"📅 {student.name} — এখনো কোনো হাজিরা রেকর্ড নেই।")
        return

    lines = [f"📅 {student.name} — সাম্প্রতিক {len(rows)} দিনের Attendance:\n"]
    for d, s in rows:
        icon = "🟢 Present" if s == AttendanceStatus.PRESENT else "🔴 Absent"
        lines.append(f"{format_date(d)} — {icon}")
    await q.edit_message_text("\n".join(lines))


async def child_fee_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    student_id = int(q.data.split(":")[-1])
    uid = update.effective_user.id
    from services.fee_service import get_fee_status
    from utils.helpers import current_month_str, format_month

    async with get_session() as session:
        link = await session.execute(
            select(GuardianStudentLink).where(
                GuardianStudentLink.guardian_id == uid, GuardianStudentLink.student_id == student_id
            )
        )
        if not link.scalar_one_or_none():
            await q.edit_message_text("⛔ এই Student আপনার সাথে Link করা নেই।")
            return
        student = await session.get(Student, student_id)
        month = current_month_str()
        status = await get_fee_status(session, student, month)

    if status["status"] == "NO_FEE":
        text = f"💰 {student.name} — এই Student-এর জন্য কোনো ফি নির্ধারিত নেই।"
    else:
        icon = {"PAID": "🟢 সম্পূর্ণ পরিশোধিত", "PARTIAL": "🟡 আংশিক পরিশোধিত", "DUE": "🔴 বকেয়া"}
        text = (
            f"💰 {student.name} — {format_month(month)}\n\n"
            f"মাসিক ফি: {status['monthly_fee']} টাকা\n"
            f"পরিশোধিত: {status['paid']} টাকা\n"
            f"বকেয়া: {status['due']} টাকা\n"
            f"অবস্থা: {icon[status['status']]}"
        )
    await q.edit_message_text(text)


async def child_back_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    async with get_session() as session:
        result = await session.execute(
            select(Student)
            .join(GuardianStudentLink, GuardianStudentLink.student_id == Student.id)
            .where(GuardianStudentLink.guardian_id == uid)
        )
        students = result.scalars().all()
        for s in students:
            await session.refresh(s, attribute_names=["classroom"])
    await q.edit_message_text("👨‍🎓 আপনার সন্তানেরা:", reply_markup=gkb.children_list_inline(students))


link_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(f"^{gkb.BTN_LINK_CHILD}$"), link_start)],
    states={
        st.GUARDIAN_LINK_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, link_code_submit)],
    },
    fallbacks=[
        MessageHandler(filters.Regex(f"^{gkb.BTN_CANCEL}$"), link_start),
        CommandHandler("cancel", link_start),
    ],
    name="guardian_link_conv",
)


def get_guardian_callback_handlers():
    return [
        CallbackQueryHandler(child_view, pattern=r"^gch:view:\d+$"),
        CallbackQueryHandler(child_history, pattern=r"^gch:history:\d+$"),
        CallbackQueryHandler(child_fee_status, pattern=r"^gch:fee:\d+$"),
        CallbackQueryHandler(child_back_to_list, pattern=r"^gch:list$"),
    ]
