from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.approval_auth import Actor
from app.models import Incident, RecoveryProposal
from app.models.approval import ApprovalDecision, ApprovalResumeJob
from app.services.approval_binding import ApprovalConflict, digest, proposal_digest, verify_reassessment
from app.services.impact_assessment import ImpactTargetNotFound
from app.services.transfer_recommendation import recommend_warehouse_transfer
from app.services.purchase_recommendation import recommend_supplier_purchases


class ApprovalNotFound(LookupError):
    pass


def revalidate(proposal: RecoveryProposal) -> dict:
    try:
        params = proposal.plan_snapshot["parameters"]
        evidence = proposal.evidence_snapshot
        kwargs = dict(sku=evidence["product"]["sku"], plant_code=evidence["plant"]["code"],
                      currency=params["currency"], include_evidence=True)
        if proposal.action_type == "WAREHOUSE_TRANSFER":
            fresh = recommend_warehouse_transfer(**kwargs, warehouse_code=params["warehouse_code"],
                lead_time=timedelta(hours=params["lead_time_hours"]),
                fixed_transport_cost=Decimal(params["fixed_transport_cost"]))
        elif proposal.action_type == "SUPPLIER_PURCHASE":
            fresh = recommend_supplier_purchases(**kwargs, freight_cost=Decimal(params["freight_cost"]))
        else:
            raise ApprovalConflict("Unsupported proposal action.")
        return verify_reassessment(proposal, fresh)
    except (KeyError, TypeError, ImpactTargetNotFound) as exc:
        raise ApprovalConflict("Incomplete proposal snapshot. Create a new proposal.") from exc


def decide_proposal(*, session: Session, proposal_id: UUID, actor: Actor,
                    decision: str, reason: str, idempotency_key: str) -> tuple[ApprovalDecision, bool]:
    """Caller owns READ COMMITTED transaction; decision and job commit atomically."""
    if actor.role != "PROCUREMENT_MANAGER":
        raise PermissionError("Procurement manager permission required.")
    reason, key = reason.strip(), idempotency_key.strip()
    if decision not in ("APPROVED", "REJECTED") or not reason or len(reason) > 1000:
        raise ValueError("Invalid decision or reason.")
    if not key or len(key) > 128:
        raise ValueError("Invalid idempotency key.")
    incident_id = session.scalar(select(RecoveryProposal.incident_id).where(RecoveryProposal.id == proposal_id))
    if incident_id is None:
        raise ApprovalNotFound("Proposal not found.")
    incident = session.scalar(select(Incident).where(Incident.id == incident_id)
        .with_for_update().execution_options(populate_existing=True))
    proposal = session.scalar(select(RecoveryProposal).where(RecoveryProposal.id == proposal_id)
        .with_for_update().execution_options(populate_existing=True))
    if proposal is None or incident is None:
        raise ApprovalNotFound("Proposal not found.")
    fingerprint = digest({"proposal_id": str(proposal_id), "manager_subject": actor.subject,
                          "decision": decision, "reason": reason})
    replay = session.scalar(select(ApprovalDecision).where(
        ApprovalDecision.manager_subject == actor.subject, ApprovalDecision.idempotency_key == key))
    if replay is not None:
        if replay.request_hash != fingerprint:
            raise ApprovalConflict("Idempotency key already used with different inputs.")
        if replay.proposal_hash != proposal_digest(proposal):
            raise ApprovalConflict("Previously decided proposal has been modified.")
        return replay, False
    if proposal.status != "PROPOSED":
        raise ApprovalConflict(f"Proposal is {proposal.status}; another decision is not allowed.")
    if incident.status not in ("OPEN", "INVESTIGATING"):
        raise ApprovalConflict("Incident is not open.")
    now = datetime.now(timezone.utc)
    if proposal.expires_at <= now or proposal.assessed_at > now:
        raise ApprovalConflict("Proposal has expired or its assessment is in the future.")
    approved = session.scalar(select(RecoveryProposal.id).where(
        RecoveryProposal.incident_id == incident.id, RecoveryProposal.status == "APPROVED"))
    if approved is not None:
        raise ApprovalConflict("Incident already has an approved action.")
    validation = {"status": "NOT_REQUIRED_FOR_REJECTION"}
    if decision == "APPROVED":
        scope = proposal.evidence_snapshot.get("scope", {})
        if scope.get("product_id") != str(incident.product_id) or scope.get("plant_id") != str(incident.plant_id):
            raise ApprovalConflict("Proposal scope does not match incident.")
        validation = revalidate(proposal)
    now = datetime.now(timezone.utc)
    if proposal.expires_at <= now:
        raise ApprovalConflict("Proposal expired during revalidation.")
    binding = proposal_digest(proposal)
    event = ApprovalDecision(proposal_id=proposal.id, manager_subject=actor.subject,
        decision=decision, reason=reason, decided_at=now, idempotency_key=key,
        request_hash=fingerprint, proposal_hash=binding, revalidation_snapshot=validation)
    session.add(event)
    proposal.status = decision
    session.flush()
    if decision == "APPROVED":
        session.execute(update(RecoveryProposal).where(
            RecoveryProposal.incident_id == incident.id,
            RecoveryProposal.id != proposal.id, RecoveryProposal.status == "PROPOSED",
        ).values(status="SUPERSEDED"))
        session.add(ApprovalResumeJob(decision_id=event.id, proposal_id=proposal.id,
            execution_key=f"recovery:{proposal.id}", status="PENDING",
            payload={"schema_version": 1, "proposal_id": str(proposal.id),
                     "decision_id": str(event.id), "proposal_hash": binding,
                     "requires_revalidation": True}))
        session.flush()
    return event, True
