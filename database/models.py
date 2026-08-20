"""
database/models.py
সব টেবিলের SQLAlchemy ORM মডেল।
"""
import enum
import datetime as dt

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String,
    Text, UniqueConstraint, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"


class ClassRoom(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    schedule_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    students: Mapped[list["Student"]] = relationship(back_populates="classroom")
    teacher_links: Mapped[list["TeacherClassAssignment"]] = relationship(back_populates="classroom")
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(back_populates="classroom")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("class_id", "roll_number", name="uq_student_class_roll"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    roll_number: Mapped[str] = mapped_column(String(30), nullable=False)
    guardian_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admission_date: Mapped[dt.date] = mapped_column(Date, default=dt.date.today)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    guardian_access_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    classroom: Mapped["ClassRoom"] = relationship(back_populates="students")
    guardian_links: Mapped[list["GuardianStudentLink"]] = relationship(back_populates="student")
    attendance_entries: Mapped[list["AttendanceEntry"]] = relationship(back_populates="student")


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram user id
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    class_links: Mapped[list["TeacherClassAssignment"]] = relationship(back_populates="teacher")


class TeacherClassAssignment(Base):
    __tablename__ = "teacher_class_assignments"
    __table_args__ = (
        UniqueConstraint("teacher_id", "class_id", name="uq_teacher_class"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)

    teacher: Mapped["Teacher"] = relationship(back_populates="class_links")
    classroom: Mapped["ClassRoom"] = relationship(back_populates="teacher_links")


class Guardian(Base):
    __tablename__ = "guardians"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram user id
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student_links: Mapped[list["GuardianStudentLink"]] = relationship(back_populates="guardian")


class GuardianStudentLink(Base):
    __tablename__ = "guardian_student_links"
    __table_args__ = (
        UniqueConstraint("guardian_id", "student_id", name="uq_guardian_student"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guardian_id: Mapped[int] = mapped_column(ForeignKey("guardians.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    linked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    guardian: Mapped["Guardian"] = relationship(back_populates="student_links")
    student: Mapped["Student"] = relationship(back_populates="guardian_links")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("class_id", "attendance_date", name="uq_class_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    attendance_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    classroom: Mapped["ClassRoom"] = relationship(back_populates="attendance_records")
    entries: Mapped[list["AttendanceEntry"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class AttendanceEntry(Base):
    __tablename__ = "attendance_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attendance_record_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_records.id"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(Enum(AttendanceStatus), nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    record: Mapped["AttendanceRecord"] = relationship(back_populates="entries")
    student: Mapped["Student"] = relationship(back_populates="attendance_entries")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
