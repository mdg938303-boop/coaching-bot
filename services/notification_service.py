"""
services/notification_service.py
অভিভাবককে Telegram-এ মেসেজ পাঠানোর লজিক, এবং Admin Settings-এ Direct SMS
চালু থাকলে + guardian_phone সেট থাকলে সরাসরি SIM-এ SMS-ও পাঠায় (Telegram-এর
পাশাপাশি, বিকল্প হিসেবে নয়)। ব্যর্থ হলে silently ignore হয় কিন্তু Activity
Log-এ noted থাকে।
"""
from sqlalchemy import select
from telegram import Bot
from telegram.error import Forbidden, TelegramError

from database.models import ActivityLog, GuardianStudentLink, Student
from services.sms_service import send_sms
from utils.helpers import format_date, format_month, is_sms_enabled
from config import logger


async def _notify_via_telegram(bot: Bot, session, student: Student, text: str) -> bool:
    """Linked guardian-দের Telegram-এ পাঠায়। কমপক্ষে একজনকে পাঠাতে পারলে True।"""
    result = await session.execute(
        select(GuardianStudentLink).where(GuardianStudentLink.student_id == student.id)
    )
    links = result.scalars().all()

    any_success = False
    for link in links:
        try:
            await bot.send_message(chat_id=link.guardian_id, text=text)
            any_success = True
        except Forbidden:
            logger.warning(f"Guardian {link.guardian_id} has blocked the bot.")
            session.add(
                ActivityLog(
                    actor_id=link.guardian_id,
                    action="notification_failed_blocked",
                    details=f"student_id={student.id}",
                )
            )
        except TelegramError as e:
            logger.warning(f"Failed to notify guardian {link.guardian_id}: {e}")
            session.add(
                ActivityLog(
                    actor_id=link.guardian_id,
                    action="notification_failed",
                    details=f"student_id={student.id} error={e}",
                )
            )
    return any_success


async def _maybe_send_sms(session, student: Student, text: str, tag: str) -> bool:
    """Settings-এ SMS চালু থাকলে এবং guardian_phone সেট থাকলে সরাসরি SMS পাঠায়।"""
    if not student.guardian_phone or not await is_sms_enabled(session):
        return False
    sms_sent = await send_sms(student.guardian_phone, text)
    session.add(
        ActivityLog(
            actor_id=0,
            action=f"sms_{tag}_sent" if sms_sent else f"sms_{tag}_failed",
            details=f"student_id={student.id} phone={student.guardian_phone}",
        )
    )
    return sms_sent


async def notify_guardian_absence(bot: Bot, session, student: Student, attendance_date) -> bool:
    """
    একজন Student Absent হলে Telegram-এ Linked guardian-দের, এবং Settings-এ
    Direct SMS চালু থাকলে সরাসরি SIM-এও নোটিফিকেশন পাঠায়। যেকোনো একটা চ্যানেল
    সফল হলেই True রিটার্ন করে (Attendance flow-এর "unnotified" তালিকায়
    ভুলবশত না ঢোকার জন্য)।
    """
    text = (
        "🔴 হাজিরা বিজ্ঞপ্তি\n\n"
        f"আপনার সন্তান {student.name} (Roll: {student.roll_number}, "
        f"Class: {student.classroom.name}) আজ ({format_date(attendance_date)}) "
        "ক্লাসে অনুপস্থিত ছিল।\n\n"
        "কোনো সমস্যা থাকলে কোচিং সেন্টারে যোগাযোগ করুন।"
    )
    telegram_sent = await _notify_via_telegram(bot, session, student, text)
    sms_sent = await _maybe_send_sms(session, student, text, "absence")
    return telegram_sent or sms_sent


async def notify_guardian_fee_due(bot: Bot, session, student: Student, month: str, due_amount: int) -> bool:
    """
    কোনো Student-এর নির্দিষ্ট মাসের ফি বকেয়া থাকলে Telegram-এ Linked
    guardian-দের, এবং Settings-এ Direct SMS চালু থাকলে সরাসরি SIM-এও Due
    Reminder পাঠায়। যেকোনো একটা চ্যানেল সফল হলেই True রিটার্ন করে।
    """
    text = (
        "💰 ফি বকেয়া বিজ্ঞপ্তি\n\n"
        f"আপনার সন্তান {student.name} (Roll: {student.roll_number}, "
        f"Class: {student.classroom.name})-এর {format_month(month)} মাসের "
        f"বেতন বকেয়া আছে।\n\n"
        f"বকেয়া পরিমাণ: {due_amount} টাকা\n\n"
        "দয়া করে যত দ্রুত সম্ভব কোচিং সেন্টারে পরিশোধ করুন।"
    )
    telegram_sent = await _notify_via_telegram(bot, session, student, text)
    sms_sent = await _maybe_send_sms(session, student, text, "fee_due")
    return telegram_sent or sms_sent
