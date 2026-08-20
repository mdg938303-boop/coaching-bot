"""
keyboards/guardian.py
অভিভাবকের জন্য Reply Keyboard এবং Inline Keyboards।
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

BTN_LINK_CHILD = "🔗 Link My Child"
BTN_MY_CHILDREN = "👨‍🎓 আমার সন্তানেরা"
BTN_CANCEL = "❌ Cancel"


def guardian_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BTN_LINK_CHILD], [BTN_MY_CHILDREN]], resize_keyboard=True
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)


def children_list_inline(students) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"{s.name} ({s.classroom.name})", callback_data=f"gch:view:{s.id}")]
        for s in students
    ]
    return InlineKeyboardMarkup(buttons)


def child_detail_inline(student_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📅 Attendance History", callback_data=f"gch:history:{student_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="gch:list")],
    ]
    return InlineKeyboardMarkup(buttons)
