"""
keyboards/admin.py
Admin/Teacher-এর জন্য Reply Keyboard (মূল নেভিগেশন) এবং Inline Keyboards
(item সিলেকশন, pagination, confirm/cancel)।
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

BTN_CLASSES = "📚 Classes"
BTN_STUDENTS = "👨‍🎓 Students"
BTN_ATTENDANCE = "✅ Take Attendance"
BTN_REPORTS = "📊 Attendance Reports"
BTN_TEACHERS = "👨‍🏫 Teachers"
BTN_BROADCAST = "📢 Broadcast"
BTN_LOGS = "📝 Activity Logs"
BTN_CANCEL = "❌ Cancel"
BTN_BACK = "🔙 Back"


def admin_main_menu(is_admin_user: bool) -> ReplyKeyboardMarkup:
    rows = [
        [BTN_CLASSES, BTN_STUDENTS],
        [BTN_ATTENDANCE, BTN_REPORTS],
    ]
    if is_admin_user:
        rows.append([BTN_TEACHERS, BTN_BROADCAST])
        rows.append([BTN_LOGS])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)


def classes_menu_inline() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("➕ Add Class", callback_data="cls:add")],
        [InlineKeyboardButton("📋 List Classes", callback_data="cls:list:0")],
    ]
    return InlineKeyboardMarkup(buttons)


def class_list_inline(classes, page: int, has_more: bool, prefix: str = "cls:view") -> InlineKeyboardMarkup:
    buttons = []
    for c in classes:
        status = "🟢" if c.is_active else "🔴"
        buttons.append([InlineKeyboardButton(f"{status} {c.name}", callback_data=f"{prefix}:{c.id}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cls:list:{page-1}"))
    if has_more:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"cls:list:{page+1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(buttons)


def class_detail_inline(class_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Deactivate" if is_active else "🟢 Activate"
    toggle_action = "deactivate" if is_active else "activate"
    buttons = [
        [InlineKeyboardButton("✏️ Edit Name", callback_data=f"cls:edit:{class_id}")],
        [InlineKeyboardButton(toggle_text, callback_data=f"cls:{toggle_action}:{class_id}")],
        [InlineKeyboardButton("🗑️ Delete Class", callback_data=f"cls:delete:{class_id}")],
        [InlineKeyboardButton("🔙 Back to list", callback_data="cls:list:0")],
    ]
    return InlineKeyboardMarkup(buttons)


def students_menu_inline() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("➕ Add Student", callback_data="stu:add")],
        [InlineKeyboardButton("📋 Browse by Class", callback_data="stu:byclass:0")],
        [InlineKeyboardButton("🔎 Search", callback_data="stu:search")],
    ]
    return InlineKeyboardMarkup(buttons)


def class_pick_inline(classes, prefix: str, page: int = 0, has_more: bool = False) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(c.name, callback_data=f"{prefix}:{c.id}")] for c in classes]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{prefix}page:{page-1}"))
    if has_more:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"{prefix}page:{page+1}"))
    if nav:
        buttons.append(nav)
    if not buttons:
        buttons = [[InlineKeyboardButton("❌ Cancel", callback_data="noop:cancel")]]
    return InlineKeyboardMarkup(buttons)


def student_list_inline(students, page: int, has_more: bool, class_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for s in students:
        status = "" if s.is_active else " (Inactive)"
        buttons.append(
            [InlineKeyboardButton(f"{s.roll_number} - {s.name}{status}", callback_data=f"stu:view:{s.id}")]
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"stu:byclass:{class_id}:{page-1}"))
    if has_more:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"stu:byclass:{class_id}:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="stu:byclass:0")])
    return InlineKeyboardMarkup(buttons)


def student_detail_inline(student_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Mark Inactive" if is_active else "🟢 Mark Active"
    toggle_action = "inactive" if is_active else "active"
    buttons = [
        [InlineKeyboardButton("✏️ Edit Info", callback_data=f"stu:editmenu:{student_id}")],
        [InlineKeyboardButton("🔄 Change Class", callback_data=f"stu:changeclass:{student_id}")],
        [InlineKeyboardButton(toggle_text, callback_data=f"stu:{toggle_action}:{student_id}")],
        [InlineKeyboardButton("🔁 Regenerate Access Code", callback_data=f"stu:regencode:{student_id}")],
        [InlineKeyboardButton("🗑️ Delete Student", callback_data=f"stu:delete:{student_id}")],
    ]
    return InlineKeyboardMarkup(buttons)


def student_edit_field_inline(student_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("নাম", callback_data=f"stu:editfield:{student_id}:name")],
        [InlineKeyboardButton("Roll Number", callback_data=f"stu:editfield:{student_id}:roll")],
        [InlineKeyboardButton("অভিভাবকের নম্বর", callback_data=f"stu:editfield:{student_id}:phone")],
        [InlineKeyboardButton("ঠিকানা", callback_data=f"stu:editfield:{student_id}:address")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"stu:view:{student_id}")],
    ]
    return InlineKeyboardMarkup(buttons)


def confirm_cancel_inline(confirm_cb: str, cancel_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Confirm", callback_data=confirm_cb),
          InlineKeyboardButton("❌ Cancel", callback_data=cancel_cb)]]
    )


def optional_skip_inline(skip_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Skip", callback_data=skip_cb)]])


def teachers_menu_inline() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("➕ Add Teacher", callback_data="tch:add")],
        [InlineKeyboardButton("📋 List Teachers", callback_data="tch:list:0")],
    ]
    return InlineKeyboardMarkup(buttons)


def teacher_list_inline(teachers, page, has_more) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(t.name, callback_data=f"tch:view:{t.id}")] for t in teachers]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"tch:list:{page-1}"))
    if has_more:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"tch:list:{page+1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(buttons)


def teacher_detail_inline(teacher_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("✏️ Edit Assigned Classes", callback_data=f"tch:editclasses:{teacher_id}")],
        [InlineKeyboardButton("🗑️ Remove Teacher", callback_data=f"tch:remove:{teacher_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="tch:list:0")],
    ]
    return InlineKeyboardMarkup(buttons)


def multi_class_select_inline(classes, selected_ids: set, prefix: str = "tchsel") -> InlineKeyboardMarkup:
    buttons = []
    for c in classes:
        mark = "✅" if c.id in selected_ids else "▫️"
        buttons.append([InlineKeyboardButton(f"{mark} {c.name}", callback_data=f"{prefix}:{c.id}")])
    buttons.append([InlineKeyboardButton("💾 Done", callback_data=f"{prefix}:done")])
    return InlineKeyboardMarkup(buttons)


def reports_menu_inline() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📅 আজকের হাজিরা সামারি", callback_data="rep:today")],
        [InlineKeyboardButton("👨‍🎓 Student Attendance History", callback_data="rep:student")],
        [InlineKeyboardButton("📚 Class-wise Monthly Sheet", callback_data="rep:classmonth")],
        [InlineKeyboardButton("📉 Low Attendance List", callback_data="rep:low")],
    ]
    return InlineKeyboardMarkup(buttons)


def month_pick_inline(prefix: str) -> InlineKeyboardMarkup:
    import datetime as dt
    today = dt.date.today()
    buttons = []
    row = []
    for i in range(6):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        label = dt.date(y, m, 1).strftime("%b %Y")
        row.append(InlineKeyboardButton(label, callback_data=f"{prefix}:{y}-{m:02d}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)
