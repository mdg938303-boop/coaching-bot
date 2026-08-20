"""
utils/helpers.py
Access code generator, permission checks, তারিখ পার্সিং, activity log হেল্পার।
"""
import datetime as dt
import random
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import ADMIN_IDS
from database.models import ActivityLog, Student, Teacher, TeacherClassAssignment

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # ambiguous char বাদ (0,O,1,I,L)


def generate_access_code(length: int = 8) -> str:
    return "".join(random.choices(CODE_ALPHABET, k=length))


async def unique_access_code(session: AsyncSession, length: int = 8) -> str:
    while True:
        code = generate_access_code(length)
        result = await session.execute(
            select(Student).where(Student.guardian_access_code == code)
        )
        if result.scalar_one_or_none() is None:
            return code


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def is_teacher(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(Teacher).where(Teacher.id == user_id))
    return result.scalar_one_or_none() is not None


async def get_teacher_class_ids(session: AsyncSession, teacher_id: int) -> list[int]:
    result = await session.execute(
        select(TeacherClassAssignment.class_id).where(
            TeacherClassAssignment.teacher_id == teacher_id
        )
    )
    return [row[0] for row in result.all()]


async def log_activity(session: AsyncSession, actor_id: int, action: str, details: str = ""):
    session.add(ActivityLog(actor_id=actor_id, action=action, details=details))
    await session.commit()


def parse_date_bn(text: str) -> dt.date | None:
    """DD-MM-YYYY অথবা YYYY-MM-DD ফরম্যাট সাপোর্ট করে।"""
    text = text.strip()
    fmts = ["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]
    for f in fmts:
        try:
            return dt.datetime.strptime(text, f).date()
        except ValueError:
            continue
    return None


def format_date(d: dt.date) -> str:
    return d.strftime("%d-%m-%Y")


def percentage(present: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round((present / total) * 100, 1)
