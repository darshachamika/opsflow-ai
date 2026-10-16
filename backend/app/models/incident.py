from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RecordMixin


class Incident(RecordMixin, Base):
    __tablename__ = "incidents"

    source_system: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    source_ref: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plant_id: Mapped[UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OPEN",
        server_default="OPEN",
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("source_system", "source_ref"),
        CheckConstraint(
            "status IN ('OPEN', 'INVESTIGATING', 'RESOLVED', 'CANCELLED')",
            name="valid_status",
        ),
        CheckConstraint(
            "length(trim(title)) > 0",
            name="nonempty_title",
        ),
        Index(
            "ix_incidents_plant_product_status",
            "plant_id",
            "product_id",
            "status",
        ),
        Index("ix_incidents_product_id", "product_id"),
    )