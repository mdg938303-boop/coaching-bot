"""
services/notification_service.py
অভিভাবককে Telegram মেসেজ পাঠানোর লজিক। ব্যর্থ হলে silently ignore হয় কিন্তু
Activity Log-এ noted থাকে।
"""
from telegram import Bot
from telegram.error import Forbidden, TelegramError

from database.models import ActivityLog, GuardianStudentLink, Student
from utils.helpers import format_date
from config import logger


async def notify_guardian_absence(bot: Bot, session, student: Student, attendance_date) -> bool:
    """
    একজন Student Absent হলে তার সব Linked Guardian-কে নোটিফিকেশন পাঠায়।
    কমপক্ষে একজন guardian-কে সফলভাবে পাঠাতে পারলে True রিটার্ন করে।
    """
    from sqlalchemy import select

    result = await session.execute(
        select(GuardianStudentLink).where(GuardianStudentLink.student_id == student.id)
    )
    links = result.scalars().all()

    if not links:
        return False

    text = (
        "🔴 হাজিরা বিজ্ঞপ্তি\n\n"
        f"আপনার সন্তান {student.name} (Roll: {student.roll_number}, "
        f"Class: {student.classroom.name}) আজ ({format_date(attendance_date)}) "
        "ক্লাসে অনুপস্থিত ছিল।\n\n"
        "কোনো সমস্যা থাকলে কোচিং সেন্টারে যোগাযোগ করুন।"
    )

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
