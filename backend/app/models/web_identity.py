"""Local single-organization login identities; roles are provisioned by an admin."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class WebUser(Base):
    __tablename__ = 'web_users'
    subject: Mapped[str] = mapped_column(String(128), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("role IN ('OPERATOR','PROCUREMENT_MANAGER','ADMIN')", name='valid_role'),
        CheckConstraint('failed_attempts >= 0', name='nonnegative_failed_attempts'),
    )

class WebSession(Base):
    __tablename__ = 'web_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject: Mapped[str] = mapped_column(ForeignKey('web_users.subject', ondelete='CASCADE'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
