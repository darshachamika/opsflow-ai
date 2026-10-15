from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import InventoryBalance, Location, Product, ProductionDemand
from app.services.impact import calculate_shortage


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

        result = calculate_shortage(
            required_qty=demand.required_qty,
            fulfilled_qty=demand.fulfilled_qty,
            on_hand_qty=balance.on_hand_qty,
            reserved_qty=balance.reserved_qty,
        )

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


if __name__ == "__main__":
    try:
        check_demo_impact()
    finally:
        engine.dispose()