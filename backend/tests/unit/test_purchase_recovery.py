from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.purchase_recovery import plan_supplier_purchase
from app.services.recovery import RecoveryDemand


AS_OF = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)


def plan(**overrides):
    arguments = {
        "demands": [
            RecoveryDemand(
                demand_id="A",
                shortage_qty=Decimal("80"),
                required_at=AS_OF + timedelta(hours=8),
            ),
            RecoveryDemand(
                demand_id="B",
                shortage_qty=Decimal("200"),
                required_at=AS_OF + timedelta(hours=9),
            ),
        ],
        "approval_status": "APPROVED",
        "available_qty": Decimal("600"),
        "unit_price": Decimal("2100.0000"),
        "currency": "LKR",
        "lead_time": timedelta(hours=7),
        "freight_cost": Decimal("12000.00"),
        "observed_at": AS_OF,
        "valid_until": AS_OF + timedelta(hours=24),
        "as_of": AS_OF,
    }

    arguments.update(overrides)
    return plan_supplier_purchase(**arguments)


def test_full_purchase_costs_freight_once():
    result = plan()

    assert result.status == "FULL_COVERAGE"
    assert result.purchase_qty == Decimal("280")
    assert result.items_cost == Decimal("588000")
    assert result.freight_cost == Decimal("12000")
    assert result.total_cost == Decimal("600000")
    assert [a.allocated_qty for a in result.allocations] == [
        Decimal("80"),
        Decimal("200"),
    ]


def test_supplier_quantity_is_shared_between_demands():
    result = plan(available_qty=Decimal("100"))

    assert result.status == "PARTIAL_COVERAGE"
    assert result.purchase_qty == Decimal("100")
    assert result.allocations[0].allocated_qty == Decimal("80")
    assert result.allocations[1].allocated_qty == Decimal("20")
    assert result.allocations[1].remaining_shortage_qty == Decimal("180")


@pytest.mark.parametrize("status", ["PENDING", "SUSPENDED"])
def test_unapproved_supplier_is_blocked(status):
    result = plan(approval_status=status)

    assert result.status == "BLOCKED"
    assert "SUPPLIER_NOT_APPROVED" in result.reasons
    assert result.allocations == ()


def test_stale_offer_is_blocked():
    result = plan(
        observed_at=AS_OF - timedelta(minutes=31),
    )

    assert result.status == "BLOCKED"
    assert "OFFER_STALE" in result.reasons


def test_future_observation_is_blocked():
    result = plan(
        observed_at=AS_OF + timedelta(minutes=2),
    )

    assert result.status == "BLOCKED"
    assert "OFFER_FUTURE_TIMESTAMP" in result.reasons


def test_offer_expiring_now_is_blocked():
    result = plan(
        observed_at=AS_OF - timedelta(minutes=5),
        valid_until=AS_OF,
    )

    assert result.status == "BLOCKED"
    assert "OFFER_EXPIRED" in result.reasons


def test_offer_can_expire_after_order_before_delivery():
    result = plan(valid_until=AS_OF + timedelta(hours=1))

    assert result.status == "FULL_COVERAGE"


def test_late_delivery_has_no_purchase_cost():
    result = plan(lead_time=timedelta(hours=10))

    assert result.status == "NO_FEASIBLE_PURCHASE"
    assert result.purchase_qty == Decimal("0")
    assert result.total_cost == Decimal("0")


def test_arrival_at_first_deadline_is_allowed():
    result = plan(lead_time=timedelta(hours=8))

    assert result.status == "FULL_COVERAGE"


@pytest.mark.parametrize("price", ["-1", "NaN", "Infinity"])
def test_invalid_price_is_rejected(price):
    with pytest.raises(ValueError, match="unit_price"):
        plan(unit_price=Decimal(price))


def test_no_shortages_need_no_purchase():
    result = plan(demands=[])

    assert result.status == "NO_ACTION_NEEDED"
    assert result.total_cost == Decimal("0")