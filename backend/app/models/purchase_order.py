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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RecordMixin


class PurchaseOrder(RecordMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("source_system", "external_id"),
        CheckConstraint(
            "status IN "
            "('OPEN', 'CONFIRMED', 'PARTIALLY_RECEIVED', "
            "'RECEIVED', 'CANCELLED')",
            name="valid_status",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="currency_format",
        ),
        Index("ix_purchase_orders_supplier_id", "supplier_id"),
        Index("ix_purchase_orders_destination_id", "destination_id"),
    )

    source_system: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(128))
    supplier_id: Mapped[UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT")
    )
    destination_id: Mapped[UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(3))
    expected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PurchaseOrderLine(RecordMixin, Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "line_number"),
        CheckConstraint("line_number > 0", name="positive_line_number"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_price >= 0", name="nonnegative_unit_price"),
        Index("ix_purchase_order_lines_product_id", "product_id"),
    )

    purchase_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="RESTRICT")
    )
    line_number: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))