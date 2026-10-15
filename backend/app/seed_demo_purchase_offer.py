from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Product, Supplier, SupplierOffer


DEMO_OFFER_ID = uuid5(
    UUID("60263a43-dbf4-44cb-97bb-86214c31d187"),
    "fresh-demo-purchase-offer",
)


def seed_demo_purchase_offer() -> None:
    with Session(engine) as session:
        with session.begin():
            product = session.scalar(
                select(Product).where(
                    Product.sku == "FAN-MOTOR-45W"
                )
            )
            supplier = session.scalar(
                select(Supplier).where(
                    Supplier.code == "SUP-LK-002"
                )
            )

            if product is None or supplier is None:
                raise RuntimeError("Original demo product/supplier is missing.")

            if supplier.approval_status != "APPROVED":
                raise RuntimeError("Demo supplier must be approved.")

            offer = session.get(SupplierOffer, DEMO_OFFER_ID)

            if offer is None:
                offer = SupplierOffer(
                    id=DEMO_OFFER_ID,
                    supplier_id=supplier.id,
                    product_id=product.id,
                )
                session.add(offer)
            elif (
                offer.supplier_id != supplier.id
                or offer.product_id != product.id
            ):
                raise RuntimeError("Demo offer identity does not match.")

            now = datetime.now(timezone.utc)

            offer.unit_price = Decimal("2100.0000")
            offer.currency = "LKR"
            offer.available_qty = Decimal("600.000")
            offer.lead_time_hours = 7
            offer.observed_at = now
            offer.valid_until = now + timedelta(hours=24)

        print("Fictional demo purchase offer created/reset.")
        print(f"Offer ID: {DEMO_OFFER_ID}")


if __name__ == "__main__":
    try:
        seed_demo_purchase_offer()
    finally:
        engine.dispose()