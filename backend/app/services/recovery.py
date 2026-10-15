from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence


ZERO = Decimal("0")


@dataclass(frozen=True)
class RecoveryDemand:
    demand_id: str
    shortage_qty: Decimal
    required_at: datetime


@dataclass(frozen=True)
class TransferAllocation:
    demand_id: str
    allocated_qty: Decimal
    remaining_shortage_qty: Decimal
    arrives_by_deadline: bool


@dataclass(frozen=True)
class TransferPlan:
    arrival_at: datetime
    available_qty: Decimal
    transfer_qty: Decimal
    remaining_warehouse_qty: Decimal
    transport_cost: Decimal
    currency: str
    allocations: tuple[TransferAllocation, ...]


def _validate_quantity(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal.")

    if not value.is_finite() or value < ZERO:
        raise ValueError(f"{name} must be finite and nonnegative.")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("Timestamp must be a datetime.")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone.")

    return value.astimezone(timezone.utc)


def plan_warehouse_transfer(
    *,
    demands: Sequence[RecoveryDemand],
    on_hand_qty: Decimal,
    reserved_qty: Decimal,
    as_of: datetime,
    lead_time: timedelta,
    fixed_transport_cost: Decimal,
    currency: str,
) -> TransferPlan:
    """Plan one combined transfer from one warehouse.

    All demands must concern the same product and destination.
    Source stock must already be checked for freshness and eligibility.
    Lead time must include preparation, transport and receiving.
    This function does not persist reservations or execute transfers.
    """
    _validate_quantity(on_hand_qty, "on_hand_qty")
    _validate_quantity(reserved_qty, "reserved_qty")
    _validate_quantity(fixed_transport_cost, "fixed_transport_cost")

    if reserved_qty > on_hand_qty:
        raise ValueError("reserved_qty cannot exceed on_hand_qty.")

    if not isinstance(lead_time, timedelta):
        raise TypeError("lead_time must be a timedelta.")

    if lead_time < timedelta(0):
        raise ValueError("lead_time cannot be negative.")

    if (
        not isinstance(currency, str)
        or len(currency) != 3
        or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               for character in currency)
    ):
        raise ValueError("currency must contain three uppercase letters.")

    arrival_at = _utc(as_of) + lead_time
    seen_ids: set[str] = set()

    for demand in demands:
        if not demand.demand_id or demand.demand_id in seen_ids:
            raise ValueError("Demand IDs must be nonempty and unique.")

        seen_ids.add(demand.demand_id)
        _validate_quantity(demand.shortage_qty, "shortage_qty")
        _utc(demand.required_at)

    available_qty = on_hand_qty - reserved_qty
    remaining_qty = available_qty
    allocations: list[TransferAllocation] = []

    for demand in sorted(
        demands,
        key=lambda item: (_utc(item.required_at), item.demand_id),
    ):
        on_time = arrival_at <= _utc(demand.required_at)
        allocated_qty = (
            min(demand.shortage_qty, remaining_qty)
            if on_time
            else ZERO
        )

        remaining_qty -= allocated_qty

        allocations.append(
            TransferAllocation(
                demand_id=demand.demand_id,
                allocated_qty=allocated_qty,
                remaining_shortage_qty=(
                    demand.shortage_qty - allocated_qty
                ),
                arrives_by_deadline=on_time,
            )
        )

    transfer_qty = available_qty - remaining_qty

    return TransferPlan(
        arrival_at=arrival_at,
        available_qty=available_qty,
        transfer_qty=transfer_qty,
        remaining_warehouse_qty=remaining_qty,
        transport_cost=(
            fixed_transport_cost if transfer_qty > ZERO else ZERO
        ),
        currency=currency,
        allocations=tuple(allocations),
    )