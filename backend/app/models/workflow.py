from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, RecordMixin


class WorkflowRun(RecordMixin, Base):
    __tablename__ = "workflow_runs"
    incident_id: Mapped[UUID] = mapped_column(ForeignKey("incidents.id", ondelete="RESTRICT"))
    requested_by: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), server_default="RUNNING")
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB(none_as_null=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("requested_by", "idempotency_key"),
        CheckConstraint("status IN ('RUNNING', 'SUCCEEDED', 'FAILED')", name="valid_status"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="valid_request_hash"),
        CheckConstraint("jsonb_typeof(inputs) = 'object'", name="inputs_object"),
        CheckConstraint("result IS NULL OR jsonb_typeof(result) = 'object'", name="result_object"),
        CheckConstraint("(status = 'RUNNING' AND completed_at IS NULL AND error_code IS NULL) OR (status = 'SUCCEEDED' AND completed_at IS NOT NULL AND result IS NOT NULL AND error_code IS NULL) OR (status = 'FAILED' AND completed_at IS NOT NULL AND error_code IS NOT NULL)", name="valid_lifecycle"),
        Index("ix_workflow_runs_incident_created", "incident_id", "created_at", "id"),
    )


class WorkflowStep(RecordMixin, Base):
    __tablename__ = "workflow_steps"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("workflow_runs.id", ondelete="RESTRICT"))
    sequence: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("run_id", "sequence"),
        CheckConstraint("sequence > 0", name="positive_sequence"),
        CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="valid_status"),
    )
