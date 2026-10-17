from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, RecordMixin


class WorkflowJob(RecordMixin, Base):
    __tablename__ = "workflow_jobs"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("workflow_runs.id", ondelete="RESTRICT"), unique=True)
    status: Mapped[str] = mapped_column(String(20), server_default="QUEUED")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[UUID | None] = mapped_column(nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')", name="valid_status"),
        CheckConstraint("attempts >= 0 AND attempts <= 3", name="valid_attempts"),
        CheckConstraint("(status = 'RUNNING' AND lease_until IS NOT NULL AND lease_token IS NOT NULL) OR (status <> 'RUNNING' AND lease_until IS NULL AND lease_token IS NULL)", name="valid_lease"),
        Index("ix_workflow_jobs_status_available", "status", "available_at"),
        Index("ix_workflow_jobs_status_lease", "status", "lease_until"),
    )


class WorkflowAttempt(RecordMixin, Base):
    __tablename__ = "workflow_attempts"
    job_id: Mapped[UUID] = mapped_column(ForeignKey("workflow_jobs.id", ondelete="RESTRICT"))
    number: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (
        UniqueConstraint("job_id", "number"),
        CheckConstraint("number BETWEEN 1 AND 3", name="valid_number"),
        CheckConstraint("status IN ('RUNNING', 'SUCCEEDED', 'FAILED', 'LEASE_EXPIRED')", name="valid_status"),
    )
