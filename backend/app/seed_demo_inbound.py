from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import (
    ProductionDemand,
    PurchaseOrder,
    PurchaseOrderLine,
    Shipment,
    ShipmentLine,
    Supplier,
)


NAMESPACE = UUID("b218b65a-e587-40b0-8770-360933f03076")


def demo_id(name: str) -> UUID:
    return uuid5(NAMESPACE, name)


def seed_demo_inbound() -> None:
    with Session(engine) as session:
        with session.begin():
            demand = session.scalar(
                select(ProductionDemand).where(
                    ProductionDemand.source_system == "DEMO_ERP",
                    ProductionDemand.source_ref == "DEMAND-DEMO-LK-001",
                )
            )

            if demand is None:
                raise RuntimeError("Run the original demo seed first.")

            supplier = session.scalar(
                select(Supplier).where(
                    Supplier.code == "SUP-LK-002"
                )
            )

            if supplier is None:
                raise RuntimeError("Demo supplier SUP-LK-002 was not found.")

            if supplier.approval_status != "APPROVED":
                raise RuntimeError("Demo supplier must be approved.")

            po_id = demo_id("replacement-po")
            po_line_id = demo_id("replacement-po-line")

            shipment_specs = (
                ("SHP-DEMO-LK-002", Decimal("200"), 2),
                ("SHP-DEMO-LK-003", Decimal("100"), 1),
            )

            expected_records = [
                (PurchaseOrder, po_id),
                (PurchaseOrderLine, po_line_id),
            ]

            for reference, _, _ in shipment_specs:
                expected_records.extend(
                    [
                        (Shipment, demo_id(reference)),
                        (ShipmentLine, demo_id(f"{reference}-line")),
                    ]
                )

            existing = [
                session.get(model, record_id) is not None
                for model, record_id in expected_records
            ]

            if all(existing):
                print("Additional demo inbound records already exist.")
                return

            if any(existing):
                raise RuntimeError(
                    "Partial demo inbound records exist. "
                    "Inspect them before reseeding."
                )

            first_eta = demand.required_at - timedelta(hours=2)
            observed_at = demand.required_at - timedelta(hours=8)

            purchase_order = PurchaseOrder(
                id=po_id,
                source_system="DEMO_ERP",
                external_id="PO-DEMO-LK-002",
                supplier_id=supplier.id,
                destination_id=demand.plant_id,
                status="CONFIRMED",
                currency="LKR",
                expected_at=first_eta,
            )
            session.add(purchase_order)
            session.flush()

            purchase_order_line = PurchaseOrderLine(
                id=po_line_id,
                purchase_order_id=po_id,
                line_number=1,
                product_id=demand.product_id,
                quantity=Decimal("300"),
                unit_price=Decimal("2100.0000"),
            )
            session.add(purchase_order_line)
            session.flush()

            for reference, quantity, hours_before in shipment_specs:
                eta = demand.required_at - timedelta(hours=hours_before)

                shipment = Shipment(
                    id=demo_id(reference),
                    source_system="DEMO_CARRIER",
                    external_id=reference,
                    destination_id=demand.plant_id,
                    status="IN_TRANSIT",
                    original_eta=eta,
                    current_eta=eta,
                    observed_at=observed_at,
                )
                session.add(shipment)
                session.flush()

                session.add(
                    ShipmentLine(
                        id=demo_id(f"{reference}-line"),
                        shipment_id=shipment.id,
                        purchase_order_line_id=po_line_id,
                        quantity=quantity,
                    )
                )

        print("Created demo purchase order PO-DEMO-LK-002.")
        print("Created on-time shipments: 200 units + 100 units.")


if __name__ == "__main__":
    try:
        seed_demo_inbound()
    finally:
        engine.dispose()