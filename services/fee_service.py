"""
services/fee_service.py
Fee/বেতন সংক্রান্ত হিসাব: কোনো Student-এর একটা মাসে কত পেমেন্ট এসেছে, কত
বকেয়া আছে, এবং Payment রেকর্ড করার লজিক।
"""
from sqlalchemy import func, select

from database.models import FeePayment, Student
from utils.helpers import log_activity


async def get_paid_amount(session, student_id: int, month: str) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(FeePayment.amount), 0)).where(
            FeePayment.student_id == student_id, FeePayment.month == month
        )
    )
    return int(total or 0)


async def get_fee_status(session, student: Student, month: str) -> dict:
    """
    রিটার্ন করে: {monthly_fee, paid, due, status} — status হবে
    'PAID' / 'PARTIAL' / 'DUE' / 'NO_FEE' (fee=0 হলে)।
    """
    paid = await get_paid_amount(session, student.id, month)
    fee = student.monthly_fee or 0
    due = max(fee - paid, 0)
    if fee <= 0:
        status = "NO_FEE"
    elif due == 0:
        status = "PAID"
    elif paid > 0:
        status = "PARTIAL"
    else:
        status = "DUE"
    return {"monthly_fee": fee, "paid": paid, "due": due, "status": status}


async def record_payment(
    session, student_id: int, amount: int, month: str, payment_method: str, actor_id: int
) -> FeePayment:
    payment = FeePayment(
        student_id=student_id,
        amount=amount,
        month=month,
        payment_method=payment_method,
        paid_by=actor_id,
    )
    session.add(payment)
    await session.commit()
    await log_activity(
        session, actor_id, "record_payment",
        f"student_id={student_id} amount={amount} month={month} method={payment_method}",
    )
    return payment


async def get_due_students_for_month(session, month: str) -> list[tuple]:
    """
    এই মাসে যাদের ফি (আংশিক বা সম্পূর্ণ) বকেয়া আছে এমন সব Active Student
    রিটার্ন করে: [(student, status_dict), ...]
    """
    result = await session.execute(
        select(Student).where(Student.is_active == True, Student.monthly_fee > 0)  # noqa: E712
    )
    students = result.scalars().all()
    due_list = []
    for s in students:
        status = await get_fee_status(session, s, month)
        if status["status"] in ("DUE", "PARTIAL"):
            due_list.append((s, status))
    return due_list
