from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RecordMixin


class SupplierOffer(RecordMixin, Base):
    __tablename__ = "supplier_offers"
    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="nonnegative_unit_price"),
        CheckConstraint("available_qty >= 0", name="nonnegative_available_qty"),
        CheckConstraint("lead_time_hours >= 0", name="nonnegative_lead_time"),
        CheckConstraint("valid_until > observed_at", name="valid_time_window"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="currency_format",
        ),
        Index("ix_supplier_offers_product_id_valid_until", "product_id", "valid_until"),
        Index("ix_supplier_offers_supplier_id", "supplier_id"),
    )

    supplier_id: Mapped[UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT")
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3))
    available_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    lead_time_hours: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))