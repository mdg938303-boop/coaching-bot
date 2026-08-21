"""
utils/menu_guard.py
কোনো multi-step ফর্মের (Add Class/Student/Teacher, Attendance date input,
Fee amount ইত্যাদি) মাঝখানে ব্যবহারকারী যদি ভুলবশত বা ইচ্ছাকৃতভাবে মূল
Reply Keyboard-এর কোনো মেনু বাটন চাপে (📚 Classes, 👨‍🎓 Students ইত্যাদি),
তাহলে সেই টেক্সটটা ফর্মের ইনপুট হিসেবে গিলে ফেলার বদলে — চলমান ফর্মটা বাতিল
করে সঠিক মেনু দেখানো হয় (অথবা, Take Attendance/Broadcast/Link My Child-এর
মতো যেগুলো নিজেই একটা ConversationHandler entry point, সেগুলোর ক্ষেত্রে
ব্যবহারকারীকে আবার বাটন চাপতে বলা হয়, কারণ এক conversation-এর ভেতর থেকে
অন্য conversation-এ নিরাপদে state পাঠানো যায় না)।

প্রতিটা free-text state handler-এর একদম শুরুতে এটা কল করা হয়:

    if await redirect_if_menu_button(update, context):
        return ConversationHandler.END
"""
from telegram import Update
from telegram.ext import ContextTypes


async def redirect_if_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.message or not update.message.text:
        return False
    text = update.message.text.strip()

    from keyboards import admin as akb
    from keyboards import guardian as gkb
    from handlers import nav, guardian as guardian_handlers

    # সরাসরি দেখানো যায় এমন মেনু — চলমান ফর্ম বাতিল করে সরাসরি সেই মেনু দেখাই
    direct_dispatch = {
        akb.BTN_CLASSES: nav.show_classes_menu,
        akb.BTN_STUDENTS: nav.show_students_menu,
        akb.BTN_REPORTS: nav.show_reports_menu,
        akb.BTN_TEACHERS: nav.show_teachers_menu,
        akb.BTN_FEES: nav.show_fees_menu,
        akb.BTN_LOGS: nav.show_logs,
        akb.BTN_SETTINGS: nav.show_settings_menu,
        gkb.BTN_MY_CHILDREN: guardian_handlers.my_children,
    }

    # এগুলো নিজেরাই আলাদা ConversationHandler entry point — এক ফর্মের ভেতর
    # থেকে সরাসরি ওদের শুরু করানো নিরাপদ না, তাই বাতিল করে আবার চাপতে বলি
    reentry_only = {akb.BTN_ATTENDANCE, akb.BTN_BROADCAST, gkb.BTN_LINK_CHILD}

    if text in direct_dispatch:
        context.user_data.clear()
        await direct_dispatch[text](update, context)
        return True

    if text in reentry_only:
        context.user_data.clear()
        from utils.helpers import is_admin
        await update.message.reply_text(
            "ℹ️ আগের ফর্মটি বাতিল করা হয়েছে (মেনু বাটন চাপার কারণে)। "
            "দয়া করে বাটনটি আবার চাপুন।",
            reply_markup=akb.admin_main_menu(is_admin(update.effective_user.id)),
        )
        return True

    return False
