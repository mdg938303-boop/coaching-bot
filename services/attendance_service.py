"""
services/attendance_service.py
Attendance atomic ভাবে সেভ করা এবং Absent Student-দের জন্য notification
trigger করার লজিক।
"""
import datetime as dt

from sqlalchemy import delete, select
from telegram import Bot

from database.models import (
    AttendanceEntry, AttendanceRecord, AttendanceStatus, Student
)
from services.notification_service import notify_guardian_absence
from utils.helpers import log_activity


async def get_existing_record(session, class_id: int, attendance_date: dt.date):
    result = await session.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.class_id == class_id,
            AttendanceRecord.attendance_date == attendance_date,
        )
    )
    return result.scalar_one_or_none()


async def submit_attendance(
    session,
    bot: Bot,
    class_id: int,
    attendance_date: dt.date,
    status_map: dict[int, str],  # student_id -> "PRESENT"/"ABSENT"
    actor_id: int,
) -> dict:
    """
    একটা Class + তারিখের হাজিরা atomic transaction-এ সেভ করে।
    আগে থেকে রেকর্ড থাকলে তার entries replace হয় (নতুন duplicate তৈরি হয় না)।
    Absent Student-দের guardian-কে notification পাঠায়।
    সামারি dict রিটার্ন করে: {present, absent, unnotified: [student names]}
    """
    existing = await get_existing_record(session, class_id, attendance_date)

    if existing:
        record = existing
        record.created_by = actor_id
        await session.execute(
            delete(AttendanceEntry).where(AttendanceEntry.attendance_record_id == record.id)
        )
    else:
        record = AttendanceRecord(
            class_id=class_id, attendance_date=attendance_date, created_by=actor_id
        )
        session.add(record)
        await session.flush()  # record.id পেতে

    present_count = 0
    absent_count = 0
    unnotified_names = []

    student_ids = list(status_map.keys())
    result = await session.execute(select(Student).where(Student.id.in_(student_ids)))
    students_by_id = {s.id: s for s in result.scalars().all()}

    absent_students = []
    for sid, status in status_map.items():
        entry = AttendanceEntry(
            attendance_record_id=record.id,
            student_id=sid,
            status=AttendanceStatus(status),
            notified=False,
        )
        session.add(entry)
        if status == "PRESENT":
            present_count += 1
        else:
            absent_count += 1
            absent_students.append((sid, entry))

    await session.commit()

    # notification পাঠানো (commit-এর পরে, যাতে attendance সেভ atomic থাকে
    # এবং notification-এর ব্যর্থতা attendance সেভে প্রভাব না ফেলে)
    for sid, entry in absent_students:
        student = students_by_id.get(sid)
        if not student:
            continue
        await session.refresh(student, attribute_names=["classroom"])
        sent = await notify_guardian_absence(bot, session, student, attendance_date)
        if sent:
            entry.notified = True
        else:
            unnotified_names.append((student.name, student.guardian_access_code))
        session.add(entry)

    await session.commit()

    await log_activity(
        session, actor_id, "submit_attendance",
        f"class_id={class_id} date={attendance_date} present={present_count} absent={absent_count}",
    )

    return {
        "present": present_count,
        "absent": absent_count,
        "unnotified": unnotified_names,
        "was_update": existing is not None,
    }
