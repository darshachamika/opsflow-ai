from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.recovery import (
    RecoveryDemand,
    plan_warehouse_transfer,
)


AS_OF = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


def demand(name, quantity, hours):
    return RecoveryDemand(
        demand_id=name,
        shortage_qty=Decimal(quantity),
        required_at=AS_OF + timedelta(hours=hours),
    )


def plan(demands, **overrides):
    arguments = {
        "demands": demands,
        "on_hand_qty": Decimal("400"),
        "reserved_qty": Decimal("20"),
        "as_of": AS_OF,
        "lead_time": timedelta(hours=6),
        "fixed_transport_cost": Decimal("18000.00"),
        "currency": "LKR",
    }
    arguments.update(overrides)
    return plan_warehouse_transfer(**arguments)


def test_combined_transfer_covers_both_demands():
    result = plan([
        demand("A", "80", 8),
        demand("B", "200", 9),
    ])

    assert result.available_qty == Decimal("380")
    assert result.transfer_qty == Decimal("280")
    assert result.remaining_warehouse_qty == Decimal("100")
    assert result.transport_cost == Decimal("18000.00")

    assert [a.allocated_qty for a in result.allocations] == [
        Decimal("80"),
        Decimal("200"),
    ]
    assert all(
        a.remaining_shortage_qty == Decimal("0")
        for a in result.allocations
    )


def test_limited_stock_prioritizes_earlier_deadline():
    result = plan(
        [
            demand("B", "200", 9),
            demand("A", "80", 8),
        ],
        on_hand_qty=Decimal("120"),
        reserved_qty=Decimal("20"),
    )

    first, second = result.allocations

    assert first.demand_id == "A"
    assert first.allocated_qty == Decimal("80")
    assert second.allocated_qty == Decimal("20")
    assert second.remaining_shortage_qty == Decimal("180")
    assert result.transfer_qty == Decimal("100")


def test_transfer_late_for_first_can_cover_second():
    result = plan([
        demand("A", "80", 5),
        demand("B", "200", 9),
    ])

    first, second = result.allocations

    assert first.arrives_by_deadline is False
    assert first.allocated_qty == Decimal("0")
    assert first.remaining_shortage_qty == Decimal("80")
    assert second.allocated_qty == Decimal("200")


def test_arrival_exactly_at_deadline_counts():
    result = plan([demand("A", "80", 6)])

    assert result.allocations[0].arrives_by_deadline is True
    assert result.transfer_qty == Decimal("80")


def test_no_feasible_transfer_has_no_transport_cost():
    result = plan([demand("A", "80", 5)])

    assert result.transfer_qty == Decimal("0")
    assert result.transport_cost == Decimal("0")


def test_zero_shortage_has_no_transport_cost():
    result = plan([demand("A", "0", 8)])

    assert result.transfer_qty == Decimal("0")
    assert result.transport_cost == Decimal("0")


def test_fully_reserved_stock_cannot_be_used():
    result = plan(
        [demand("A", "80", 8)],
        reserved_qty=Decimal("400"),
    )

    assert result.transfer_qty == Decimal("0")
    assert result.allocations[0].remaining_shortage_qty == Decimal("80")


def test_duplicate_demands_are_rejected():
    with pytest.raises(ValueError, match="Demand IDs"):
        plan([
            demand("A", "80", 8),
            demand("A", "80", 9),
        ])


@pytest.mark.parametrize("quantity", ["-1", "NaN", "Infinity"])
def test_invalid_shortage_is_rejected(quantity):
    with pytest.raises(ValueError, match="finite and nonnegative"):
        plan([demand("A", quantity, 8)])


def test_negative_lead_time_is_rejected():
    with pytest.raises(ValueError, match="lead_time"):
        plan(
            [demand("A", "80", 8)],
            lead_time=timedelta(hours=-1),
        )


def test_naive_assessment_time_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        plan(
            [demand("A", "80", 8)],
            as_of=AS_OF.replace(tzinfo=None),
        )


def test_reservations_cannot_exceed_stock():
    with pytest.raises(ValueError, match="reserved_qty"):
        plan(
            [demand("A", "80", 8)],
            reserved_qty=Decimal("401"),
        )