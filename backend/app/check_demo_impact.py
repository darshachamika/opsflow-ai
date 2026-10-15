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
)
from app.services.inbound import InboundSupply, calculate_inbound_impact


def check_demo_impact() -> None:
    with Session(engine) as session:
        demand = session.scalar(
            select(ProductionDemand).where(
                ProductionDemand.source_system == "DEMO_ERP",
                ProductionDemand.source_ref == "DEMAND-DEMO-LK-001",
            )
        )

        if demand is None:
            raise RuntimeError("Demo demand not found. Run app.seed_demo first.")

        if demand.status not in ("OPEN", "PARTIALLY_FULFILLED"):
            raise RuntimeError("Demo demand is not open for impact analysis.")

        plant = session.get(Location, demand.plant_id)
        product = session.get(Product, demand.product_id)

        if plant is None or plant.type != "PLANT":
            raise RuntimeError("Demand must reference a valid plant.")

        if product is None:
            raise RuntimeError("Demand product was not found.")

        balance = session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == demand.product_id,
                InventoryBalance.location_id == demand.plant_id,
            )
        )

        if balance is None:
            raise RuntimeError(
                "Inventory evidence is missing; cannot calculate shortage."
            )

        shipment_rows = session.execute(
            select(ShipmentLine, Shipment, PurchaseOrder)
            .join(
                Shipment,
                ShipmentLine.shipment_id == Shipment.id,
            )
            .join(
                PurchaseOrderLine,
                ShipmentLine.purchase_order_line_id == PurchaseOrderLine.id,
            )
            .join(
                PurchaseOrder,
                PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
            )
            .where(
                PurchaseOrderLine.product_id == demand.product_id,
                Shipment.destination_id == demand.plant_id,
                Shipment.status.in_(
                    ("PLANNED", "IN_TRANSIT", "DELAYED")
                ),
            )
            .order_by(
                Shipment.current_eta,
                Shipment.id,
                ShipmentLine.id,
            )
        ).all()

        inbound_supplies = []

        for line, shipment, purchase_order in shipment_rows:
            if purchase_order.destination_id != shipment.destination_id:
                raise RuntimeError(
                    f"Shipment {shipment.external_id}: "
                    "purchase order destination does not match shipment."
                )

            if purchase_order.status not in (
                "OPEN",
                "CONFIRMED",
                "PARTIALLY_RECEIVED",
            ):
                raise RuntimeError(
                    f"Shipment {shipment.external_id}: "
                    "active shipment references a closed purchase order."
                )

            inbound_supplies.append(
                InboundSupply(
                    shipment_line_id=str(line.id),
                    quantity=line.quantity,
                    current_eta=shipment.current_eta,
                    status=shipment.status,
                )
            )

        result = calculate_inbound_impact(
            required_qty=demand.required_qty,
            fulfilled_qty=demand.fulfilled_qty,
            on_hand_qty=balance.on_hand_qty,
            reserved_qty=balance.reserved_qty,
            required_at=demand.required_at,
            inbound_supplies=inbound_supplies,
        )

        print("=== DEMO INBOUND IMPACT ===")
        print(f"Plant: {plant.name}")
        print(f"SKU: {product.sku}")
        print(f"Demand reference: {demand.source_ref}")
        print(f"Required at: {demand.required_at.isoformat()}")
        print(f"Inventory observed at: {balance.observed_at.isoformat()}")

        print("\n--- Matching active shipment lines ---")

        if not shipment_rows:
            print("No matching active shipment lines.")

        for line, shipment, _ in shipment_rows:
            timing_label = (
                "ON TIME"
                if shipment.current_eta <= demand.required_at
                else "LATE"
            )

            print(
                f"{shipment.external_id} | "
                f"Line: {line.id} | "
                f"Qty: {line.quantity} | "
                f"ETA: {shipment.current_eta.isoformat()} | "
                f"{timing_label}"
            )

        print("\n--- Coverage calculation ---")
        print(f"Remaining demand: {result.remaining_demand}")
        print(f"Available stock: {result.available_stock}")
        print(f"Shortage before inbound: {result.shortage_before_inbound}")
        print(f"On-time inbound quantity: {result.on_time_inbound_qty}")
        print(f"Late inbound quantity: {result.late_inbound_qty}")
        print(f"Inbound allocated in calculation: {result.inbound_allocated_qty}")
        print(f"Shortage after inbound: {result.shortage_after_inbound}")

        print(
            "\nScope: one demand, stored snapshot, expected arrivals; "
            "no persisted reservations or freshness checks."
        )
        print(
            "Demo assumption: active shipment quantities are fully "
            "unreceived, unallocated, and usable at ETA."
        )


if __name__ == "__main__":
    try:
        check_demo_impact()
    finally:
        engine.dispose()