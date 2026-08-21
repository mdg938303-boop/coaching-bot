"""
handlers/attendance.py
Take Attendance flow: Class বাছাই → তারিখ কনফার্ম → Present/Absent টগল →
Submit (atomic save + guardian notification trigger)।
"""
import datetime as dt

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, CommandHandler,
    MessageHandler, filters,
)

from database.database import get_session
from database.models import AttendanceStatus, ClassRoom, Student, TeacherClassAssignment
from keyboards import admin as akb
from services.attendance_service import get_existing_record, submit_attendance
from utils import states as st
from utils.menu_guard import redirect_if_menu_button
from utils.helpers import format_date, is_admin, is_teacher, parse_date_bn, get_teacher_class_ids


async def att_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("att", None)
    uid = update.effective_user.id
    async with get_session() as session:
        if is_admin(uid):
            result = await session.execute(
                select(ClassRoom).where(ClassRoom.is_active == True).order_by(ClassRoom.name)  # noqa: E712
            )
            classes = result.scalars().all()
        elif await is_teacher(session, uid):
            class_ids = await get_teacher_class_ids(session, uid)
            if not class_ids:
                await update.message.reply_text("⚠️ আপনাকে এখনো কোনো Class assign করা হয়নি।")
                return ConversationHandler.END
            result = await session.execute(
                select(ClassRoom).where(
                    ClassRoom.id.in_(class_ids), ClassRoom.is_active == True  # noqa: E712
                ).order_by(ClassRoom.name)
            )
            classes = result.scalars().all()
        else:
            await update.message.reply_text("⛔ আপনার এই কাজের অনুমতি নেই।")
            return ConversationHandler.END

    if not classes:
        await update.message.reply_text("⚠️ কোনো Active Class নেই।")
        return ConversationHandler.END

    buttons = [[InlineKeyboardButton(c.name, callback_data=f"att:class:{c.id}")] for c in classes]
    await update.message.reply_text(
        "✅ কোন Class-এর হাজিরা নেবেন?", reply_markup=InlineKeyboardMarkup(buttons)
    )
    return st.ATT_CHOOSE_CLASS


async def att_class_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    class_id = int(q.data.split(":")[-1])
    context.user_data["att"] = {"class_id": class_id}
    buttons = [
        [InlineKeyboardButton("📅 আজকের তারিখ", callback_data="att:date:today")],
        [InlineKeyboardButton("🗓️ অন্য তারিখ দিন", callback_data="att:date:custom")],
    ]
    await q.edit_message_text("তারিখ কনফার্ম করুন:", reply_markup=InlineKeyboardMarkup(buttons))
    return st.ATT_CHOOSE_DATE


async def att_date_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    return await _proceed_with_date(update, context, dt.date.today(), via_callback=True)


async def att_date_custom_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(
        "🗓️ তারিখ লিখুন (DD-MM-YYYY ফরম্যাটে):", reply_markup=akb.cancel_keyboard()
    )
    return st.ATT_CUSTOM_DATE_INPUT


async def att_date_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    text = update.message.text.strip()
    if text == akb.BTN_CANCEL:
        context.user_data.pop("att", None)
        from keyboards.admin import admin_main_menu
        await update.message.reply_text(
            "❌ বাতিল করা হয়েছে।", reply_markup=admin_main_menu(is_admin(update.effective_user.id))
        )
        return ConversationHandler.END
    parsed = parse_date_bn(text)
    if not parsed:
        await update.message.reply_text("⚠️ তারিখ ফরম্যাট ভুল। DD-MM-YYYY আকারে দিন:")
        return st.ATT_CUSTOM_DATE_INPUT
    return await _proceed_with_date(update, context, parsed, via_callback=False)


async def _proceed_with_date(update, context, chosen_date: dt.date, via_callback: bool) -> int:
    att = context.user_data.get("att")
    if not att:
        return ConversationHandler.END
    att["date"] = chosen_date

    async with get_session() as session:
        existing = await get_existing_record(session, att["class_id"], chosen_date)

    reply_target = update.callback_query.message if via_callback else update.message

    if existing:
        buttons = [
            [
                InlineKeyboardButton("✅ হ্যাঁ, Update করুন", callback_data="att:overwrite:yes"),
                InlineKeyboardButton("❌ না, বাতিল", callback_data="att:overwrite:no"),
            ]
        ]
        await reply_target.reply_text(
            f"⚠️ {format_date(chosen_date)} তারিখের হাজিরা ইতিমধ্যে নেওয়া হয়েছে। Update করতে চান?",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return st.ATT_CHOOSE_DATE

    return await _load_students_and_show(reply_target, context)


async def att_overwrite_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    choice = q.data.split(":")[-1]
    if choice == "no":
        context.user_data.pop("att", None)
        from keyboards.admin import admin_main_menu
        await q.edit_message_text("❌ বাতিল করা হয়েছে।")
        await q.message.reply_text(
            "মূল মেনু:", reply_markup=admin_main_menu(is_admin(update.effective_user.id))
        )
        return ConversationHandler.END
    return await _load_students_and_show(q.message, context)


async def _load_students_and_show(reply_target, context) -> int:
    att = context.user_data["att"]
    async with get_session() as session:
        result = await session.execute(
            select(Student).where(
                Student.class_id == att["class_id"], Student.is_active == True  # noqa: E712
            ).order_by(Student.roll_number)
        )
        students = result.scalars().all()
        classroom = await session.get(ClassRoom, att["class_id"])

    if not students:
        await reply_target.reply_text("⚠️ এই Class-এ কোনো Active Student নেই।")
        context.user_data.pop("att", None)
        return ConversationHandler.END

    att["status"] = {s.id: "PRESENT" for s in students}
    att["class_name"] = classroom.name
    context.user_data["att"] = att

    await reply_target.reply_text(
        f"📚 {classroom.name} — {format_date(att['date'])}\n"
        f"সব Student ডিফল্টভাবে 🟢 Present। Absent হলে ট্যাপ করে বদলান।",
        reply_markup=_marking_keyboard(students, att["status"]),
    )
    return st.ATT_MARKING


def _marking_keyboard(students, status_map) -> InlineKeyboardMarkup:
    buttons = []
    for s in students:
        icon = "🟢" if status_map[s.id] == "PRESENT" else "🔴"
        buttons.append(
            [InlineKeyboardButton(f"{icon} {s.roll_number} - {s.name}", callback_data=f"att:toggle:{s.id}")]
        )
    buttons.append([InlineKeyboardButton("✅ সবাইকে Present করুন", callback_data="att:markall")])
    buttons.append([InlineKeyboardButton("📤 Submit Attendance", callback_data="att:submit")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="att:cancel")])
    return InlineKeyboardMarkup(buttons)


async def att_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    att = context.user_data.get("att")
    if not att:
        await q.edit_message_text("⚠️ সেশন শেষ হয়ে গেছে, আবার শুরু করুন।")
        return ConversationHandler.END
    student_id = int(q.data.split(":")[-1])
    current = att["status"].get(student_id, "PRESENT")
    att["status"][student_id] = "ABSENT" if current == "PRESENT" else "PRESENT"

    async with get_session() as session:
        result = await session.execute(
            select(Student).where(
                Student.class_id == att["class_id"], Student.is_active == True  # noqa: E712
            ).order_by(Student.roll_number)
        )
        students = result.scalars().all()
    await q.edit_message_reply_markup(reply_markup=_marking_keyboard(students, att["status"]))
    return st.ATT_MARKING


async def att_markall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer("✅ সবাইকে Present করা হয়েছে।")
    att = context.user_data.get("att")
    if not att:
        return ConversationHandler.END
    for sid in att["status"]:
        att["status"][sid] = "PRESENT"
    async with get_session() as session:
        result = await session.execute(
            select(Student).where(
                Student.class_id == att["class_id"], Student.is_active == True  # noqa: E712
            ).order_by(Student.roll_number)
        )
        students = result.scalars().all()
    await q.edit_message_reply_markup(reply_markup=_marking_keyboard(students, att["status"]))
    return st.ATT_MARKING


async def att_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    context.user_data.pop("att", None)
    from keyboards.admin import admin_main_menu
    await q.edit_message_text("❌ Attendance বাতিল করা হয়েছে।")
    await q.message.reply_text(
        "মূল মেনু:", reply_markup=admin_main_menu(is_admin(update.effective_user.id))
    )
    return ConversationHandler.END


async def att_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer("⏳ সেভ হচ্ছে...")
    att = context.user_data.pop("att", None)
    if not att:
        await q.edit_message_text("⚠️ সেশন শেষ হয়ে গেছে।")
        return ConversationHandler.END

    async with get_session() as session:
        summary = await submit_attendance(
            session=session,
            bot=context.bot,
            class_id=att["class_id"],
            attendance_date=att["date"],
            status_map=att["status"],
            actor_id=update.effective_user.id,
        )

    text = (
        f"✅ হাজিরা সংরক্ষিত হয়েছে — Class: {att['class_name']}, তারিখ: {format_date(att['date'])}\n"
        f"🟢 Present: {summary['present']} জন\n"
        f"🔴 Absent: {summary['absent']} জন"
    )
    if summary["unnotified"]:
        text += "\n\n⚠️ নিচের Student-দের অভিভাবক এখনো Link করেননি, তাই notification যায়নি:\n"
        for name, code in summary["unnotified"]:
            text += f"• {name} — Access Code: `{code}`\n"

    await q.edit_message_text(text, parse_mode="Markdown")
    from keyboards.admin import admin_main_menu
    await q.message.reply_text(
        "মূল মেনু:", reply_markup=admin_main_menu(is_admin(update.effective_user.id))
    )
    return ConversationHandler.END


async def att_flow_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("att", None)
    from keyboards.admin import admin_main_menu
    await update.effective_message.reply_text(
        "❌ বাতিল করা হয়েছে।", reply_markup=admin_main_menu(is_admin(update.effective_user.id))
    )
    return ConversationHandler.END


attendance_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(f"^{akb.BTN_ATTENDANCE}$"), att_start)],
    states={
        st.ATT_CHOOSE_CLASS: [CallbackQueryHandler(att_class_chosen, pattern=r"^att:class:\d+$")],
        st.ATT_CHOOSE_DATE: [
            CallbackQueryHandler(att_date_today, pattern=r"^att:date:today$"),
            CallbackQueryHandler(att_date_custom_prompt, pattern=r"^att:date:custom$"),
            CallbackQueryHandler(att_overwrite_choice, pattern=r"^att:overwrite:(yes|no)$"),
        ],
        st.ATT_CUSTOM_DATE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, att_date_custom_input)],
        st.ATT_MARKING: [
            CallbackQueryHandler(att_toggle, pattern=r"^att:toggle:\d+$"),
            CallbackQueryHandler(att_markall, pattern=r"^att:markall$"),
            CallbackQueryHandler(att_submit, pattern=r"^att:submit$"),
            CallbackQueryHandler(att_cancel, pattern=r"^att:cancel$"),
        ],
    },
    fallbacks=[
        MessageHandler(filters.Regex(f"^{akb.BTN_CANCEL}$"), att_flow_cancel),
        CommandHandler("cancel", att_flow_cancel),
    ],
    allow_reentry=True,
    conversation_timeout=600,
    name="attendance_conv",
)
