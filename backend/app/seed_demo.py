from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import (
    InventoryBalance,
    Location,
    Product,
    ProductionDemand,
    PurchaseOrder,
    PurchaseOrderLine,
    Shipment,
    ShipmentLine,
    Supplier,
    SupplierOffer,
)


DEMO_NAMESPACE = UUID("902cff87-8eef-49c8-8b18-b10485888140")


def demo_id(name: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, name)


def seed_demo() -> None:
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        with session.begin():
            existing = session.get(Product, demo_id("product"))

            if existing is not None:
                print("Sri Lankan demo already exists. No changes made.")
                return

            # Avoid accidentally attaching demo data to an existing SKU.
            existing_sku = session.scalar(
                select(Product).where(Product.sku == "FAN-MOTOR-45W")
            )
            if existing_sku is not None:
                raise RuntimeError(
                    "SKU FAN-MOTOR-45W already exists with a different ID."
                )

            product = Product(
                id=demo_id("product"),
                sku="FAN-MOTOR-45W",
                name="Electric Fan Motor — 45W",
                unit_of_measure="UNIT",
                is_active=True,
            )

            homagama = Location(
                id=demo_id("homagama"),
                code="LK-HOM-PLANT",
                name="Homagama Assembly Plant",
                type="PLANT",
            )

            wattala = Location(
                id=demo_id("wattala"),
                code="LK-WAT-WH",
                name="Wattala Distribution Warehouse",
                type="WAREHOUSE",
            )

            original_supplier = Supplier(
                id=demo_id("original-supplier"),
                code="SUP-LK-001",
                name="Serendib Motor Supplies (Demo)",
                approval_status="APPROVED",
            )

            alternative_supplier = Supplier(
                id=demo_id("alternative-supplier"),
                code="SUP-LK-002",
                name="Kelani Components (Demo)",
                approval_status="APPROVED",
            )

            session.add_all(
                [
                    product,
                    homagama,
                    wattala,
                    original_supplier,
                    alternative_supplier,
                ]
            )
            session.flush()

            session.add_all(
                [
                    InventoryBalance(
                        id=demo_id("homagama-stock"),
                        product_id=product.id,
                        location_id=homagama.id,
                        on_hand_qty=Decimal("120"),
                        reserved_qty=Decimal("0"),
                        observed_at=now,
                        source_system="DEMO_WMS",
                        source_version="1",
                    ),
                    InventoryBalance(
                        id=demo_id("wattala-stock"),
                        product_id=product.id,
                        location_id=wattala.id,
                        on_hand_qty=Decimal("400"),
                        reserved_qty=Decimal("20"),
                        observed_at=now,
                        source_system="DEMO_WMS",
                        source_version="1",
                    ),
                    SupplierOffer(
                        id=demo_id("alternative-offer"),
                        supplier_id=alternative_supplier.id,
                        product_id=product.id,
                        unit_price=Decimal("2100.0000"),
                        currency="LKR",
                        available_qty=Decimal("600"),
                        lead_time_hours=7,
                        observed_at=now,
                        valid_until=now + timedelta(hours=24),
                    ),
                    ProductionDemand(
                        id=demo_id("production-demand"),
                        source_system="DEMO_ERP",
                        source_ref="DEMAND-DEMO-LK-001",
                        plant_id=homagama.id,
                        product_id=product.id,
                        required_qty=Decimal("500"),
                        fulfilled_qty=Decimal("0"),
                        required_at=now + timedelta(hours=8),
                        status="OPEN",
                    ),
                ]
            )

            purchase_order = PurchaseOrder(
                id=demo_id("purchase-order"),
                source_system="DEMO_ERP",
                external_id="PO-DEMO-LK-001",
                supplier_id=original_supplier.id,
                destination_id=homagama.id,
                status="CONFIRMED",
                currency="LKR",
                expected_at=now + timedelta(hours=4),
            )
            session.add(purchase_order)
            session.flush()

            order_line = PurchaseOrderLine(
                id=demo_id("purchase-order-line"),
                purchase_order_id=purchase_order.id,
                line_number=1,
                product_id=product.id,
                quantity=Decimal("500"),
                unit_price=Decimal("2000.0000"),
            )
            session.add(order_line)
            session.flush()

            shipment = Shipment(
                id=demo_id("shipment"),
                source_system="DEMO_CARRIER",
                external_id="SHP-DEMO-LK-001",
                destination_id=homagama.id,
                status="DELAYED",
                original_eta=now + timedelta(hours=4),
                current_eta=now + timedelta(hours=72),
                observed_at=now,
            )
            session.add(shipment)
            session.flush()

            session.add(
                ShipmentLine(
                    id=demo_id("shipment-line"),
                    shipment_id=shipment.id,
                    purchase_order_line_id=order_line.id,
                    quantity=Decimal("500"),
                )
            )

    print("Sri Lankan demo saved successfully.")
    print("Homagama: 120 on hand, 0 reserved.")
    print("Wattala: 400 on hand, 20 reserved.")
    print("Production demand: 500 units due in 8 hours.")
    print("Delayed shipment: 500 units arriving in 72 hours.")
    print("All timestamps are relative to this first seed run.")


if __name__ == "__main__":
    try:
        seed_demo()
    finally:
        engine.dispose()