from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.services.approval_binding import ApprovalConflict, proposal_digest, verify_reassessment


def scenario():
    now = datetime.now(timezone.utc)
    evidence = {"schema_version": 2, "product": {"id": "p"}, "plant": {"id": "l"},
                "inventory_balances": [{"id": "b", "on_hand_qty": "100"}]}
    plan = {"arrival_at": now.isoformat(), "transfer_qty": "80", "currency": "LKR",
            "transport_cost": "100", "allocations": [{"demand_id": "d", "allocated_qty": "80"}]}
    evaluation = {"status": "FULL_COVERAGE", "plan": plan}
    proposal = SimpleNamespace(id=uuid4(), incident_id=uuid4(), version=1,
        action_type="WAREHOUSE_TRANSFER", assessed_at=now, expires_at=now + timedelta(minutes=5),
        evidence_snapshot=evidence, plan_snapshot={"evaluation": evaluation})
    fresh = deepcopy(evaluation)
    fresh.update(assessed_at=now.isoformat(), _evidence=deepcopy(evidence))
    return proposal, fresh


def test_unchanged_inputs_accepted():
    proposal, fresh = scenario()
    assert verify_reassessment(proposal, fresh)["status"] == "REVALIDATED"


@pytest.mark.parametrize("change", ["stock", "cost", "allocation", "incomplete", "legacy"])
def test_changed_evidence_or_business_payload_rejected(change):
    proposal, fresh = scenario()
    if change == "stock": fresh["_evidence"]["inventory_balances"][0]["on_hand_qty"] = "0"
    elif change == "cost": fresh["plan"]["transport_cost"] = "999"
    elif change == "allocation": fresh["plan"]["allocations"][0]["allocated_qty"] = "79"
    elif change == "incomplete": fresh["status"] = "INCOMPLETE"
    else: proposal.evidence_snapshot["schema_version"] = 1
    with pytest.raises(ApprovalConflict):
        verify_reassessment(proposal, fresh)


def test_hash_changes_if_snapshot_or_expiry_changes():
    proposal, _ = scenario()
    original = proposal_digest(proposal)
    proposal.plan_snapshot["evaluation"]["plan"]["transfer_qty"] = "81"
    assert proposal_digest(proposal) != original
    next_hash = proposal_digest(proposal)
    proposal.expires_at += timedelta(seconds=1)
    assert proposal_digest(proposal) != next_hash


def test_new_arrival_forecast_is_audited_without_overwriting_saved_payload():
    proposal, fresh = scenario()
    old = deepcopy(proposal.plan_snapshot)
    fresh["plan"]["arrival_at"] = (proposal.assessed_at + timedelta(minutes=1)).isoformat()
    result = verify_reassessment(proposal, fresh)
    assert result["current_arrival_forecast"] != result["original_arrival_forecast"]
    assert proposal.plan_snapshot == old
