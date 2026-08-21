"""
handlers/admin.py
Class / Student / Teacher / Reports / Broadcast — সব Admin-side ConversationHandler
এবং সাধারণ CallbackQueryHandler এখানে।
"""
import datetime as dt

from sqlalchemy import select, func, delete
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler,
    CommandHandler, filters,
)

from database.database import get_session
from database.models import (
    ClassRoom, Student, Teacher, TeacherClassAssignment, AttendanceEntry,
    AttendanceRecord, AttendanceStatus, Guardian,
)
from keyboards import admin as akb
from utils import states as st
from utils.menu_guard import redirect_if_menu_button
from utils.helpers import (
    is_admin, is_teacher, log_activity, unique_access_code, parse_date_bn,
    format_date, percentage,
)

PAGE_SIZE = 8


async def _require_admin(update: Update) -> bool:
    uid = update.effective_user.id
    if not is_admin(uid):
        if update.callback_query:
            await update.callback_query.answer("⛔ শুধু Admin এই কাজ করতে পারবে।", show_alert=True)
        else:
            await update.message.reply_text("⛔ শুধু Admin এই কাজ করতে পারবে।")
        return False
    return True


async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    from keyboards.admin import admin_main_menu
    uid = update.effective_user.id
    await update.effective_message.reply_text(
        "❌ বাতিল করা হয়েছে।", reply_markup=admin_main_menu(is_admin(uid))
    )
    return ConversationHandler.END


# =========================================================
# CLASS MANAGEMENT
# =========================================================

async def cls_menu_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not await _require_admin(update):
        return ConversationHandler.END
    await q.message.reply_text(
        "📚 নতুন Class-এর নাম লিখুন:", reply_markup=akb.cancel_keyboard()
    )
    return st.CLASS_ADD_NAME


async def cls_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    name = update.message.text.strip()
    if not name or name == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    context.user_data["new_class_name"] = name
    await update.message.reply_text(
        "🗓️ Schedule Note দিন (ঐচ্ছিক — যেমন 'প্রতিদিন বিকাল ৫টা')।\n"
        "না দিতে চাইলে - লিখে পাঠান।"
    )
    return st.CLASS_ADD_SCHEDULE


async def cls_add_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    note = update.message.text.strip()
    if note == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    schedule_note = None if note == "-" else note
    name = context.user_data.pop("new_class_name")

    async with get_session() as session:
        classroom = ClassRoom(name=name, schedule_note=schedule_note, is_active=True)
        session.add(classroom)
        await session.commit()
        await log_activity(session, update.effective_user.id, "add_class", f"name={name}")

    from keyboards.admin import admin_main_menu
    await update.message.reply_text(
        f"✅ Class '{name}' তৈরি হয়েছে।",
        reply_markup=admin_main_menu(is_admin(update.effective_user.id)),
    )
    return ConversationHandler.END


async def cls_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    page = int(q.data.split(":")[-1])
    async with get_session() as session:
        result = await session.execute(
            select(ClassRoom).order_by(ClassRoom.name).offset(page * PAGE_SIZE).limit(PAGE_SIZE + 1)
        )
        classes = result.scalars().all()
    has_more = len(classes) > PAGE_SIZE
    classes = classes[:PAGE_SIZE]
    if not classes:
        await q.edit_message_text("📚 এখনো কোনো Class তৈরি হয়নি।", reply_markup=akb.classes_menu_inline())
        return
    await q.edit_message_text(
        "📋 Class লিস্ট:", reply_markup=akb.class_list_inline(classes, page, has_more)
    )


async def cls_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    class_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        classroom = await session.get(ClassRoom, class_id)
        if not classroom:
            await q.edit_message_text("⚠️ Class পাওয়া যায়নি।")
            return
        student_count = await session.scalar(
            select(func.count()).select_from(Student).where(
                Student.class_id == class_id, Student.is_active == True  # noqa: E712
            )
        )
    status = "🟢 Active" if classroom.is_active else "🔴 Inactive"
    text = (
        f"📚 {classroom.name}\n"
        f"Schedule: {classroom.schedule_note or '—'}\n"
        f"Status: {status}\n"
        f"Active Students: {student_count}"
    )
    await q.edit_message_text(text, reply_markup=akb.class_detail_inline(class_id, classroom.is_active))


async def cls_toggle_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not await _require_admin(update):
        return
    parts = q.data.split(":")
    action, class_id = parts[1], int(parts[2])
    async with get_session() as session:
        classroom = await session.get(ClassRoom, class_id)
        if not classroom:
            await q.answer("⚠️ পাওয়া যায়নি।", show_alert=True)
            return
        classroom.is_active = (action == "activate")
        await session.commit()
        await log_activity(session, update.effective_user.id, f"class_{action}", f"class_id={class_id}")
    await q.answer("✅ সম্পন্ন হয়েছে।")
    await cls_view(update, context)


async def cls_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not await _require_admin(update):
        return
    class_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        student_count = await session.scalar(
            select(func.count()).select_from(Student).where(Student.class_id == class_id)
        )
        if student_count and student_count > 0:
            await q.answer(
                "⚠️ এই Class-এ Student আছে, তাই Delete করা যাবে না। আগে Student সরান।",
                show_alert=True,
            )
            return
        classroom = await session.get(ClassRoom, class_id)
        name = classroom.name if classroom else "?"
        # আগের কোনো attendance record/teacher assignment থাকলে সরিয়ে নেওয়া হচ্ছে
        old_record_ids = await session.execute(
            select(AttendanceRecord.id).where(AttendanceRecord.class_id == class_id)
        )
        old_record_ids = [r[0] for r in old_record_ids.all()]
        if old_record_ids:
            await session.execute(
                delete(AttendanceEntry).where(AttendanceEntry.attendance_record_id.in_(old_record_ids))
            )
            await session.execute(
                delete(AttendanceRecord).where(AttendanceRecord.class_id == class_id)
            )
        await session.execute(
            delete(TeacherClassAssignment).where(TeacherClassAssignment.class_id == class_id)
        )
        await session.delete(classroom)
        await session.commit()
        await log_activity(session, update.effective_user.id, "delete_class", f"name={name}")
    await q.answer("🗑️ Class মুছে ফেলা হয়েছে।")
    await q.edit_message_text(f"🗑️ Class '{name}' মুছে ফেলা হয়েছে।")


async def cls_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not await _require_admin(update):
        return ConversationHandler.END
    class_id = int(q.data.split(":")[-1])
    context.user_data["edit_class_id"] = class_id
    await q.message.reply_text("✏️ নতুন Class নাম লিখুন:", reply_markup=akb.cancel_keyboard())
    return st.CLASS_EDIT_NAME


async def cls_edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    name = update.message.text.strip()
    if name == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    class_id = context.user_data.pop("edit_class_id")
    async with get_session() as session:
        classroom = await session.get(ClassRoom, class_id)
        old_name = classroom.name
        classroom.name = name
        await session.commit()
        await log_activity(
            session, update.effective_user.id, "edit_class",
            f"class_id={class_id} old={old_name} new={name}",
        )
    from keyboards.admin import admin_main_menu
    await update.message.reply_text(
        f"✅ Class নাম বদলে '{name}' করা হয়েছে।",
        reply_markup=admin_main_menu(is_admin(update.effective_user.id)),
    )
    return ConversationHandler.END


class_add_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(cls_menu_add_start, pattern=r"^cls:add$")],
    states={
        st.CLASS_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cls_add_name)],
        st.CLASS_ADD_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cls_add_schedule)],
    },
    fallbacks=[
        MessageHandler(filters.Regex(f"^{akb.BTN_CANCEL}$"), cancel_flow),
        CommandHandler("cancel", cancel_flow),
    ],
    allow_reentry=True,
    conversation_timeout=600,
    name="class_add_conv",
)

class_edit_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(cls_edit_start, pattern=r"^cls:edit:\d+$")],
    states={
        st.CLASS_EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cls_edit_save)],
    },
    fallbacks=[
        MessageHandler(filters.Regex(f"^{akb.BTN_CANCEL}$"), cancel_flow),
        CommandHandler("cancel", cancel_flow),
    ],
    allow_reentry=True,
    conversation_timeout=600,
    name="class_edit_conv",
)


# =========================================================
# STUDENT MANAGEMENT
# =========================================================

async def stu_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not await _require_admin(update):
        return ConversationHandler.END
    async with get_session() as session:
        result = await session.execute(
            select(ClassRoom).where(ClassRoom.is_active == True).order_by(ClassRoom.name)  # noqa: E712
        )
        classes = result.scalars().all()
    if not classes:
        await q.message.reply_text("⚠️ আগে অন্তত একটা Active Class তৈরি করুন।")
        return ConversationHandler.END
    context.user_data["student_form"] = {}
    await q.message.reply_text(
        "👨‍🎓 কোন Class-এ Student যোগ হবে?",
        reply_markup=akb.class_pick_inline(classes, prefix="stuadd:class"),
    )
    return st.STUDENT_ADD_CLASS


async def stu_add_class(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    class_id = int(q.data.split(":")[-1])
    context.user_data["student_form"]["class_id"] = class_id
    await q.message.reply_text("✍️ ছাত্রের পূর্ণ নাম লিখুন:", reply_markup=akb.cancel_keyboard())
    return st.STUDENT_ADD_NAME


async def stu_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    name = update.message.text.strip()
    if name == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    context.user_data["student_form"]["name"] = name
    await update.message.reply_text("🔢 Roll Number লিখুন:")
    return st.STUDENT_ADD_ROLL


async def stu_add_roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    roll = update.message.text.strip()
    if roll == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    form = context.user_data["student_form"]
    async with get_session() as session:
        result = await session.execute(
            select(Student).where(Student.class_id == form["class_id"], Student.roll_number == roll)
        )
        if result.scalar_one_or_none():
            await update.message.reply_text(
                f"⚠️ এই Class-এ Roll '{roll}' আগে থেকেই আছে। অন্য Roll Number দিন:"
            )
            return st.STUDENT_ADD_ROLL
    form["roll_number"] = roll
    await update.message.reply_text("📱 অভিভাবকের Mobile Number দিন:")
    return st.STUDENT_ADD_GUARDIAN_PHONE


async def stu_add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    phone = update.message.text.strip()
    if phone == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    context.user_data["student_form"]["guardian_phone"] = phone
    await update.message.reply_text("🏠 ঠিকানা দিন (ঐচ্ছিক)। না দিতে চাইলে - লিখুন।")
    return st.STUDENT_ADD_ADDRESS


async def stu_add_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    address = update.message.text.strip()
    if address == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    context.user_data["student_form"]["address"] = None if address == "-" else address
    await update.message.reply_text(
        "📅 ভর্তির তারিখ দিন (DD-MM-YYYY)। আজকের তারিখ ডিফল্ট রাখতে - লিখুন।"
    )
    return st.STUDENT_ADD_ADMISSION_DATE


async def stu_add_admission_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    text = update.message.text.strip()
    if text == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    if text == "-":
        admission_date = dt.date.today()
    else:
        admission_date = parse_date_bn(text)
        if not admission_date:
            await update.message.reply_text("⚠️ তারিখ ফরম্যাট ভুল। DD-MM-YYYY দিন, অথবা - লিখুন।")
            return st.STUDENT_ADD_ADMISSION_DATE

    context.user_data["student_form"]["admission_date"] = admission_date
    await update.message.reply_text(
        "💰 মাসিক ফি কত টাকা? (শুধু সংখ্যা লিখুন, যেমন 1500)। ফি নেই এমন হলে 0 লিখুন।"
    )
    return st.STUDENT_ADD_FEE


async def stu_add_fee(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    text = update.message.text.strip()
    if text == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    if not text.isdigit():
        await update.message.reply_text("⚠️ শুধু সংখ্যা দিন (যেমন 1500, ফি না থাকলে 0):")
        return st.STUDENT_ADD_FEE
    monthly_fee = int(text)

    form = context.user_data.pop("student_form")
    async with get_session() as session:
        code = await unique_access_code(session)
        student = Student(
            class_id=form["class_id"],
            name=form["name"],
            roll_number=form["roll_number"],
            guardian_phone=form["guardian_phone"],
            address=form["address"],
            admission_date=form["admission_date"],
            guardian_access_code=code,
            monthly_fee=monthly_fee,
        )
        session.add(student)
        await session.commit()
        classroom = await session.get(ClassRoom, form["class_id"])
        await log_activity(
            session, update.effective_user.id, "add_student",
            f"name={form['name']} class={classroom.name} fee={monthly_fee}",
        )

    from keyboards.admin import admin_main_menu
    await update.message.reply_text(
        f"✅ Student তৈরি হয়েছে!\n\n"
        f"👤 নাম: {form['name']}\n"
        f"🔢 Roll: {form['roll_number']}\n"
        f"📚 Class: {classroom.name}\n"
        f"💰 মাসিক ফি: {monthly_fee} টাকা\n\n"
        f"🔑 Guardian Access Code: `{code}`\n\n"
        f"এই কোডটি অভিভাবককে দিন — তিনি বটে গিয়ে '🔗 Link My Child' চেপে এটি "
        f"দিয়ে লিংক করলে তবেই Absence/Fee Notification পাবেন।",
        reply_markup=admin_main_menu(is_admin(update.effective_user.id)),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def _show_class_picker_for_students(q):
    async with get_session() as session:
        result = await session.execute(select(ClassRoom).order_by(ClassRoom.name))
        classes = result.scalars().all()
    if not classes:
        await q.edit_message_text("⚠️ কোনো Class নেই।")
        return
    await q.edit_message_text(
        "📚 কোন Class-এর Student দেখতে চান?",
        reply_markup=akb.class_pick_inline(classes, prefix="stu:byclasssel"),
    )


async def _show_student_list(q, class_id: int, page: int):
    async with get_session() as session:
        result = await session.execute(
            select(Student)
            .where(Student.class_id == class_id)
            .order_by(Student.roll_number)
            .offset(page * PAGE_SIZE)
            .limit(PAGE_SIZE + 1)
        )
        students = result.scalars().all()
    has_more = len(students) > PAGE_SIZE
    students = students[:PAGE_SIZE]
    if not students:
        await q.edit_message_text("⚠️ এই Class-এ কোনো Student নেই।")
        return
    await q.edit_message_text(
        "👨‍🎓 Student লিস্ট:",
        reply_markup=akb.student_list_inline(students, page, has_more, class_id),
    )


async def stu_browse_by_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles both 'stu:byclass:<page>' (class পছন্দ করার ধাপ) এবং
    'stu:byclass:<class_id>:<page>' (student লিস্ট দেখানোর ধাপ)।"""
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    if len(parts) == 3:  # stu:byclass:<page> => class পছন্দ করার ধাপ
        await _show_class_picker_for_students(q)
        return
    # stu:byclass:<class_id>:<page>
    class_id, page = int(parts[2]), int(parts[3])
    await _show_student_list(q, class_id, page)


async def stu_byclass_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    class_id = int(q.data.split(":")[-1])
    await _show_student_list(q, class_id, 0)


async def stu_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    student_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        student = await session.get(Student, student_id)
        if not student:
            await q.edit_message_text("⚠️ Student পাওয়া যায়নি।")
            return
        classroom = await session.get(ClassRoom, student.class_id)
        total = await session.scalar(
            select(func.count()).select_from(AttendanceEntry).where(AttendanceEntry.student_id == student_id)
        )
        present = await session.scalar(
            select(func.count()).select_from(AttendanceEntry).where(
                AttendanceEntry.student_id == student_id,
                AttendanceEntry.status == AttendanceStatus.PRESENT,
            )
        )
        from database.models import GuardianStudentLink
        guardian_linked = await session.scalar(
            select(func.count()).select_from(GuardianStudentLink).where(
                GuardianStudentLink.student_id == student_id
            )
        )
        from services.fee_service import get_fee_status
        from utils.helpers import current_month_str, format_month
        month = current_month_str()
        fee_info = await get_fee_status(session, student, month)
    pct = percentage(present or 0, total or 0)
    status = "🟢 Active" if student.is_active else "🔴 Inactive"
    linked_text = "✅ হ্যাঁ" if guardian_linked else "❌ না"
    fee_icons = {"NO_FEE": "⚪ ফি নেই", "PAID": "🟢 পরিশোধিত", "PARTIAL": "🟡 আংশিক পরিশোধিত", "DUE": "🔴 বকেয়া"}
    fee_line = f"💰 মাসিক ফি: {student.monthly_fee} টাকা | {format_month(month)}: {fee_icons[fee_info['status']]}"
    if fee_info["status"] in ("DUE", "PARTIAL"):
        fee_line += f" (বকেয়া: {fee_info['due']} টাকা)"
    text = (
        f"👤 {student.name}\n"
        f"🔢 Roll: {student.roll_number}\n"
        f"📚 Class: {classroom.name}\n"
        f"📱 Guardian Phone: {student.guardian_phone or '—'}\n"
        f"🏠 ঠিকানা: {student.address or '—'}\n"
        f"📅 ভর্তির তারিখ: {format_date(student.admission_date)}\n"
        f"Status: {status}\n"
        f"👪 Guardian Linked: {linked_text}\n"
        f"🔑 Access Code: `{student.guardian_access_code}`\n\n"
        f"📊 Attendance: {present or 0}/{total or 0} ({pct}%)\n"
        f"{fee_line}"
    )
    await q.edit_message_text(
        text, reply_markup=akb.student_detail_inline(student_id, student.is_active),
        parse_mode="Markdown",
    )


async def stu_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🔎 নাম বা Roll Number লিখুন:", reply_markup=akb.cancel_keyboard())
    return st.STUDENT_SEARCH_QUERY


async def stu_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    query = update.message.text.strip()
    if query == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    async with get_session() as session:
        result = await session.execute(
            select(Student).where(
                (Student.name.ilike(f"%{query}%")) | (Student.roll_number.ilike(f"%{query}%"))
            ).limit(15)
        )
        students = result.scalars().all()
    from keyboards.admin import admin_main_menu
    if not students:
        await update.message.reply_text(
            "⚠️ কোনো Student পাওয়া যায়নি।",
            reply_markup=admin_main_menu(is_admin(update.effective_user.id)),
        )
        return ConversationHandler.END
    buttons = [
        [InlineKeyboardButton(f"{s.roll_number} - {s.name}", callback_data=f"stu:view:{s.id}")]
        for s in students
    ]
    await update.message.reply_text(
        f"🔎 '{query}' এর জন্য ফলাফল:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    await update.message.reply_text(
        "মূল মেনুতে ফিরে যেতে নিচের বাটন ব্যবহার করুন।",
        reply_markup=admin_main_menu(is_admin(update.effective_user.id)),
    )
    return ConversationHandler.END


async def stu_toggle_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not await _require_admin(update):
        return
    parts = q.data.split(":")
    action, student_id = parts[1], int(parts[2])
    async with get_session() as session:
        student = await session.get(Student, student_id)
        student.is_active = (action == "active")
        await session.commit()
        await log_activity(session, update.effective_user.id, f"student_{action}", f"student_id={student_id}")
    await q.answer("✅ সম্পন্ন হয়েছে।")
    await stu_view(update, context)


async def stu_regen_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not await _require_admin(update):
        return
    student_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        student = await session.get(Student, student_id)
        new_code = await unique_access_code(session)
        student.guardian_access_code = new_code
        await session.commit()
        await log_activity(session, update.effective_user.id, "regen_access_code", f"student_id={student_id}")
    await q.answer("🔁 নতুন কোড জেনারেট হয়েছে।", show_alert=True)
    await stu_view(update, context)


async def stu_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not await _require_admin(update):
        return
    student_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        from database.models import GuardianStudentLink
        student = await session.get(Student, student_id)
        name = student.name if student else "?"
        # dependent রেকর্ড আগে সরিয়ে না নিলে FK constraint এ আটকে যেতে পারে
        await session.execute(
            delete(AttendanceEntry).where(AttendanceEntry.student_id == student_id)
        )
        await session.execute(
            delete(GuardianStudentLink).where(GuardianStudentLink.student_id == student_id)
        )
        await session.delete(student)
        await session.commit()
        await log_activity(session, update.effective_user.id, "delete_student", f"name={name}")
    await q.answer("🗑️ Student মুছে ফেলা হয়েছে।")
    await q.edit_message_text(f"🗑️ Student '{name}' সম্পূর্ণ মুছে ফেলা হয়েছে।")


async def stu_editmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    student_id = int(q.data.split(":")[-1])
    await q.edit_message_text(
        "✏️ কোন তথ্য পরিবর্তন করবেন?", reply_markup=akb.student_edit_field_inline(student_id)
    )


async def stu_editfield_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not await _require_admin(update):
        return ConversationHandler.END
    parts = q.data.split(":")
    student_id, field = int(parts[2]), parts[3]
    context.user_data["edit_student_id"] = student_id
    context.user_data["edit_field"] = field
    labels = {"name": "নাম", "roll": "Roll Number", "phone": "অভিভাবকের নম্বর", "address": "ঠিকানা", "fee": "মাসিক ফি (শুধু সংখ্যা)"}
    await q.message.reply_text(f"✍️ নতুন {labels[field]} লিখুন:", reply_markup=akb.cancel_keyboard())
    return st.STUDENT_EDIT_FIELD_VALUE


async def stu_editfield_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    value = update.message.text.strip()
    if value == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    student_id = context.user_data.pop("edit_student_id")
    field = context.user_data.pop("edit_field")

    async with get_session() as session:
        student = await session.get(Student, student_id)
        if field == "name":
            student.name = value
        elif field == "roll":
            dup = await session.execute(
                select(Student).where(
                    Student.class_id == student.class_id, Student.roll_number == value,
                    Student.id != student_id,
                )
            )
            if dup.scalar_one_or_none():
                await update.message.reply_text(f"⚠️ Roll '{value}' আগে থেকেই এই Class-এ আছে।")
                return st.STUDENT_EDIT_FIELD_VALUE
            student.roll_number = value
        elif field == "phone":
            student.guardian_phone = value
        elif field == "fee":
            if not value.isdigit():
                await update.message.reply_text("⚠️ শুধু সংখ্যা দিন (যেমন 1500):")
                context.user_data["edit_student_id"] = student_id
                context.user_data["edit_field"] = field
                return st.STUDENT_EDIT_FIELD_VALUE
            student.monthly_fee = int(value)
        elif field == "address":
            student.address = value
        await session.commit()
        await log_activity(session, update.effective_user.id, "edit_student", f"student_id={student_id} field={field}")

    from keyboards.admin import admin_main_menu
    await update.message.reply_text(
        "✅ আপডেট হয়েছে।", reply_markup=admin_main_menu(is_admin(update.effective_user.id))
    )
    return ConversationHandler.END


async def stu_changeclass_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await _require_admin(update):
        return
    student_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        result = await session.execute(
            select(ClassRoom).where(ClassRoom.is_active == True).order_by(ClassRoom.name)  # noqa: E712
        )
        classes = result.scalars().all()
    await q.message.reply_text(
        "🔄 নতুন Class বেছে নিন:",
        reply_markup=akb.class_pick_inline(classes, prefix=f"stuchcls:{student_id}"),
    )


async def stu_changeclass_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    student_id, new_class_id = int(parts[1]), int(parts[2])
    async with get_session() as session:
        student = await session.get(Student, student_id)
        old_class = await session.get(ClassRoom, student.class_id)
        new_class = await session.get(ClassRoom, new_class_id)
        student.class_id = new_class_id
        await session.commit()
        await log_activity(
            session, update.effective_user.id, "change_class",
            f"student_id={student_id} from={old_class.name} to={new_class.name}",
        )
    await q.message.reply_text(f"✅ {student.name}-কে '{new_class.name}' এ ট্রান্সফার করা হয়েছে।")


student_add_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(stu_add_start, pattern=r"^stu:add$")],
    states={
        st.STUDENT_ADD_CLASS: [CallbackQueryHandler(stu_add_class, pattern=r"^stuadd:class:\d+$")],
        st.STUDENT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_add_name)],
        st.STUDENT_ADD_ROLL: [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_add_roll)],
        st.STUDENT_ADD_GUARDIAN_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_add_phone)],
        st.STUDENT_ADD_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_add_address)],
        st.STUDENT_ADD_ADMISSION_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_add_admission_date)],
        st.STUDENT_ADD_FEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_add_fee)],
    },
    fallbacks=[
        MessageHandler(filters.Regex(f"^{akb.BTN_CANCEL}$"), cancel_flow),
        CommandHandler("cancel", cancel_flow),
    ],
    allow_reentry=True,
    conversation_timeout=600,
    name="student_add_conv",
)

student_search_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(stu_search_start, pattern=r"^stu:search$")],
    states={
        st.STUDENT_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_search_query)],
    },
    fallbacks=[
        MessageHandler(filters.Regex(f"^{akb.BTN_CANCEL}$"), cancel_flow),
        CommandHandler("cancel", cancel_flow),
    ],
    allow_reentry=True,
    conversation_timeout=600,
    name="student_search_conv",
)

student_editfield_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(stu_editfield_start, pattern=r"^stu:editfield:\d+:\w+$")],
    states={
        st.STUDENT_EDIT_FIELD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, stu_editfield_save)],
    },
    fallbacks=[
        MessageHandler(filters.Regex(f"^{akb.BTN_CANCEL}$"), cancel_flow),
        CommandHandler("cancel", cancel_flow),
    ],
    allow_reentry=True,
    conversation_timeout=600,
    name="student_editfield_conv",
)


# =========================================================
# TEACHER MANAGEMENT (Admin only)
# =========================================================

async def tch_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if not await _require_admin(update):
        return ConversationHandler.END
    context.user_data["teacher_form"] = {}
    await q.message.reply_text("👨‍🏫 Teacher-এর নাম লিখুন:", reply_markup=akb.cancel_keyboard())
    return st.TEACHER_ADD_NAME


async def tch_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    name = update.message.text.strip()
    if name == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    context.user_data["teacher_form"]["name"] = name
    await update.message.reply_text(
        "🆔 Teacher-এর Telegram numeric ID দিন (Teacher @userinfobot দিয়ে বের করে দেবে):"
    )
    return st.TEACHER_ADD_ID


async def tch_add_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    text = update.message.text.strip()
    if text == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    if not text.isdigit():
        await update.message.reply_text("⚠️ শুধু সংখ্যা দিন (Telegram numeric ID):")
        return st.TEACHER_ADD_ID
    teacher_id = int(text)
    async with get_session() as session:
        existing = await session.get(Teacher, teacher_id)
        if existing:
            await update.message.reply_text("⚠️ এই আইডি দিয়ে ইতিমধ্যে একজন Teacher যোগ করা আছে।")
            return ConversationHandler.END
        result = await session.execute(
            select(ClassRoom).where(ClassRoom.is_active == True).order_by(ClassRoom.name)  # noqa: E712
        )
        classes = result.scalars().all()
    if not classes:
        await update.message.reply_text("⚠️ আগে অন্তত একটা Active Class তৈরি করুন।")
        return ConversationHandler.END
    context.user_data["teacher_form"]["id"] = teacher_id
    context.user_data["teacher_form"]["selected_classes"] = set()
    await update.message.reply_text(
        "📚 কোন কোন Class assign করবেন? (একাধিক সিলেক্ট করা যাবে, শেষে Done চাপুন)",
        reply_markup=akb.multi_class_select_inline(classes, set()),
    )
    return st.TEACHER_ADD_CLASSES


async def tch_add_toggle_class(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    payload = q.data.split(":")[-1]
    form = context.user_data.get("teacher_form")
    if not form:
        await q.edit_message_text("⚠️ সেশন শেষ হয়ে গেছে, আবার শুরু করুন।")
        return ConversationHandler.END

    async with get_session() as session:
        result = await session.execute(
            select(ClassRoom).where(ClassRoom.is_active == True).order_by(ClassRoom.name)  # noqa: E712
        )
        classes = result.scalars().all()

        if payload == "done":
            if not form["selected_classes"]:
                await q.answer("⚠️ কমপক্ষে একটা Class সিলেক্ট করুন।", show_alert=True)
                return st.TEACHER_ADD_CLASSES
            teacher = Teacher(id=form["id"], name=form["name"])
            session.add(teacher)
            await session.flush()
            for cid in form["selected_classes"]:
                session.add(TeacherClassAssignment(teacher_id=form["id"], class_id=cid))
            await session.commit()
            await log_activity(
                session, update.effective_user.id, "add_teacher",
                f"teacher_id={form['id']} name={form['name']} classes={list(form['selected_classes'])}",
            )
            context.user_data.pop("teacher_form", None)
            from keyboards.admin import admin_main_menu
            await q.edit_message_text(f"✅ Teacher '{form['name']}' যোগ করা হয়েছে।")
            await q.message.reply_text(
                "মূল মেনু:", reply_markup=admin_main_menu(is_admin(update.effective_user.id))
            )
            return ConversationHandler.END

        cid = int(payload)
        if cid in form["selected_classes"]:
            form["selected_classes"].discard(cid)
        else:
            form["selected_classes"].add(cid)

    await q.edit_message_reply_markup(
        reply_markup=akb.multi_class_select_inline(classes, form["selected_classes"])
    )
    return st.TEACHER_ADD_CLASSES


async def tch_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await _require_admin(update):
        return
    page = int(q.data.split(":")[-1])
    async with get_session() as session:
        result = await session.execute(
            select(Teacher).order_by(Teacher.name).offset(page * PAGE_SIZE).limit(PAGE_SIZE + 1)
        )
        teachers = result.scalars().all()
    has_more = len(teachers) > PAGE_SIZE
    teachers = teachers[:PAGE_SIZE]
    if not teachers:
        await q.edit_message_text("👨‍🏫 কোনো Teacher যোগ করা হয়নি।", reply_markup=akb.teachers_menu_inline())
        return
    await q.edit_message_text("📋 Teacher লিস্ট:", reply_markup=akb.teacher_list_inline(teachers, page, has_more))


async def tch_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    teacher_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        teacher = await session.get(Teacher, teacher_id)
        result = await session.execute(
            select(ClassRoom.name).join(
                TeacherClassAssignment, TeacherClassAssignment.class_id == ClassRoom.id
            ).where(TeacherClassAssignment.teacher_id == teacher_id)
        )
        class_names = [r[0] for r in result.all()]
    text = (
        f"👨‍🏫 {teacher.name}\n"
        f"🆔 Telegram ID: {teacher.id}\n"
        f"📚 Assigned Classes: {', '.join(class_names) if class_names else '—'}"
    )
    await q.edit_message_text(text, reply_markup=akb.teacher_detail_inline(teacher_id))


async def tch_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not await _require_admin(update):
        return
    teacher_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        teacher = await session.get(Teacher, teacher_id)
        name = teacher.name if teacher else "?"
        await session.execute(
            delete(TeacherClassAssignment).where(TeacherClassAssignment.teacher_id == teacher_id)
        )
        await session.delete(teacher)
        await session.commit()
        await log_activity(session, update.effective_user.id, "remove_teacher", f"name={name}")
    await q.answer("🗑️ সরানো হয়েছে।")
    await q.edit_message_text(f"🗑️ Teacher '{name}' সরিয়ে ফেলা হয়েছে।")


async def tch_editclasses_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await _require_admin(update):
        return
    teacher_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        result = await session.execute(
            select(ClassRoom).where(ClassRoom.is_active == True).order_by(ClassRoom.name)  # noqa: E712
        )
        classes = result.scalars().all()
        result2 = await session.execute(
            select(TeacherClassAssignment.class_id).where(TeacherClassAssignment.teacher_id == teacher_id)
        )
        current = {r[0] for r in result2.all()}
    context.user_data["edit_teacher_id"] = teacher_id
    context.user_data["edit_teacher_selected"] = current
    await q.message.reply_text(
        "✏️ Assigned Classes আপডেট করুন (টগল করুন, শেষে Done চাপুন):",
        reply_markup=akb.multi_class_select_inline(classes, current, prefix="tcheditsel"),
    )


async def tch_editclasses_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    payload = q.data.split(":")[-1]
    teacher_id = context.user_data.get("edit_teacher_id")
    selected = context.user_data.get("edit_teacher_selected")
    if teacher_id is None or selected is None:
        await q.edit_message_text("⚠️ সেশন শেষ, আবার চেষ্টা করুন।")
        return

    async with get_session() as session:
        result = await session.execute(
            select(ClassRoom).where(ClassRoom.is_active == True).order_by(ClassRoom.name)  # noqa: E712
        )
        classes = result.scalars().all()

        if payload == "done":
            await session.execute(
                delete(TeacherClassAssignment).where(TeacherClassAssignment.teacher_id == teacher_id)
            )
            for cid in selected:
                session.add(TeacherClassAssignment(teacher_id=teacher_id, class_id=cid))
            await session.commit()
            await log_activity(
                session, update.effective_user.id, "edit_teacher_classes",
                f"teacher_id={teacher_id} classes={list(selected)}",
            )
            context.user_data.pop("edit_teacher_id", None)
            context.user_data.pop("edit_teacher_selected", None)
            await q.edit_message_text("✅ Assigned Classes আপডেট হয়েছে।")
            return

        cid = int(payload)
        if cid in selected:
            selected.discard(cid)
        else:
            selected.add(cid)

    await q.edit_message_reply_markup(
        reply_markup=akb.multi_class_select_inline(classes, selected, prefix="tcheditsel")
    )


teacher_add_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(tch_add_start, pattern=r"^tch:add$")],
    states={
        st.TEACHER_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, tch_add_name)],
        st.TEACHER_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, tch_add_id)],
        st.TEACHER_ADD_CLASSES: [CallbackQueryHandler(tch_add_toggle_class, pattern=r"^tchsel:")],
    },
    fallbacks=[
        MessageHandler(filters.Regex(f"^{akb.BTN_CANCEL}$"), cancel_flow),
        CommandHandler("cancel", cancel_flow),
    ],
    allow_reentry=True,
    conversation_timeout=600,
    name="teacher_add_conv",
)


# =========================================================
# REPORTS
# =========================================================

async def rep_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    today = dt.date.today()
    async with get_session() as session:
        result = await session.execute(select(ClassRoom).where(ClassRoom.is_active == True))  # noqa: E712
        classes = result.scalars().all()
        lines = [f"📅 আজকের হাজিরা সামারি ({format_date(today)}):\n"]
        for c in classes:
            record = await session.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.class_id == c.id, AttendanceRecord.attendance_date == today
                )
            )
            record = record.scalar_one_or_none()
            if not record:
                lines.append(f"📚 {c.name}: ⚠️ এখনো হাজিরা নেওয়া হয়নি")
                continue
            present = await session.scalar(
                select(func.count()).select_from(AttendanceEntry).where(
                    AttendanceEntry.attendance_record_id == record.id,
                    AttendanceEntry.status == AttendanceStatus.PRESENT,
                )
            )
            absent = await session.scalar(
                select(func.count()).select_from(AttendanceEntry).where(
                    AttendanceEntry.attendance_record_id == record.id,
                    AttendanceEntry.status == AttendanceStatus.ABSENT,
                )
            )
            lines.append(f"📚 {c.name}: 🟢 {present} Present, 🔴 {absent} Absent")
    await q.edit_message_text("\n".join(lines))


async def rep_student_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🔎 Student-এর নাম বা Roll লিখুন:", reply_markup=akb.cancel_keyboard())
    return st.REPORT_STUDENT_SEARCH


async def rep_student_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    query = update.message.text.strip()
    if query == akb.BTN_CANCEL:
        return await cancel_flow(update, context)
    async with get_session() as session:
        result = await session.execute(
            select(Student).where(
                (Student.name.ilike(f"%{query}%")) | (Student.roll_number.ilike(f"%{query}%"))
            ).limit(10)
        )
        students = result.scalars().all()
    from keyboards.admin import admin_main_menu
    if not students:
        await update.message.reply_text(
            "⚠️ কোনো Student পাওয়া যায়নি।",
            reply_markup=admin_main_menu(is_admin(update.effective_user.id)),
        )
        return ConversationHandler.END
    buttons = [
        [InlineKeyboardButton(f"{s.roll_number} - {s.name}", callback_data=f"rep:studentview:{s.id}")]
        for s in students
    ]
    await update.message.reply_text("ফলাফল বেছে নিন:", reply_markup=InlineKeyboardMarkup(buttons))
    await update.message.reply_text(
        "মূল মেনু:", reply_markup=admin_main_menu(is_admin(update.effective_user.id))
    )
    return ConversationHandler.END


async def rep_student_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    student_id = int(q.data.split(":")[-1])
    async with get_session() as session:
        student = await session.get(Student, student_id)
        classroom = await session.get(ClassRoom, student.class_id)
        result = await session.execute(
            select(AttendanceRecord.attendance_date, AttendanceEntry.status)
            .join(AttendanceEntry, AttendanceEntry.attendance_record_id == AttendanceRecord.id)
            .where(AttendanceEntry.student_id == student_id)
            .order_by(AttendanceRecord.attendance_date.desc())
            .limit(30)
        )
        rows = result.all()
    total = len(rows)
    present = sum(1 for _, s in rows if s == AttendanceStatus.PRESENT)
    pct = percentage(present, total)
    lines = [f"👨‍🎓 {student.name} ({classroom.name}) — সাম্প্রতিক {total} দিন\n"]
    for d, s in rows:
        icon = "🟢" if s == AttendanceStatus.PRESENT else "🔴"
        lines.append(f"{icon} {format_date(d)}")
    lines.append(f"\n📊 সামগ্রিক শতাংশ (সাম্প্রতিক {total} দিনের): {pct}%")
    await q.edit_message_text("\n".join(lines))


async def rep_classmonth_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with get_session() as session:
        result = await session.execute(select(ClassRoom).order_by(ClassRoom.name))
        classes = result.scalars().all()
    await q.message.reply_text(
        "📚 কোন Class?", reply_markup=akb.class_pick_inline(classes, prefix="repcls")
    )


async def rep_classmonth_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    class_id = int(q.data.split(":")[-1])
    context.user_data["rep_class_id"] = class_id
    await q.message.reply_text("🗓️ কোন মাস?", reply_markup=akb.month_pick_inline(f"repmonth:{class_id}"))


async def rep_classmonth_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    class_id, ym = int(parts[1]), parts[2]
    year, month = map(int, ym.split("-"))
    async with get_session() as session:
        classroom = await session.get(ClassRoom, class_id)
        result = await session.execute(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.class_id == class_id,
                func.extract("year", AttendanceRecord.attendance_date) == year,
                func.extract("month", AttendanceRecord.attendance_date) == month,
            )
            .order_by(AttendanceRecord.attendance_date)
        )
        records = result.scalars().all()
        lines = [f"📚 {classroom.name} — {dt.date(year, month, 1).strftime('%B %Y')}\n"]
        if not records:
            lines.append("⚠️ এই মাসে কোনো হাজিরা নেওয়া হয়নি।")
        for r in records:
            present = await session.scalar(
                select(func.count()).select_from(AttendanceEntry).where(
                    AttendanceEntry.attendance_record_id == r.id,
                    AttendanceEntry.status == AttendanceStatus.PRESENT,
                )
            )
            absent = await session.scalar(
                select(func.count()).select_from(AttendanceEntry).where(
                    AttendanceEntry.attendance_record_id == r.id,
                    AttendanceEntry.status == AttendanceStatus.ABSENT,
                )
            )
            lines.append(f"{format_date(r.attendance_date)}: 🟢 {present} | 🔴 {absent}")
    await q.edit_message_text("\n".join(lines))


async def rep_low_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    from config import LOW_ATTENDANCE_THRESHOLD
    async with get_session() as session:
        result = await session.execute(select(Student).where(Student.is_active == True))  # noqa: E712
        students = result.scalars().all()
        low_list = []
        for s in students:
            total = await session.scalar(
                select(func.count()).select_from(AttendanceEntry).where(AttendanceEntry.student_id == s.id)
            )
            if not total:
                continue
            present = await session.scalar(
                select(func.count()).select_from(AttendanceEntry).where(
                    AttendanceEntry.student_id == s.id, AttendanceEntry.status == AttendanceStatus.PRESENT
                )
            )
            pct = percentage(present, total)
            if pct < LOW_ATTENDANCE_THRESHOLD:
                classroom = await session.get(ClassRoom, s.class_id)
                low_list.append((s.name, classroom.name, pct))
    if not low_list:
        await q.edit_message_text(f"✅ {LOW_ATTENDANCE_THRESHOLD}% এর নিচে কোনো Student নেই।")
        return
    low_list.sort(key=lambda x: x[2])
    lines = [f"📉 {LOW_ATTENDANCE_THRESHOLD}% এর নিচে Attendance:\n"]
    for name, cname, pct in low_list:
        lines.append(f"🔴 {name} ({cname}) — {pct}%")
    await q.edit_message_text("\n".join(lines))


report_student_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(rep_student_start, pattern=r"^rep:student$")],
    states={
        st.REPORT_STUDENT_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, rep_student_query)],
    },
    fallbacks=[
        MessageHandler(filters.Regex(f"^{akb.BTN_CANCEL}$"), cancel_flow),
        CommandHandler("cancel", cancel_flow),
    ],
    allow_reentry=True,
    conversation_timeout=600,
    name="report_student_conv",
)


# =========================================================
# BROADCAST (Admin only) — সব Guardian-কে মেসেজ পাঠানো
# =========================================================

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _require_admin(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "📢 যে মেসেজটা সব Linked Guardian-কে পাঠাতে চান, লিখুন:",
        reply_markup=akb.cancel_keyboard(),
    )
    return st.BROADCAST_MESSAGE


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
    text = update.message.text.strip()
    if text == akb.BTN_CANCEL:
        return await cancel_flow(update, context)

    async with get_session() as session:
        result = await session.execute(select(Guardian.id))
        guardian_ids = [r[0] for r in result.all()]

    sent, failed = 0, 0
    for gid in guardian_ids:
        try:
            await context.bot.send_message(chat_id=gid, text=f"📢 কোচিং সেন্টার থেকে ঘোষণা:\n\n{text}")
            sent += 1
        except Exception:
            failed += 1

    async with get_session() as session:
        await log_activity(
            session, update.effective_user.id, "broadcast", f"sent={sent} failed={failed}"
        )

    from keyboards.admin import admin_main_menu
    await update.message.reply_text(
        f"✅ Broadcast পাঠানো শেষ। সফল: {sent}, ব্যর্থ: {failed}",
        reply_markup=admin_main_menu(is_admin(update.effective_user.id)),
    )
    return ConversationHandler.END


broadcast_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(f"^{akb.BTN_BROADCAST}$"), broadcast_start)],
    states={
        st.BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)],
    },
    fallbacks=[
        MessageHandler(filters.Regex(f"^{akb.BTN_CANCEL}$"), cancel_flow),
        CommandHandler("cancel", cancel_flow),
    ],
    allow_reentry=True,
    conversation_timeout=600,
    name="broadcast_conv",
)


# =========================================================
# একগুচ্ছ সাধারণ (non-conversation) CallbackQueryHandler
# =========================================================

async def settings_sms_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not await _require_admin(update):
        return
    from config import SMS_API_KEY
    from utils.helpers import SMS_ENABLED_KEY, is_sms_enabled, set_setting

    async with get_session() as session:
        currently_enabled = await is_sms_enabled(session)
        new_value = "false" if currently_enabled else "true"
        if new_value == "true" and not SMS_API_KEY:
            await q.answer(
                "⚠️ SMS_API_KEY .env-এ সেট করা নেই, তাই SMS চালু করা যাচ্ছে না। "
                "আগে .env-এ SMS_PROVIDER/SMS_API_KEY/SMS_SENDER_ID সেট করে বট রিস্টার্ট করুন।",
                show_alert=True,
            )
            return
        await set_setting(session, SMS_ENABLED_KEY, new_value)
        await log_activity(
            session, update.effective_user.id, "settings_sms_toggle", f"enabled={new_value}"
        )
        sms_enabled = new_value == "true"

    await q.answer("✅ আপডেট হয়েছে।")
    status = "🟢 চালু" if sms_enabled else "🔴 বন্ধ"
    await q.edit_message_text(
        f"⚙️ Settings\n\n📩 Direct SMS নোটিফিকেশন: {status}\n\n"
        "Absent/Fee Due হলে Telegram-এর পাশাপাশি অভিভাবকের ফোনে সরাসরি SMS "
        "পাঠাতে চাইলে এখান থেকে চালু করুন।",
        reply_markup=akb.settings_menu_inline(sms_enabled, sms_configured=bool(SMS_API_KEY)),
    )


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


def get_admin_callback_handlers():
    return [
        CallbackQueryHandler(noop_callback, pattern=r"^noop:"),
        CallbackQueryHandler(settings_sms_toggle, pattern=r"^settings:sms:toggle$"),
        CallbackQueryHandler(cls_list, pattern=r"^cls:list:\d+$"),
        CallbackQueryHandler(cls_view, pattern=r"^cls:view:\d+$"),
        CallbackQueryHandler(cls_toggle_active, pattern=r"^cls:(activate|deactivate):\d+$"),
        CallbackQueryHandler(cls_delete, pattern=r"^cls:delete:\d+$"),
        CallbackQueryHandler(stu_browse_by_class, pattern=r"^stu:byclass:\d+(:\d+)?$"),
        CallbackQueryHandler(stu_byclass_selected, pattern=r"^stu:byclasssel:\d+$"),
        CallbackQueryHandler(stu_view, pattern=r"^stu:view:\d+$"),
        CallbackQueryHandler(stu_toggle_active, pattern=r"^stu:(active|inactive):\d+$"),
        CallbackQueryHandler(stu_regen_code, pattern=r"^stu:regencode:\d+$"),
        CallbackQueryHandler(stu_delete, pattern=r"^stu:delete:\d+$"),
        CallbackQueryHandler(stu_editmenu, pattern=r"^stu:editmenu:\d+$"),
        CallbackQueryHandler(stu_changeclass_start, pattern=r"^stu:changeclass:\d+$"),
        CallbackQueryHandler(stu_changeclass_confirm, pattern=r"^stuchcls:\d+:\d+$"),
        CallbackQueryHandler(tch_list, pattern=r"^tch:list:\d+$"),
        CallbackQueryHandler(tch_view, pattern=r"^tch:view:\d+$"),
        CallbackQueryHandler(tch_remove, pattern=r"^tch:remove:\d+$"),
        CallbackQueryHandler(tch_editclasses_start, pattern=r"^tch:editclasses:\d+$"),
        CallbackQueryHandler(tch_editclasses_toggle, pattern=r"^tcheditsel:"),
        CallbackQueryHandler(rep_today, pattern=r"^rep:today$"),
        CallbackQueryHandler(rep_student_view, pattern=r"^rep:studentview:\d+$"),
        CallbackQueryHandler(rep_classmonth_start, pattern=r"^rep:classmonth$"),
        CallbackQueryHandler(rep_classmonth_class, pattern=r"^repcls:\d+$"),
        CallbackQueryHandler(rep_classmonth_month, pattern=r"^repmonth:\d+:"),
        CallbackQueryHandler(rep_low_attendance, pattern=r"^rep:low$"),
    ]


def get_admin_conversations():
    return [
        class_add_conv,
        class_edit_conv,
        student_add_conv,
        student_search_conv,
        student_editfield_conv,
        teacher_add_conv,
        report_student_conv,
        broadcast_conv,
    ]
