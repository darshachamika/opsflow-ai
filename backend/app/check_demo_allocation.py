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
    PurchaseOrderLine,
    Shipment,
    ShipmentLine,
)
from app.services.allocation import DemandRequest, allocate_supply
from app.services.freshness import assess_freshness
from app.services.inbound import InboundSupply


def check_demo_allocation() -> None:
    as_of = datetime.now(timezone.utc)

    with Session(engine) as session:
        reference_demand = session.scalar(
            select(ProductionDemand).where(
                ProductionDemand.source_system == "DEMO_ERP",
                ProductionDemand.source_ref == "DEMAND-DEMO-LK-001",
            )
        )

        if reference_demand is None:
            raise RuntimeError(
                "Demo demand not found. Run app.seed_demo first."
            )

        plant = session.get(Location, reference_demand.plant_id)
        product = session.get(Product, reference_demand.product_id)

        if plant is None or plant.type != "PLANT":
            raise RuntimeError("Demand must reference a valid plant.")

        if product is None:
            raise RuntimeError("Demand product was not found.")

        demands = session.scalars(
            select(ProductionDemand)
            .where(
                ProductionDemand.plant_id == plant.id,
                ProductionDemand.product_id == product.id,
                ProductionDemand.status.in_(
                    ("OPEN", "PARTIALLY_FULFILLED")
                ),
            )
            .order_by(
                ProductionDemand.required_at,
                ProductionDemand.id,
            )
        ).all()

        if not demands:
            print("No open demands for this product and plant.")
            return

        balance = session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product.id,
                InventoryBalance.location_id == plant.id,
            )
        )

        if balance is None:
            raise RuntimeError(
                "Inventory evidence is missing; cannot allocate supply."
            )

        shipment_rows = session.execute(
            select(ShipmentLine, Shipment, PurchaseOrder)
            .join(
                Shipment,
                ShipmentLine.shipment_id == Shipment.id,
            )
            .join(
                PurchaseOrderLine,
                ShipmentLine.purchase_order_line_id
                == PurchaseOrderLine.id,
            )
            .join(
                PurchaseOrder,
                PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
            )
            .where(
                PurchaseOrderLine.product_id == product.id,
                Shipment.destination_id == plant.id,
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

        # Validate relationships before calculating allocations.
        for _, shipment, purchase_order in shipment_rows:
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

        print("=== DEMO SHARED SUPPLY ALLOCATION ===")
        print(f"Plant: {plant.name}")
        print(f"SKU: {product.sku}")
        print(f"Open demands: {len(demands)}")
        print(f"Assessed at: {as_of.isoformat()}")
        print(
            f"Inventory observed at: "
            f"{balance.observed_at.isoformat()}"
        )

        # Check supply evidence before allocating any quantities.
        evidence_issues: list[str] = []

        inventory_freshness = assess_freshness(
            observed_at=balance.observed_at,
            as_of=as_of,
        )

        if not inventory_freshness.is_fresh:
            evidence_issues.append(
                f"Inventory: {inventory_freshness.reason}; "
                f"observed_at={balance.observed_at.isoformat()}"
            )

        checked_shipments = set()

        for _, shipment, _ in shipment_rows:
            if shipment.id in checked_shipments:
                continue

            checked_shipments.add(shipment.id)

            shipment_freshness = assess_freshness(
                observed_at=shipment.observed_at,
                as_of=as_of,
            )

            if not shipment_freshness.is_fresh:
                evidence_issues.append(
                    f"Shipment {shipment.external_id}: "
                    f"{shipment_freshness.reason}; "
                    f"observed_at={shipment.observed_at.isoformat()}"
                )

            if shipment.current_eta <= as_of:
                evidence_issues.append(
                    f"Shipment {shipment.external_id}: "
                    "ETA has passed but shipment is still active; "
                    "confirm receipt or obtain an updated ETA."
                )

        if evidence_issues:
            print("\nAssessment status: INCOMPLETE")
            print("Reason: supply evidence needs an update.")

            for issue in evidence_issues:
                print(f"- {issue}")

            print(
                "\nNo allocation or definitive shortage was calculated."
            )
            return

        print("\nSupply evidence freshness: PASSED")

        inbound_supplies: list[InboundSupply] = []
        shipment_references: dict[str, str] = {}

        for line, shipment, _ in shipment_rows:
            line_id = str(line.id)
            shipment_references[line_id] = shipment.external_id

            inbound_supplies.append(
                InboundSupply(
                    shipment_line_id=line_id,
                    quantity=line.quantity,
                    current_eta=shipment.current_eta,
                    status=shipment.status,
                )
            )

        demand_requests = [
            DemandRequest(
                demand_id=str(demand.id),
                required_qty=demand.required_qty,
                fulfilled_qty=demand.fulfilled_qty,
                required_at=demand.required_at,
            )
            for demand in demands
        ]

        results = allocate_supply(
            demands=demand_requests,
            on_hand_qty=balance.on_hand_qty,
            reserved_qty=balance.reserved_qty,
            inbound_supplies=inbound_supplies,
        )

        demands_by_id = {
            str(demand.id): demand
            for demand in demands
        }

        print(
            f"Initial available stock: "
            f"{balance.on_hand_qty - balance.reserved_qty}"
        )

        for result in results:
            demand = demands_by_id[result.demand_id]

            print(f"\nDemand: {demand.source_ref}")
            print(f"Required at: {demand.required_at.isoformat()}")
            print(f"Remaining demand: {result.remaining_demand}")
            print(f"Stock allocated: {result.stock_allocated_qty}")
            print(f"Inbound allocated: {result.inbound_allocated_qty}")
            print(f"Shortage: {result.shortage_qty}")

            for allocation in result.inbound_allocations:
                reference = shipment_references[
                    allocation.shipment_line_id
                ]

                print(
                    f"  From {reference}: {allocation.quantity}"
                    f" | Line: {allocation.shipment_line_id}"
                )

        print(
            "\nScope: stored supply observations, earliest deadline first, "
            "one product and plant."
        )
        print(
            "Planning only: no database reservations are saved. "
            "Inventory and shipment observation freshness checks passed."
        )
        print(
            "Demo assumption: active shipment quantities are fully "
            "unreceived, unallocated, and usable at ETA."
        )


if __name__ == "__main__":
    try:
        check_demo_allocation()
    finally:
        engine.dispose()