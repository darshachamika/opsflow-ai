from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.allocation import DemandRequest, allocate_supply
from app.services.inbound import InboundSupply


BASE = datetime(2026, 10, 15, 9, tzinfo=timezone.utc)


def demand(name, quantity, hours, fulfilled="0"):
    return DemandRequest(
        demand_id=name,
        required_qty=Decimal(quantity),
        fulfilled_qty=Decimal(fulfilled),
        required_at=BASE + timedelta(hours=hours),
    )


def shipment(name, quantity, hours, status="IN_TRANSIT"):
    return InboundSupply(
        shipment_line_id=name,
        quantity=Decimal(quantity),
        current_eta=BASE + timedelta(hours=hours),
        status=status,
    )


def allocate(demands, supplies=(), stock="0", reserved="0"):
    return allocate_supply(
        demands=demands,
        on_hand_qty=Decimal(stock),
        reserved_qty=Decimal(reserved),
        inbound_supplies=supplies,
    )


def test_shared_supply_is_not_counted_twice():
    results = allocate(
        [
            demand("B", "250", 9),
            demand("A", "250", 8),
        ],
        [
            shipment("S1", "200", 6),
            shipment("S2", "100", 7),
        ],
        stock="120",
    )

    first, second = results

    assert first.demand_id == "A"
    assert first.stock_allocated_qty == Decimal("120")
    assert first.inbound_allocated_qty == Decimal("130")
    assert first.shortage_qty == Decimal("0")

    assert second.demand_id == "B"
    assert second.stock_allocated_qty == Decimal("0")
    assert second.inbound_allocated_qty == Decimal("170")
    assert second.shortage_qty == Decimal("80")

    allocated_by_line = {}
    for result in results:
        for item in result.inbound_allocations:
            allocated_by_line[item.shipment_line_id] = (
                allocated_by_line.get(item.shipment_line_id, Decimal("0"))
                + item.quantity
            )

    assert allocated_by_line == {
        "S1": Decimal("200"),
        "S2": Decimal("100"),
    }


def test_late_for_first_demand_can_cover_later_demand():
    first, second = allocate(
        [
            demand("A", "100", 4),
            demand("B", "100", 8),
        ],
        [shipment("S1", "100", 6)],
    )

    assert first.shortage_qty == Decimal("100")
    assert second.shortage_qty == Decimal("0")


def test_reserved_stock_is_excluded():
    first, second = allocate(
        [
            demand("A", "100", 4),
            demand("B", "100", 8),
        ],
        stock="120",
        reserved="20",
    )

    assert first.stock_allocated_qty == Decimal("100")
    assert second.stock_allocated_qty == Decimal("0")
    assert second.shortage_qty == Decimal("100")


def test_fulfilled_demand_does_not_consume_supply():
    first, second = allocate(
        [
            demand("A", "100", 4, fulfilled="100"),
            demand("B", "100", 8),
        ],
        stock="100",
    )

    assert first.stock_allocated_qty == Decimal("0")
    assert second.stock_allocated_qty == Decimal("100")


def test_same_deadline_uses_demand_id_order():
    results = allocate(
        [
            demand("B", "100", 8),
            demand("A", "100", 8),
        ],
        stock="100",
    )

    assert results[0].demand_id == "A"
    assert results[0].shortage_qty == Decimal("0")
    assert results[1].shortage_qty == Decimal("100")


@pytest.mark.parametrize("status", ["DELIVERED", "CANCELLED"])
def test_inactive_shipments_are_excluded(status):
    results = allocate(
        [demand("A", "100", 8)],
        [shipment("S1", "100", 6, status)],
    )

    assert results[0].shortage_qty == Decimal("100")


def test_duplicate_demand_is_rejected():
    with pytest.raises(ValueError, match="Demand IDs"):
        allocate([
            demand("A", "100", 4),
            demand("A", "100", 8),
        ])


def test_duplicate_shipment_line_is_rejected():
    with pytest.raises(ValueError, match="Shipment line IDs"):
        allocate(
            [demand("A", "100", 8)],
            [
                shipment("S1", "100", 6),
                shipment("S1", "100", 6),
            ],
        )


def test_arrival_at_deadline_counts():
    results = allocate(
        [demand("A", "100", 8)],
        [shipment("S1", "100", 8)],
    )

    assert results[0].shortage_qty == Decimal("0")