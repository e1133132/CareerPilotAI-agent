from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    salt: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserMemoryRow(Base):
    __tablename__ = "user_memory"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preferred_target_roles: Mapped[list] = mapped_column(JSON, default=list)
    rejected_job_ids: Mapped[list] = mapped_column(JSON, default=list)
    saved_job_ids: Mapped[list] = mapped_column(JSON, default=list)
    run_history: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
