from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RecordMixin


class Location(RecordMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint(
            "type IN ('PLANT', 'WAREHOUSE')",
            name="valid_type",
        ),
    )

    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(20))