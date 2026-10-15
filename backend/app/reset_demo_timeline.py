from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import (
    InventoryBalance,
    Location,
    Product,
    ProductionDemand,
    PurchaseOrder,
    Shipment,
    SupplierOffer,
)


def reset_demo_timeline() -> None:
    with Session(engine) as session:
        with session.begin():
            product = session.scalar(
                select(Product).where(Product.sku == "FAN-MOTOR-45W")
            )
            plant = session.scalar(
                select(Location).where(Location.code == "LK-HOM-PLANT")
            )

            if product is None or plant is None:
                raise RuntimeError("Original demo product or plant is missing.")

            balances = session.scalars(
                select(InventoryBalance)
                .where(
                    InventoryBalance.product_id == product.id,
                    InventoryBalance.source_system == "DEMO_WMS",
                )
                .with_for_update()
            ).all()

            plant_balance = next(
                (
                    balance
                    for balance in balances
                    if balance.location_id == plant.id
                ),
                None,
            )

            if plant_balance is None:
                raise RuntimeError("Demo plant inventory is missing.")

            demands = session.scalars(
                select(ProductionDemand)
                .where(
                    ProductionDemand.source_system == "DEMO_ERP",
                    ProductionDemand.source_ref.in_(
                        ("DEMAND-DEMO-LK-001", "DEMAND-DEMO-LK-002")
                    ),
                    ProductionDemand.product_id == product.id,
                    ProductionDemand.plant_id == plant.id,
                )
                .with_for_update()
            ).all()

            shipments = session.scalars(
                select(Shipment)
                .where(
                    Shipment.source_system == "DEMO_CARRIER",
                    Shipment.external_id.in_(
                        (
                            "SHP-DEMO-LK-001",
                            "SHP-DEMO-LK-002",
                            "SHP-DEMO-LK-003",
                        )
                    ),
                    Shipment.destination_id == plant.id,
                )
                .with_for_update()
            ).all()

            orders = session.scalars(
                select(PurchaseOrder)
                .where(
                    PurchaseOrder.source_system == "DEMO_ERP",
                    PurchaseOrder.external_id.in_(
                        ("PO-DEMO-LK-001", "PO-DEMO-LK-002")
                    ),
                    PurchaseOrder.destination_id == plant.id,
                )
                .with_for_update()
            ).all()

            if len(demands) != 2 or len(shipments) != 3 or len(orders) != 2:
                raise RuntimeError(
                    "Expected 2 demo demands, 3 shipments and 2 orders."
                )

            if any(d.status != "OPEN" for d in demands):
                raise RuntimeError("Demo demands have changed; reset aborted.")

            if any(
                s.status not in ("IN_TRANSIT", "DELAYED")
                for s in shipments
            ):
                raise RuntimeError("Demo shipments have changed; reset aborted.")

            # Move the complete scenario by one common time offset.
            new_reference = datetime.now(timezone.utc)
            offset = new_reference - plant_balance.observed_at

            for balance in balances:
                balance.observed_at += offset

            for demand in demands:
                demand.required_at += offset

            for shipment in shipments:
                shipment.original_eta += offset
                shipment.current_eta += offset
                shipment.observed_at += offset

            for order in orders:
                order.expected_at += offset

        print("Fictional demo timeline restarted.")
        print(f"Reference time: {new_reference.isoformat()}")
        print("Quantities and statuses were not changed.")


if __name__ == "__main__":
    try:
        reset_demo_timeline()
    finally:
        engine.dispose()