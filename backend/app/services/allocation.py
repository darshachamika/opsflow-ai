from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from app.services.inbound import (
    ACTIVE_STATUSES,
    INACTIVE_STATUSES,
    InboundSupply,
)


ZERO = Decimal("0")


@dataclass(frozen=True)
class DemandRequest:
    demand_id: str
    required_qty: Decimal
    fulfilled_qty: Decimal
    required_at: datetime


@dataclass(frozen=True)
class SupplyAllocation:
    shipment_line_id: str
    quantity: Decimal


@dataclass(frozen=True)
class DemandAllocation:
    demand_id: str
    remaining_demand: Decimal
    stock_allocated_qty: Decimal
    inbound_allocations: tuple[SupplyAllocation, ...]
    shortage_qty: Decimal

    @property
    def inbound_allocated_qty(self) -> Decimal:
        return sum(
            (item.quantity for item in self.inbound_allocations),
            ZERO,
        )


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


def allocate_supply(
    *,
    demands: Sequence[DemandRequest],
    on_hand_qty: Decimal,
    reserved_qty: Decimal,
    inbound_supplies: Sequence[InboundSupply],
) -> tuple[DemandAllocation, ...]:
    """Plan allocations within one product/location supply pool.

    Inputs must contain unique demands and shipment lines.
    Inbound quantities must be unreceived and unallocated.
    Existing reserved stock is excluded from this planning pool.
    Freshness and database reservations are handled separately.
    """
    _validate_quantity(on_hand_qty, "on_hand_qty")
    _validate_quantity(reserved_qty, "reserved_qty")

    if reserved_qty > on_hand_qty:
        raise ValueError("reserved_qty cannot exceed on_hand_qty.")

    demand_ids: set[str] = set()

    for demand in demands:
        if not demand.demand_id or demand.demand_id in demand_ids:
            raise ValueError("Demand IDs must be nonempty and unique.")

        demand_ids.add(demand.demand_id)

        _validate_quantity(demand.required_qty, "required_qty")
        _validate_quantity(demand.fulfilled_qty, "fulfilled_qty")
        _utc(demand.required_at)

        if demand.required_qty == ZERO:
            raise ValueError("required_qty must be positive.")

        if demand.fulfilled_qty > demand.required_qty:
            raise ValueError("fulfilled_qty cannot exceed required_qty.")

    line_ids: set[str] = set()
    active_supplies: list[InboundSupply] = []

    for supply in inbound_supplies:
        if (
            not supply.shipment_line_id
            or supply.shipment_line_id in line_ids
        ):
            raise ValueError("Shipment line IDs must be nonempty and unique.")

        line_ids.add(supply.shipment_line_id)

        _validate_quantity(supply.quantity, "inbound quantity")
        _utc(supply.current_eta)

        if supply.quantity == ZERO:
            raise ValueError("Inbound quantity must be positive.")

        if supply.status in INACTIVE_STATUSES:
            continue

        if supply.status not in ACTIVE_STATUSES:
            raise ValueError(f"Unknown shipment status: {supply.status}")

        active_supplies.append(supply)

    ordered_demands = sorted(
        demands,
        key=lambda item: (_utc(item.required_at), item.demand_id),
    )
    ordered_supplies = sorted(
        active_supplies,
        key=lambda item: (
            _utc(item.current_eta),
            item.shipment_line_id,
        ),
    )

    stock_remaining = on_hand_qty - reserved_qty
    inbound_remaining = {
        item.shipment_line_id: item.quantity
        for item in ordered_supplies
    }

    results: list[DemandAllocation] = []

    for demand in ordered_demands:
        remaining_demand = demand.required_qty - demand.fulfilled_qty
        stock_allocated = min(remaining_demand, stock_remaining)

        stock_remaining -= stock_allocated
        uncovered = remaining_demand - stock_allocated
        allocations: list[SupplyAllocation] = []

        for supply in ordered_supplies:
            if uncovered == ZERO:
                break

            if _utc(supply.current_eta) > _utc(demand.required_at):
                break

            available = inbound_remaining[supply.shipment_line_id]
            allocated = min(uncovered, available)

            if allocated == ZERO:
                continue

            inbound_remaining[supply.shipment_line_id] -= allocated
            uncovered -= allocated

            allocations.append(
                SupplyAllocation(
                    shipment_line_id=supply.shipment_line_id,
                    quantity=allocated,
                )
            )

        results.append(
            DemandAllocation(
                demand_id=demand.demand_id,
                remaining_demand=remaining_demand,
                stock_allocated_qty=stock_allocated,
                inbound_allocations=tuple(allocations),
                shortage_qty=uncovered,
            )
        )

    return tuple(results)