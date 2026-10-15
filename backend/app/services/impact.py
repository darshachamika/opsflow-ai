from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ImpactResult:
    remaining_demand: Decimal
    available_stock: Decimal
    shortage_qty: Decimal


def calculate_shortage(
    *,
    required_qty: Decimal,
    fulfilled_qty: Decimal,
    on_hand_qty: Decimal,
    reserved_qty: Decimal,
) -> ImpactResult:
    quantities = {
        "required_qty": required_qty,
        "fulfilled_qty": fulfilled_qty,
        "on_hand_qty": on_hand_qty,
        "reserved_qty": reserved_qty,
    }

    for name, value in quantities.items():
        if not isinstance(value, Decimal):
            raise TypeError(f"{name} must be a Decimal")
        if not value.is_finite() or value < 0:
            raise ValueError(f"{name} must be finite and nonnegative")

    if required_qty == 0:
        raise ValueError("required_qty must be positive")

    if fulfilled_qty > required_qty:
        raise ValueError("fulfilled_qty cannot exceed required_qty")

    if reserved_qty > on_hand_qty:
        raise ValueError("reserved_qty cannot exceed on_hand_qty")

    remaining = required_qty - fulfilled_qty
    available = on_hand_qty - reserved_qty
    shortage = max(remaining - available, Decimal("0"))

    return ImpactResult(
        remaining_demand=remaining,
        available_stock=available,
        shortage_qty=shortage,
    )

@dataclass(frozen=True)
class ShipmentTimingResult:
    arrives_by_deadline: bool
    lateness: timedelta


def assess_shipment_timing(
    *,
    current_eta: datetime,
    required_at: datetime,
) -> ShipmentTimingResult:
    for name, value in {
        "current_eta": current_eta,
        "required_at": required_at,
    }.items():
        if not isinstance(value, datetime):
            raise TypeError(f"{name} must be a datetime")

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must include a timezone")

    lateness = max(current_eta - required_at, timedelta(0))

    return ShipmentTimingResult(
        arrives_by_deadline=current_eta <= required_at,
        lateness=lateness,
    )