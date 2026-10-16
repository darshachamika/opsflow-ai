import hashlib
import json
from datetime import timezone


class ApprovalConflict(ValueError):
    pass


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def proposal_digest(proposal) -> str:
    return digest({
        "proposal_id": str(proposal.id), "incident_id": str(proposal.incident_id),
        "version": proposal.version, "action_type": proposal.action_type,
        "assessed_at": proposal.assessed_at.astimezone(timezone.utc).isoformat(),
        "expires_at": proposal.expires_at.astimezone(timezone.utc).isoformat(),
        "plan_snapshot": proposal.plan_snapshot, "evidence_snapshot": proposal.evidence_snapshot,
    })


def input_records(evidence: dict) -> dict:
    keys = ("product", "plant", "warehouse", "inventory_balances", "production_demands",
            "shipments", "shipment_lines", "purchase_order_lines", "purchase_orders", "suppliers", "supplier_offers")
    return {key: evidence[key] for key in keys if key in evidence}


def business_plan(plan: dict) -> dict:
    # Preserve the saved forecast, and audit the updated forecast separately.
    return {key: value for key, value in plan.items() if key != "arrival_at"}


def verify_reassessment(proposal, fresh: dict) -> dict:
    old = proposal.evidence_snapshot
    if old.get("schema_version") != 2:
        raise ApprovalConflict("Full version-2 evidence is required. Create a new proposal.")
    new = fresh.get("_evidence")
    if not new or input_records(old) != input_records(new):
        raise ApprovalConflict("Source evidence changed or is unusable. Create a new proposal.")
    if proposal.action_type == "WAREHOUSE_TRANSFER":
        previous, current = proposal.plan_snapshot["evaluation"], fresh
    else:
        offer_id = proposal.plan_snapshot["selected_offer_id"]
        previous = proposal.plan_snapshot["selected_option"]
        current = next((row for row in fresh["options"] if row["offer_id"] == offer_id), None)
    if current is None or current["status"] not in ("FULL_COVERAGE", "PARTIAL_COVERAGE"):
        raise ApprovalConflict("Selected action is no longer feasible.")
    if current["status"] != previous["status"] or business_plan(current["plan"]) != business_plan(previous["plan"]):
        raise ApprovalConflict("Quantities, costs or allocations changed. Create a new proposal.")
    return {"status": "REVALIDATED", "assessed_at": fresh["assessed_at"],
        "input_records_hash": digest(input_records(new)),
        "original_arrival_forecast": previous["plan"]["arrival_at"],
        "current_arrival_forecast": current["plan"]["arrival_at"],
        "requires_execution_revalidation": True}
