from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from app.services.freshness import assess_freshness
from app.services.recovery import (
    RecoveryDemand,
    TransferAllocation,
    plan_warehouse_transfer,
)


@dataclass(frozen=True)
class PurchasePlan:
    status: str
    reasons: tuple[str, ...]
    arrival_at: datetime | None
    purchase_qty: Decimal
    items_cost: Decimal
    freight_cost: Decimal
    total_cost: Decimal
    currency: str
    allocations: tuple[TransferAllocation, ...]


def plan_supplier_purchase(
    *,
    demands: Sequence[RecoveryDemand],
    approval_status: str,
    available_qty: Decimal,
    unit_price: Decimal,
    currency: str,
    lead_time: timedelta,
    freight_cost: Decimal,
    observed_at: datetime,
    valid_until: datetime,
    as_of: datetime,
    max_offer_age: timedelta = timedelta(minutes=30),
) -> PurchasePlan:
    """Evaluate one offer for one product and destination.

    Purchase is assumed to start at as_of.
    Lead time must include delivery and receiving.
    Freight is charged once for the combined purchase.
    No order is placed and no supplier stock is reserved.
    """
    if not isinstance(unit_price, Decimal):
        raise TypeError("unit_price must be a Decimal.")

    if not unit_price.is_finite() or unit_price < 0:
        raise ValueError("unit_price must be finite and nonnegative.")

    for name, value in (
        ("observed_at", observed_at),
        ("valid_until", valid_until),
        ("as_of", as_of),
    ):
        if not isinstance(value, datetime):
            raise TypeError(f"{name} must be a datetime.")

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must include a timezone.")

    if valid_until <= observed_at:
        raise ValueError("valid_until must be after observed_at.")

    if approval_status not in ("APPROVED", "PENDING", "SUSPENDED"):
        raise ValueError("Unknown supplier approval status.")

    # Reuse shared quantity/deadline allocation and input validation.
    candidate = plan_warehouse_transfer(
        demands=demands,
        on_hand_qty=available_qty,
        reserved_qty=Decimal("0"),
        as_of=as_of,
        lead_time=lead_time,
        fixed_transport_cost=freight_cost,
        currency=currency,
    )

    freshness = assess_freshness(
        observed_at=observed_at,
        as_of=as_of,
        max_age=max_offer_age,
    )

    reasons = []

    if approval_status != "APPROVED":
        reasons.append("SUPPLIER_NOT_APPROVED")

    if not freshness.is_fresh:
        reasons.append(f"OFFER_{freshness.reason}")

    if valid_until <= as_of:
        reasons.append("OFFER_EXPIRED")

    if reasons:
        return PurchasePlan(
            status="BLOCKED",
            reasons=tuple(reasons),
            arrival_at=None,
            purchase_qty=Decimal("0"),
            items_cost=Decimal("0"),
            freight_cost=Decimal("0"),
            total_cost=Decimal("0"),
            currency=currency,
            allocations=(),
        )

    remaining_shortage = sum(
        (
            item.remaining_shortage_qty
            for item in candidate.allocations
        ),
        Decimal("0"),
    )

    if candidate.transfer_qty == 0:
        status = (
            "NO_ACTION_NEEDED"
            if remaining_shortage == 0
            else "NO_FEASIBLE_PURCHASE"
        )
    elif remaining_shortage > 0:
        status = "PARTIAL_COVERAGE"
    else:
        status = "FULL_COVERAGE"

    items_cost = candidate.transfer_qty * unit_price
    charged_freight = candidate.transport_cost

    return PurchasePlan(
        status=status,
        reasons=(),
        arrival_at=as_of.astimezone(timezone.utc) + lead_time,
        purchase_qty=candidate.transfer_qty,
        items_cost=items_cost,
        freight_cost=charged_freight,
        total_cost=items_cost + charged_freight,
        currency=currency,
        allocations=candidate.allocations,
    )