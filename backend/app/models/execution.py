from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, RecordMixin


class RecoveryExecution(RecordMixin, Base):
    __tablename__ = "recovery_executions"
    proposal_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_proposals.id", ondelete="RESTRICT"), nullable=False, unique=True)
    decision_id: Mapped[UUID] = mapped_column(ForeignKey("approval_decisions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("approval_resume_jobs.id", ondelete="RESTRICT"), nullable=False, unique=True)
    execution_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB(none_as_null=True), nullable=False)
    __table_args__ = (
        CheckConstraint("status IN ('RUNNING', 'SUCCEEDED', 'FAILED')", name="valid_status"),
        CheckConstraint("proposal_hash ~ '^[0-9a-f]{64}$'", name="valid_proposal_hash"),
        CheckConstraint("jsonb_typeof(result) = 'object'", name="result_is_object"),
    )


class RecoveryReservation(RecordMixin, Base):
    __tablename__ = "recovery_reservations"
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_executions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    inventory_balance_id: Mapped[UUID | None] = mapped_column(ForeignKey("inventory_balances.id", ondelete="RESTRICT"))
    supplier_offer_id: Mapped[UUID | None] = mapped_column(ForeignKey("supplier_offers.id", ondelete="RESTRICT"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE")
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("(inventory_balance_id IS NOT NULL) <> (supplier_offer_id IS NOT NULL)", name="one_supply_source"),
        CheckConstraint("status IN ('ACTIVE', 'RELEASED', 'CONSUMED')", name="valid_status"),
    )


class RecoveryDemandClaim(RecordMixin, Base):
    __tablename__ = "recovery_demand_claims"
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_executions.id", ondelete="RESTRICT"), nullable=False)
    demand_id: Mapped[UUID] = mapped_column(ForeignKey("production_demands.id", ondelete="RESTRICT"), nullable=False, unique=True)
    # Conservative MVP: an accepted order owns this demand until a receipt/cancellation workflow exists.


class MockERPOrder(RecordMixin, Base):
    __tablename__ = "mock_erp_orders"
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("recovery_executions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    execution_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    external_ref: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB(none_as_null=True), nullable=False)
    __table_args__ = (
        CheckConstraint("action_type IN ('WAREHOUSE_TRANSFER', 'SUPPLIER_PURCHASE')", name="valid_action_type"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="valid_payload_hash"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_is_object"),
    )
