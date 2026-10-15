from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Product, Supplier, SupplierOffer
from app.services.impact_assessment import _assess
from app.services.purchase_recovery import plan_supplier_purchase
from app.services.recovery import RecoveryDemand


def recommend_supplier_purchases(
    *,
    sku: str,
    plant_code: str,
    freight_cost: Decimal,
    currency: str,
) -> dict:
    """Evaluate individual offers as alternative purchase plans.

    Freight is a supplied estimate for each alternative.
    Offers are not combined and no purchase orders are created.
    """
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
                    "issues": list(impact["issues"]),
                    "options": [],
                    "execution_status": "NOT_EXECUTED",
                    "assumptions": [
                        *impact["assumptions"],
                        "Each offer is an independent alternative.",
                        "Purchase starts at assessment time.",
                        "Offer lead time includes delivery and receiving.",
                        "Freight is a supplied estimate per alternative.",
                        "Costs exclude taxes and unspecified charges.",
                        "Approval requires revalidation before execution.",
                    ],
                }

                if impact["status"] == "INCOMPLETE":
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

                rows = session.execute(
                    select(SupplierOffer, Supplier)
                    .join(
                        Supplier,
                        SupplierOffer.supplier_id == Supplier.id,
                    )
                    .where(SupplierOffer.product_id == product.id)
                    .order_by(Supplier.code, SupplierOffer.id)
                ).all()

                references = {
                    item["demand_id"]: item["source_ref"]
                    for item in impact["allocations"]
                }

                for offer, supplier in rows:
                    option = {
                        "offer_id": str(offer.id),
                        "supplier_code": supplier.code,
                        "supplier_name": supplier.name,
                        "observed_at": offer.observed_at.isoformat(),
                        "valid_until": offer.valid_until.isoformat(),
                        "unit_price": str(offer.unit_price),
                        "currency": offer.currency,
                        "status": "BLOCKED",
                        "reasons": [],
                        "plan": None,
                    }

                    # Do not add freight in one currency to another currency.
                    if offer.currency != currency:
                        option["reasons"] = ["CURRENCY_MISMATCH"]
                        response["options"].append(option)
                        continue

                    plan = plan_supplier_purchase(
                        demands=shortages,
                        approval_status=supplier.approval_status,
                        available_qty=offer.available_qty,
                        unit_price=offer.unit_price,
                        currency=offer.currency,
                        lead_time=timedelta(
                            hours=offer.lead_time_hours
                        ),
                        freight_cost=freight_cost,
                        observed_at=offer.observed_at,
                        valid_until=offer.valid_until,
                        as_of=as_of,
                    )

                    option["status"] = plan.status
                    option["reasons"] = list(plan.reasons)

                    if plan.status != "BLOCKED":
                        option["plan"] = {
                            "arrival_at": (
                                plan.arrival_at.isoformat()
                                if plan.arrival_at is not None
                                else None
                            ),
                            "purchase_qty": str(plan.purchase_qty),
                            "items_cost": str(plan.items_cost),
                            "freight_cost": str(plan.freight_cost),
                            "total_cost": str(plan.total_cost),
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

                    response["options"].append(option)

                if not rows:
                    response["status"] = "NO_OFFERS"
                elif any(
                    option["status"] in (
                        "FULL_COVERAGE",
                        "PARTIAL_COVERAGE",
                    )
                    for option in response["options"]
                ):
                    response["status"] = "OPTIONS_AVAILABLE"
                else:
                    response["status"] = "NO_ELIGIBLE_OPTIONS"

                return response