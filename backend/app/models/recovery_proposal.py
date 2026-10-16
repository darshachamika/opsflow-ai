from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RecordMixin


class RecoveryProposal(RecordMixin, Base):
    __tablename__ = "recovery_proposals"

    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="RESTRICT"),
        nullable=False,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    action_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PROPOSED",
        server_default="PROPOSED",
    )

    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    plan_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=True),
        nullable=False,
    )

    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=True),
        nullable=False,
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    request_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "uq_recovery_proposals_one_approved_incident", "incident_id",
            unique=True, postgresql_where=text("status = 'APPROVED'"),
        ),
        UniqueConstraint("incident_id", "version"),
        UniqueConstraint("incident_id", "idempotency_key"),
        CheckConstraint(
            "version > 0",
            name="positive_version",
        ),
        CheckConstraint(
            "action_type IN ('WAREHOUSE_TRANSFER', 'SUPPLIER_PURCHASE')",
            name="valid_action_type",
        ),
        CheckConstraint(
            "status IN "
            "('PROPOSED', 'APPROVED', 'REJECTED', 'SUPERSEDED', 'EXPIRED')",
            name="valid_status",
        ),
        CheckConstraint(
            "expires_at > assessed_at",
            name="valid_time_window",
        ),
        CheckConstraint(
            "jsonb_typeof(plan_snapshot) = 'object'",
            name="plan_is_object",
        ),
        CheckConstraint(
            "jsonb_typeof(evidence_snapshot) = 'object'",
            name="evidence_is_object",
        ),
        CheckConstraint(
            "(idempotency_key IS NULL AND request_hash IS NULL) OR "
            "(idempotency_key IS NOT NULL AND request_hash IS NOT NULL "
            "AND length(trim(idempotency_key)) > 0 "
            "AND request_hash ~ '^[0-9a-f]{64}$')",
            name="valid_idempotency_fields",
        ),
        Index(
            "ix_recovery_proposals_status_expires_at",
            "status",
            "expires_at",
        ),
    )
