from sqlalchemy import String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RecordMixin


class Product(RecordMixin, Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    unit_of_measure: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(server_default=true())