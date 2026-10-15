from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RecordMixin


class Supplier(RecordMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint(
            "approval_status IN ('APPROVED', 'SUSPENDED', 'PENDING')",
            name="valid_approval_status",
        ),
    )

    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    approval_status: Mapped[str] = mapped_column(
        String(20),
        server_default="PENDING",
    )