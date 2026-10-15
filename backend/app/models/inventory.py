from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RecordMixin


class InventoryBalance(RecordMixin, Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (
        UniqueConstraint("product_id", "location_id"),
        CheckConstraint("on_hand_qty >= 0", name="nonnegative_on_hand"),
        CheckConstraint("reserved_qty >= 0", name="nonnegative_reserved"),
        CheckConstraint(
            "reserved_qty <= on_hand_qty",
            name="reserved_within_stock",
        ),
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    location_id: Mapped[UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT")
    )
    on_hand_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    reserved_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_system: Mapped[str] = mapped_column(String(64))
    source_version: Mapped[str] = mapped_column(String(128))