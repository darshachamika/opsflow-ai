from datetime import datetime, timedelta, timezone
import pytest
from app.services.proposal_validity import proposal_expiry

NOW = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)


def inputs():
    return dict(
        assessed_at=NOW,
        evidence={
            "inventory_balances": [{"observed_at": NOW.isoformat()}],
            "shipments": [],
            "production_demands": [{"id": "d1", "required_at": (NOW + timedelta(hours=3)).isoformat()}],
            "supplier_offers": [{"id": "o1", "observed_at": NOW.isoformat(),
                                 "valid_until": (NOW + timedelta(hours=2)).isoformat()}],
        },
        plan={"allocations": [{"demand_id": "d1", "allocated_qty": "10"}]},
        lead_time=timedelta(hours=1),
    )


def test_default_window_is_five_minutes():
    assert proposal_expiry(**inputs()) == NOW + timedelta(minutes=5)


def test_inventory_freshness_limits_window():
    data = inputs()
    data["evidence"]["inventory_balances"][0]["observed_at"] = (NOW - timedelta(minutes=29)).isoformat()
    assert proposal_expiry(**data) == NOW + timedelta(minutes=1)


def test_offer_expiry_limits_window():
    data = inputs()
    data["evidence"]["supplier_offers"][0]["valid_until"] = (NOW + timedelta(seconds=40)).isoformat()
    assert proposal_expiry(**data, offer_id="o1") == NOW + timedelta(seconds=40)


def test_departure_deadline_limits_window():
    data = inputs()
    data["evidence"]["production_demands"][0]["required_at"] = (NOW + timedelta(hours=1, minutes=2)).isoformat()
    assert proposal_expiry(**data) == NOW + timedelta(minutes=2)


def test_no_approval_window_rejected():
    data = inputs()
    data["evidence"]["production_demands"][0]["required_at"] = (NOW + timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError, match="approval window"):
        proposal_expiry(**data)


def test_active_shipment_eta_limits_window():
    data = inputs()
    data["evidence"]["shipments"] = [{"observed_at": NOW.isoformat(),
        "current_eta": (NOW + timedelta(minutes=1)).isoformat()}]
    assert proposal_expiry(**data) == NOW + timedelta(minutes=1)


def test_zero_allocation_does_not_shorten_window():
    data = inputs()
    data["evidence"]["production_demands"].append({"id": "d2", "required_at": NOW.isoformat()})
    data["plan"]["allocations"].append({"demand_id": "d2", "allocated_qty": "0"})
    assert proposal_expiry(**data) == NOW + timedelta(minutes=5)
