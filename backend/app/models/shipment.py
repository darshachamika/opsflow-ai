from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RecordMixin


class Shipment(RecordMixin, Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("source_system", "external_id"),
        CheckConstraint(
            "status IN "
            "('PLANNED', 'IN_TRANSIT', 'DELAYED', 'DELIVERED', 'CANCELLED')",
            name="valid_status",
        ),
        Index("ix_shipments_destination_id", "destination_id"),
        Index("ix_shipments_status_current_eta", "status", "current_eta"),
    )

    source_system: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(128))
    destination_id: Mapped[UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(20))
    original_eta: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_eta: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ShipmentLine(RecordMixin, Base):
    __tablename__ = "shipment_lines"
    __table_args__ = (
        UniqueConstraint("shipment_id", "purchase_order_line_id"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        Index(
            "ix_shipment_lines_purchase_order_line_id",
            "purchase_order_line_id",
        ),
    )

    shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("shipments.id", ondelete="RESTRICT")
    )
    purchase_order_line_id: Mapped[UUID] = mapped_column(
        ForeignKey("purchase_order_lines.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))