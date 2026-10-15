from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import InventoryBalance, Location, Product
from app.services.freshness import assess_freshness
from app.services.impact_assessment import ImpactTargetNotFound, _assess
from app.services.recovery import RecoveryDemand, plan_warehouse_transfer


def recommend_warehouse_transfer(
    *,
    sku: str,
    plant_code: str,
    warehouse_code: str,
    lead_time: timedelta,
    fixed_transport_cost: Decimal,
    currency: str,
) -> dict:
    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as connection:
        with Session(bind=connection) as session:
            with session.begin():
                as_of = datetime.now(timezone.utc)

                impact = _assess(
                    session=session,
                    sku=sku,
                    plant_code=plant_code,
                    as_of=as_of,
                )

                response = {
                    "status": "INCOMPLETE",
                    "assessed_at": as_of.isoformat(),
                    "sku": sku,
                    "plant_code": plant_code,
                    "warehouse_code": warehouse_code,
                    "issues": list(impact["issues"]),
                    "plan": None,
                    "assumptions": [
                        *impact["assumptions"],
                        "Transfer lead time and cost are supplied assumptions.",
                        "Lead time includes preparation and receiving.",
                        "Cost is transport only, not inventory value.",
                        "Warehouse unreserved stock is available for transfer.",
                        "One combined transfer serves this destination.",
                    ],
                    "execution_status": "NOT_EXECUTED",
                }

                if impact["status"] == "INCOMPLETE":
                    return response

                if impact["status"] == "NO_OPEN_DEMANDS":
                    response["status"] = "NO_ACTION_NEEDED"
                    return response

                shortages = [
                    RecoveryDemand(
                        demand_id=item["demand_id"],
                        shortage_qty=Decimal(item["shortage_qty"]),
                        required_at=datetime.fromisoformat(
                            item["required_at"]
                        ),
                    )
                    for item in impact["allocations"]
                    if Decimal(item["shortage_qty"]) > 0
                ]

                if not shortages:
                    response["status"] = "NO_ACTION_NEEDED"
                    return response

                product = session.scalar(
                    select(Product).where(Product.sku == sku)
                )
                warehouse = session.scalar(
                    select(Location).where(
                        Location.code == warehouse_code,
                        Location.type == "WAREHOUSE",
                    )
                )

                if warehouse is None:
                    raise ImpactTargetNotFound("Warehouse not found.")

                balance = session.scalar(
                    select(InventoryBalance).where(
                        InventoryBalance.product_id == product.id,
                        InventoryBalance.location_id == warehouse.id,
                    )
                )

                if balance is None:
                    response["issues"].append({
                        "code": "MISSING_WAREHOUSE_INVENTORY",
                        "reference": warehouse_code,
                        "message": "Warehouse inventory evidence is missing.",
                    })
                    return response

                freshness = assess_freshness(
                    observed_at=balance.observed_at,
                    as_of=as_of,
                )

                if not freshness.is_fresh:
                    response["issues"].append({
                        "code": f"WAREHOUSE_{freshness.reason}",
                        "reference": warehouse_code,
                        "message": (
                            "Warehouse inventory observed at "
                            f"{balance.observed_at.isoformat()}."
                        ),
                    })
                    return response

                plan = plan_warehouse_transfer(
                    demands=shortages,
                    on_hand_qty=balance.on_hand_qty,
                    reserved_qty=balance.reserved_qty,
                    as_of=as_of,
                    lead_time=lead_time,
                    fixed_transport_cost=fixed_transport_cost,
                    currency=currency,
                )

                references = {
                    item["demand_id"]: item["source_ref"]
                    for item in impact["allocations"]
                }

                remaining_shortage = sum(
                    (
                        item.remaining_shortage_qty
                        for item in plan.allocations
                    ),
                    Decimal("0"),
                )

                if plan.transfer_qty == 0:
                    response["status"] = "NO_FEASIBLE_TRANSFER"
                elif remaining_shortage > 0:
                    response["status"] = "PARTIAL_COVERAGE"
                else:
                    response["status"] = "FULL_COVERAGE"

                response["plan"] = {
                    "warehouse_name": warehouse.name,
                    "warehouse_observed_at": (
                        balance.observed_at.isoformat()
                    ),
                    "arrival_at": plan.arrival_at.isoformat(),
                    "available_qty": str(plan.available_qty),
                    "transfer_qty": str(plan.transfer_qty),
                    "remaining_warehouse_qty": str(
                        plan.remaining_warehouse_qty
                    ),
                    "remaining_shortage_qty": str(remaining_shortage),
                    "transport_cost": str(plan.transport_cost),
                    "currency": plan.currency,
                    "allocations": [
                        {
                            "demand_id": item.demand_id,
                            "source_ref": references[item.demand_id],
                            "allocated_qty": str(item.allocated_qty),
                            "remaining_shortage_qty": str(
                                item.remaining_shortage_qty
                            ),
                            "arrives_by_deadline": (
                                item.arrives_by_deadline
                            ),
                        }
                        for item in plan.allocations
                    ],
                }

                return response