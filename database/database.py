"""
database/database.py
Async engine, session factory এবং init_db().
"""
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import DATABASE_URL, logger
from database.models import Base

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


def _get_student_columns(sync_conn) -> list[str]:
    insp = inspect(sync_conn)
    if "students" not in insp.get_table_names():
        return []
    return [c["name"] for c in insp.get_columns("students")]


async def _ensure_fee_column():
    """
    আগে থেকে ডিপ্লয় করা ডাটাবেসে `create_all` নতুন কলাম যোগ করে না (শুধু নতুন
    টেবিল তৈরি করে), তাই Fee সিস্টেম চালু করার সময় students টেবিলে
    monthly_fee কলাম না থাকলে এখানে সেটা ALTER TABLE দিয়ে যোগ করে দেওয়া হয়।
    """
    async with engine.begin() as conn:
        columns = await conn.run_sync(_get_student_columns)
        if columns and "monthly_fee" not in columns:
            await conn.execute(
                text("ALTER TABLE students ADD COLUMN monthly_fee INTEGER DEFAULT 0")
            )
            logger.info("✅ Migrated: added 'monthly_fee' column to students table.")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_fee_column()
    logger.info("✅ Database initialized (tables ensured).")


@asynccontextmanager
async def get_session():
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
