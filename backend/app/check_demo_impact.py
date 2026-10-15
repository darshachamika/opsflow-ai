from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import (
    InventoryBalance,
    Location,
    Product,
    ProductionDemand,
    PurchaseOrderLine,
    Shipment,
    ShipmentLine,
)
from app.services.impact import assess_shipment_timing, calculate_shortage


def check_demo_impact() -> None:
    with Session(engine) as session:
        # 1. Load the production demand.
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

        # 2. Validate the plant and product.
        plant = session.get(Location, demand.plant_id)
        product = session.get(Product, demand.product_id)

        if plant is None or plant.type != "PLANT":
            raise RuntimeError("Demand must reference a valid plant.")

        if product is None:
            raise RuntimeError("Demand product was not found.")

        # 3. Load inventory evidence.
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

        # 4. Calculate the shortage using stored stock.
        result = calculate_shortage(
            required_qty=demand.required_qty,
            fulfilled_qty=demand.fulfilled_qty,
            on_hand_qty=balance.on_hand_qty,
            reserved_qty=balance.reserved_qty,
        )

        # 5. Load and validate the selected inbound shipment.
        shipment = session.scalar(
            select(Shipment).where(
                Shipment.source_system == "DEMO_CARRIER",
                Shipment.external_id == "SHP-DEMO-LK-001",
            )
        )

        if shipment is None:
            raise RuntimeError("Demo shipment was not found.")

        if shipment.destination_id != demand.plant_id:
            raise RuntimeError("Shipment destination does not match the plant.")

        if shipment.status not in ("PLANNED", "IN_TRANSIT", "DELAYED"):
            raise RuntimeError("Shipment is not an active inbound shipment.")

        matching_line = session.scalar(
            select(ShipmentLine)
            .join(
                PurchaseOrderLine,
                ShipmentLine.purchase_order_line_id == PurchaseOrderLine.id,
            )
            .where(
                ShipmentLine.shipment_id == shipment.id,
                PurchaseOrderLine.product_id == demand.product_id,
            )
        )

        if matching_line is None:
            raise RuntimeError("Shipment does not contain the demanded product.")

        # 6. Compare the shipment ETA with the demand deadline.
        timing = assess_shipment_timing(
            current_eta=shipment.current_eta,
            required_at=demand.required_at,
        )

        # 7. Display the results.
        print("=== DEMO SNAPSHOT IMPACT ===")
        print(f"Plant: {plant.name}")
        print(f"SKU: {product.sku}")
        print(f"Demand reference: {demand.source_ref}")
        print(f"Required at: {demand.required_at.isoformat()}")
        print(f"Inventory observed at: {balance.observed_at.isoformat()}")
        print(f"Remaining demand: {result.remaining_demand}")
        print(f"Available stock: {result.available_stock}")
        print(f"Shortage: {result.shortage_qty}")
        print("Scope: one demand, current stored stock, no inbound allocation.")
        print(f"Shipment: {shipment.external_id}")
        print(f"Shipment ETA: {shipment.current_eta.isoformat()}")
        print(f"Arrives by deadline: {timing.arrives_by_deadline}")
        print(
            f"Hours after deadline: "
            f"{timing.lateness / timedelta(hours=1):.1f}"
        )


if __name__ == "__main__":
    try:
        check_demo_impact()
    finally:
        engine.dispose()