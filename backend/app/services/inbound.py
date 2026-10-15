from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from app.services.impact import calculate_shortage


ACTIVE_STATUSES = frozenset({"PLANNED", "IN_TRANSIT", "DELAYED"})
INACTIVE_STATUSES = frozenset({"DELIVERED", "CANCELLED"})


@dataclass(frozen=True)
class InboundSupply:
    shipment_line_id: str
    quantity: Decimal
    current_eta: datetime
    status: str


@dataclass(frozen=True)
class InboundImpactResult:
    remaining_demand: Decimal
    available_stock: Decimal
    shortage_before_inbound: Decimal
    on_time_inbound_qty: Decimal
    late_inbound_qty: Decimal
    inbound_allocated_qty: Decimal
    shortage_after_inbound: Decimal
    included_line_ids: tuple[str, ...]


def _validate_datetime(value: datetime, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime.")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone.")


def calculate_inbound_impact(
    *,
    required_qty: Decimal,
    fulfilled_qty: Decimal,
    on_hand_qty: Decimal,
    reserved_qty: Decimal,
    required_at: datetime,
    inbound_supplies: Sequence[InboundSupply],
) -> InboundImpactResult:
    """Calculate coverage for one demand using expected inbound supply.

    Caller must provide:
    - Lines for the same product and destination as the demand.
    - Outstanding, unreceived quantities available for this demand.
    - Each shipment line exactly once.

    This calculation does not persist reservations or assess freshness.
    """
    _validate_datetime(required_at, "required_at")

    stock_result = calculate_shortage(
        required_qty=required_qty,
        fulfilled_qty=fulfilled_qty,
        on_hand_qty=on_hand_qty,
        reserved_qty=reserved_qty,
    )

    on_time_qty = Decimal("0")
    late_qty = Decimal("0")
    seen_ids: set[str] = set()
    included_ids: list[str] = []

    for supply in inbound_supplies:
        if not supply.shipment_line_id:
            raise ValueError("shipment_line_id must not be empty.")

        if supply.shipment_line_id in seen_ids:
            raise ValueError(
                f"Duplicate shipment line: {supply.shipment_line_id}"
            )

        seen_ids.add(supply.shipment_line_id)

        if not isinstance(supply.quantity, Decimal):
            raise TypeError("Inbound quantity must be a Decimal.")

        if not supply.quantity.is_finite() or supply.quantity <= 0:
            raise ValueError("Inbound quantity must be finite and positive.")

        _validate_datetime(supply.current_eta, "current_eta")

        if supply.status in INACTIVE_STATUSES:
            continue

        if supply.status not in ACTIVE_STATUSES:
            raise ValueError(f"Unknown shipment status: {supply.status}")

        if supply.current_eta <= required_at:
            on_time_qty += supply.quantity
            included_ids.append(supply.shipment_line_id)
        else:
            late_qty += supply.quantity

    allocated_qty = min(stock_result.shortage_qty, on_time_qty)
    shortage_after = stock_result.shortage_qty - allocated_qty

    return InboundImpactResult(
        remaining_demand=stock_result.remaining_demand,
        available_stock=stock_result.available_stock,
        shortage_before_inbound=stock_result.shortage_qty,
        on_time_inbound_qty=on_time_qty,
        late_inbound_qty=late_qty,
        inbound_allocated_qty=allocated_qty,
        shortage_after_inbound=shortage_after,
        included_line_ids=tuple(included_ids),
    )