from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RecordMixin


class ApprovalDecision(RecordMixin, Base):
    __tablename__ = "approval_decisions"
    proposal_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_proposals.id", ondelete="RESTRICT"), nullable=False)
    manager_subject: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revalidation_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB(none_as_null=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("proposal_id"),
        UniqueConstraint("manager_subject", "idempotency_key"),
        CheckConstraint("decision IN ('APPROVED', 'REJECTED')", name="valid_decision"),
        CheckConstraint("length(trim(reason)) > 0", name="nonblank_reason"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$' AND proposal_hash ~ '^[0-9a-f]{64}$'", name="valid_hashes"),
        CheckConstraint("jsonb_typeof(revalidation_snapshot) = 'object'", name="revalidation_is_object"),
    )


class ApprovalResumeJob(RecordMixin, Base):
    __tablename__ = "approval_resume_jobs"
    decision_id: Mapped[UUID] = mapped_column(ForeignKey("approval_decisions.id", ondelete="RESTRICT"), nullable=False)
    proposal_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_proposals.id", ondelete="RESTRICT"), nullable=False)
    execution_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB(none_as_null=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("decision_id"), UniqueConstraint("proposal_id"), UniqueConstraint("execution_key"),
        CheckConstraint("status IN ('PENDING', 'CLAIMED', 'COMPLETED', 'FAILED', 'CANCELLED')", name="valid_status"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_is_object"),
    )


@event.listens_for(ApprovalDecision, "before_update")
@event.listens_for(ApprovalDecision, "before_delete")
def prevent_decision_mutation(mapper, connection, target):
    raise ValueError("Approval decisions are append-only; create a new proposal for a new decision.")
