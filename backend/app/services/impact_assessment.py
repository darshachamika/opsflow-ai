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


class ImpactTargetNotFound(Exception):
    """The requested product or plant does not exist."""


def assess_product_impact(*, sku: str, plant_code: str) -> dict:
    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as connection:
        with Session(bind=connection) as session:
            with session.begin():
                return _assess(
                    session=session,
                    sku=sku,
                    plant_code=plant_code,
                    as_of=datetime.now(timezone.utc),
                )


def _assess(
    *,
    session: Session,
    sku: str,
    plant_code: str,
    as_of: datetime,
) -> dict:
    product = session.scalar(
        select(Product).where(Product.sku == sku)
    )
    plant = session.scalar(
        select(Location).where(
            Location.code == plant_code,
            Location.type == "PLANT",
        )
    )

    if product is None:
        raise ImpactTargetNotFound("Product not found.")

    if plant is None:
        raise ImpactTargetNotFound("Plant not found.")

    response = {
        "status": "INCOMPLETE",
        "assessed_at": as_of.isoformat(),
        "sku": product.sku,
        "plant_code": plant.code,
        "plant_name": plant.name,
        "issues": [],
        "allocations": [],
        "assumptions": [
            "Active shipment quantities are unreceived and unallocated.",
            "Inbound supply is usable at its current ETA.",
            "Existing reserved stock is excluded.",
            "Allocations are calculated, not persisted.",
        ],
    }

    demands = session.scalars(
        select(ProductionDemand)
        .where(
            ProductionDemand.product_id == product.id,
            ProductionDemand.plant_id == plant.id,
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
        response["status"] = "NO_OPEN_DEMANDS"
        return response

    balance = session.scalar(
        select(InventoryBalance).where(
            InventoryBalance.product_id == product.id,
            InventoryBalance.location_id == plant.id,
        )
    )

    issues = response["issues"]

    if balance is None:
        issues.append({
            "code": "MISSING_INVENTORY",
            "reference": plant.code,
            "message": "Inventory evidence is missing.",
        })
    else:
        freshness = assess_freshness(
            observed_at=balance.observed_at,
            as_of=as_of,
        )

        if not freshness.is_fresh:
            issues.append({
                "code": f"INVENTORY_{freshness.reason}",
                "reference": plant.code,
                "message": (
                    "Inventory observed at "
                    f"{balance.observed_at.isoformat()}."
                ),
            })

    # Current stock cannot establish historical deadline coverage.
    for demand in demands:
        if demand.required_at <= as_of:
            issues.append({
                "code": "DEMAND_DEADLINE_PASSED",
                "reference": demand.source_ref,
                "message": (
                    "Demand deadline has passed. Current supply cannot "
                    "establish whether its historical deadline was met."
                ),
            })

    rows = session.execute(
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

    inbound_supplies = []
    checked_shipments = set()

    for line, shipment, purchase_order in rows:
        if purchase_order.destination_id != shipment.destination_id:
            issues.append({
                "code": "DESTINATION_MISMATCH",
                "reference": shipment.external_id,
                "message": "Purchase order and shipment destinations differ.",
            })

        if purchase_order.status not in (
            "OPEN",
            "CONFIRMED",
            "PARTIALLY_RECEIVED",
        ):
            issues.append({
                "code": "INACTIVE_PURCHASE_ORDER",
                "reference": shipment.external_id,
                "message": "Active shipment references a closed purchase order.",
            })

        if shipment.id not in checked_shipments:
            checked_shipments.add(shipment.id)

            freshness = assess_freshness(
                observed_at=shipment.observed_at,
                as_of=as_of,
            )

            if not freshness.is_fresh:
                issues.append({
                    "code": f"SHIPMENT_{freshness.reason}",
                    "reference": shipment.external_id,
                    "message": (
                        "Shipment observed at "
                        f"{shipment.observed_at.isoformat()}."
                    ),
                })

            if shipment.current_eta <= as_of:
                issues.append({
                    "code": "SHIPMENT_ETA_PASSED",
                    "reference": shipment.external_id,
                    "message": (
                        "Active shipment ETA has passed. "
                        "Confirm receipt or obtain an updated ETA."
                    ),
                })

        inbound_supplies.append(
            InboundSupply(
                shipment_line_id=str(line.id),
                quantity=line.quantity,
                current_eta=shipment.current_eta,
                status=shipment.status,
            )
        )

    if issues:
        return response

    results = allocate_supply(
        demands=[
            DemandRequest(
                demand_id=str(demand.id),
                required_qty=demand.required_qty,
                fulfilled_qty=demand.fulfilled_qty,
                required_at=demand.required_at,
            )
            for demand in demands
        ],
        on_hand_qty=balance.on_hand_qty,
        reserved_qty=balance.reserved_qty,
        inbound_supplies=inbound_supplies,
    )

    demands_by_id = {
        str(demand.id): demand
        for demand in demands
    }

    response["status"] = "ASSESSED"
    response["allocations"] = [
        {
            "demand_id": result.demand_id,
            "source_ref": demands_by_id[result.demand_id].source_ref,
            "required_at": (
                demands_by_id[result.demand_id].required_at.isoformat()
            ),
            "remaining_demand": str(result.remaining_demand),
            "stock_allocated_qty": str(result.stock_allocated_qty),
            "inbound_allocated_qty": str(result.inbound_allocated_qty),
            "shortage_qty": str(result.shortage_qty),
            "inbound_allocations": [
                {
                    "shipment_line_id": allocation.shipment_line_id,
                    "quantity": str(allocation.quantity),
                }
                for allocation in result.inbound_allocations
            ],
        }
        for result in results
    ]

    return response