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


class ProductionDemand(RecordMixin, Base):
    __tablename__ = "production_demands"
    __table_args__ = (
        UniqueConstraint("source_system", "source_ref"),
        CheckConstraint("required_qty > 0", name="positive_required_qty"),
        CheckConstraint("fulfilled_qty >= 0", name="nonnegative_fulfilled_qty"),
        CheckConstraint(
            "fulfilled_qty <= required_qty",
            name="fulfilled_within_required",
        ),
        CheckConstraint(
            "status IN "
            "('OPEN', 'PARTIALLY_FULFILLED', 'FULFILLED', 'CANCELLED')",
            name="valid_status",
        ),
        Index(
            "ix_production_demands_plant_product_required_at",
            "plant_id",
            "product_id",
            "required_at",
        ),
        Index("ix_production_demands_product_id", "product_id"),
    )

    source_system: Mapped[str] = mapped_column(String(64))
    source_ref: Mapped[str] = mapped_column(String(128))
    plant_id: Mapped[UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT")
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    required_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    fulfilled_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        server_default="0",
    )
    required_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), server_default="OPEN")