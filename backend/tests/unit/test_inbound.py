from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.inbound import InboundSupply, calculate_inbound_impact


BASE_TIME = datetime(2026, 10, 15, 9, tzinfo=timezone.utc)
DEADLINE = BASE_TIME + timedelta(hours=8)


def supply(
    line_id: str,
    quantity: str,
    hours: int,
    status: str = "IN_TRANSIT",
) -> InboundSupply:
    return InboundSupply(
        shipment_line_id=line_id,
        quantity=Decimal(quantity),
        current_eta=BASE_TIME + timedelta(hours=hours),
        status=status,
    )


def calculate(inbound_supplies):
    return calculate_inbound_impact(
        required_qty=Decimal("500"),
        fulfilled_qty=Decimal("0"),
        on_hand_qty=Decimal("120"),
        reserved_qty=Decimal("0"),
        required_at=DEADLINE,
        inbound_supplies=inbound_supplies,
    )


def test_multiple_on_time_shipments_reduce_shortage():
    result = calculate([
        supply("line-a", "200", 6),
        supply("line-b", "100", 7),
        supply("line-c", "500", 72, "DELAYED"),
    ])

    assert result.shortage_before_inbound == Decimal("380")
    assert result.on_time_inbound_qty == Decimal("300")
    assert result.late_inbound_qty == Decimal("500")
    assert result.inbound_allocated_qty == Decimal("300")
    assert result.shortage_after_inbound == Decimal("80")
    assert result.included_line_ids == ("line-a", "line-b")


def test_another_shipment_can_cover_late_shipment():
    result = calculate([
        supply("late-line", "500", 72, "DELAYED"),
        supply("replacement-line", "400", 6),
    ])

    assert result.shortage_after_inbound == Decimal("0")
    assert result.inbound_allocated_qty == Decimal("380")


def test_arrival_exactly_at_deadline_counts():
    result = calculate([supply("line-a", "380", 8)])

    assert result.shortage_after_inbound == Decimal("0")


def test_late_supply_does_not_cover_shortage():
    result = calculate([supply("line-a", "500", 9)])

    assert result.on_time_inbound_qty == Decimal("0")
    assert result.shortage_after_inbound == Decimal("380")


@pytest.mark.parametrize("status", ["DELIVERED", "CANCELLED"])
def test_inactive_shipments_are_excluded(status):
    result = calculate([supply("line-a", "500", 6, status)])

    assert result.on_time_inbound_qty == Decimal("0")
    assert result.late_inbound_qty == Decimal("0")
    assert result.shortage_after_inbound == Decimal("380")


def test_delayed_status_can_still_arrive_before_demand_deadline():
    result = calculate([supply("line-a", "200", 7, "DELAYED")])

    assert result.shortage_after_inbound == Decimal("180")


def test_no_shipments_keeps_original_shortage():
    result = calculate([])

    assert result.shortage_after_inbound == Decimal("380")


def test_duplicate_line_is_rejected():
    with pytest.raises(ValueError, match="Duplicate shipment line"):
        calculate([
            supply("same-line", "200", 6),
            supply("same-line", "200", 6),
        ])


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity"])
def test_invalid_quantity_is_rejected(quantity):
    with pytest.raises(ValueError, match="finite and positive"):
        calculate([supply("line-a", quantity, 6)])


def test_naive_eta_is_rejected():
    inbound = InboundSupply(
        shipment_line_id="line-a",
        quantity=Decimal("200"),
        current_eta=datetime(2026, 10, 15, 15),
        status="IN_TRANSIT",
    )

    with pytest.raises(ValueError, match="timezone"):
        calculate([inbound])


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError, match="Unknown shipment status"):
        calculate([supply("line-a", "200", 6, "UNKNOWN")])


def test_fulfilled_and_reserved_quantities_are_respected():
    result = calculate_inbound_impact(
        required_qty=Decimal("500"),
        fulfilled_qty=Decimal("100"),
        on_hand_qty=Decimal("120"),
        reserved_qty=Decimal("20"),
        required_at=DEADLINE,
        inbound_supplies=[supply("line-a", "200", 6)],
    )

    assert result.remaining_demand == Decimal("400")
    assert result.available_stock == Decimal("100")
    assert result.shortage_before_inbound == Decimal("300")
    assert result.shortage_after_inbound == Decimal("100")