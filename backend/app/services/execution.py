"""Synchronous, transactional MOCK execution. No external ERP requests."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from sqlalchemy import func, select, text
from app.core.approval_auth import Actor
from app.models import Incident, InventoryBalance, RecoveryProposal, SupplierOffer
from app.models.approval import ApprovalDecision, ApprovalResumeJob
from app.models.execution import RecoveryDemandClaim, RecoveryExecution, RecoveryReservation
from app.connectors.mock_erp import MockERPRejected, submit_mock_order
from app.services.approval_binding import ApprovalConflict, proposal_digest, verify_reassessment
from app.services.evidence import capture_recovery_evidence
from app.services.impact_assessment import ImpactTargetNotFound
from app.services.transfer_recommendation import _recommend_transfer
from app.services.purchase_recommendation import _recommend_purchases


class ExecutionConflict(ValueError):
    pass


class ExecutionNotFound(LookupError):
    pass


def _lock_planning_sources(session):
    # Coarse MVP lock closes the read/check/write gap, including newly inserted demands.
    # Only this local, short-lived simulator uses it. No network calls while held.
    session.execute(text("""LOCK TABLE inventory_balances, locations, products,
        production_demands, purchase_order_lines, purchase_orders, shipment_lines,
        shipments, supplier_offers, suppliers IN SHARE ROW EXCLUSIVE MODE"""))


def _reassess(session, proposal, now):
    params, evidence = proposal.plan_snapshot["parameters"], proposal.evidence_snapshot
    kwargs = dict(session=session, as_of=now, sku=evidence["product"]["sku"],
                  plant_code=evidence["plant"]["code"], currency=params["currency"])
    if proposal.action_type == "WAREHOUSE_TRANSFER":
        fresh = _recommend_transfer(**kwargs, warehouse_code=params["warehouse_code"],
            lead_time=timedelta(hours=params["lead_time_hours"]),
            fixed_transport_cost=Decimal(params["fixed_transport_cost"]))
    else:
        fresh = _recommend_purchases(**kwargs, freight_cost=Decimal(params["freight_cost"]))
    fresh["_evidence"] = capture_recovery_evidence(session=session, sku=kwargs["sku"],
        plant_code=kwargs["plant_code"], assessed_at=now,
        warehouse_code=params["warehouse_code"] if proposal.action_type == "WAREHOUSE_TRANSFER" else None)
    return verify_reassessment(proposal, fresh)


def _reserve(session, execution, proposal):
    evidence = proposal.evidence_snapshot
    demand_ids = [UUID(row["id"]) for row in evidence["production_demands"]]
    if session.scalar(select(RecoveryDemandClaim.id).where(RecoveryDemandClaim.demand_id.in_(demand_ids)).limit(1)):
        raise ExecutionConflict("A demand in this planning pool already has an accepted recovery order.")
    # Claim the entire assessed demand pool to prevent overlapping incidents purchasing twice.
    for demand_id in demand_ids:
        session.add(RecoveryDemandClaim(execution_id=execution.id, demand_id=demand_id))
    if proposal.action_type == "WAREHOUSE_TRANSFER":
        plan = proposal.plan_snapshot["evaluation"]["plan"]
        quantity = Decimal(plan["transfer_qty"])
        balance = session.scalar(select(InventoryBalance).where(
            InventoryBalance.product_id == UUID(evidence["scope"]["product_id"]),
            InventoryBalance.location_id == UUID(evidence["scope"]["warehouse_id"])).with_for_update())
        if balance is None or balance.on_hand_qty - balance.reserved_qty < quantity:
            raise ExecutionConflict("Insufficient warehouse stock.")
        balance.reserved_qty += quantity
        reservation = RecoveryReservation(execution_id=execution.id,
            inventory_balance_id=balance.id, quantity=quantity, status="ACTIVE")
    else:
        plan = proposal.plan_snapshot["selected_option"]["plan"]
        quantity = Decimal(plan["purchase_qty"])
        offer_id = UUID(proposal.plan_snapshot["selected_offer_id"])
        offer = session.scalar(select(SupplierOffer).where(SupplierOffer.id == offer_id).with_for_update())
        held = session.scalar(select(func.coalesce(func.sum(RecoveryReservation.quantity), 0)).where(
            RecoveryReservation.supplier_offer_id == offer_id, RecoveryReservation.status == "ACTIVE"))
        if offer is None or offer.available_qty - held < quantity:
            raise ExecutionConflict("Insufficient uncommitted supplier offer quantity.")
        reservation = RecoveryReservation(execution_id=execution.id,
            supplier_offer_id=offer_id, quantity=quantity, status="ACTIVE")
    if not quantity.is_finite() or quantity <= 0:
        raise ExecutionConflict("Execution quantity must be positive and finite.")
    session.add(reservation)
    session.flush()
    return reservation


def execute_mock(*, session, proposal_id: UUID, actor: Actor):
    if actor.role != "PROCUREMENT_MANAGER":
        raise PermissionError("Procurement manager permission required.")
    session.execute(text("SET LOCAL lock_timeout = '5s'"))
    session.execute(text("SET LOCAL statement_timeout = '15s'"))
    incident_id = session.scalar(select(RecoveryProposal.incident_id).where(RecoveryProposal.id == proposal_id))
    if incident_id is None:
        raise ExecutionNotFound("Proposal not found.")
    incident = session.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
    proposal = session.scalar(select(RecoveryProposal).where(RecoveryProposal.id == proposal_id)
        .with_for_update().execution_options(populate_existing=True))
    existing = session.scalar(select(RecoveryExecution).where(RecoveryExecution.proposal_id == proposal_id))
    if existing is not None:
        return existing, False
    if proposal.status != "APPROVED":
        raise ExecutionConflict("Only an approved proposal can execute.")
    decision = session.scalar(select(ApprovalDecision).where(
        ApprovalDecision.proposal_id == proposal_id, ApprovalDecision.decision == "APPROVED"))
    job = session.scalar(select(ApprovalResumeJob).where(ApprovalResumeJob.proposal_id == proposal_id).with_for_update())
    if decision is None or job is None or job.decision_id != decision.id or job.status != "PENDING":
        raise ExecutionConflict("A matching approved decision and pending resume job are required.")
    binding = proposal_digest(proposal)
    if (decision.proposal_hash != binding or job.payload.get("proposal_hash") != binding
        or job.execution_key != f"recovery:{proposal.id}"
        or job.payload.get("proposal_id") != str(proposal.id)
        or job.payload.get("decision_id") != str(decision.id)):
        raise ExecutionConflict("Approval/job binding does not match the exact proposal.")
    execution = RecoveryExecution(proposal_id=proposal.id, decision_id=decision.id, job_id=job.id,
        execution_key=job.execution_key, requested_by=actor.subject, status="RUNNING",
        proposal_hash=binding, result={"mode": "MOCK"})
    session.add(execution)
    session.flush()
    try:
        # Savepoint rolls back all holds, claims and mock orders on definitive rejection.
        with session.begin_nested():
            _lock_planning_sources(session)
            now = datetime.now(timezone.utc)
            if incident.status not in ("OPEN", "INVESTIGATING"):
                raise ExecutionConflict("Incident is not open.")
            scope = proposal.evidence_snapshot["scope"]
            if scope["product_id"] != str(incident.product_id) or scope["plant_id"] != str(incident.plant_id):
                raise ExecutionConflict("Incident scope changed.")
            if proposal.expires_at <= now or proposal.assessed_at > now:
                raise ExecutionConflict("Proposal has expired or is not yet valid.")
            validation = _reassess(session, proposal, now)
            reservation = _reserve(session, execution, proposal)
            if proposal.expires_at <= datetime.now(timezone.utc):
                raise ExecutionConflict("Proposal expired during execution checks.")
            payload = {"proposal_id": str(proposal.id), "proposal_hash": binding,
                "action_type": proposal.action_type, "approved_plan": proposal.plan_snapshot,
                "revalidation": validation}
            order = submit_mock_order(session=session, execution=execution,
                action_type=proposal.action_type, payload=payload)
            result = {"mode": "MOCK", "order_status": "ACCEPTED", "external_ref": order.external_ref,
                "reservation_id": str(reservation.id), "quantity": str(reservation.quantity),
                "physical_receipt_recorded": False, "revalidation": validation}
    except (ApprovalConflict, ExecutionConflict, MockERPRejected, ImpactTargetNotFound) as exc:
        execution.status = "FAILED"
        execution.failure_reason = str(exc)[:500]
        execution.result = {"mode": "MOCK", "requires_new_proposal": True}
        job.status = "FAILED"
        proposal.status = "EXPIRED" if proposal.expires_at <= datetime.now(timezone.utc) else "SUPERSEDED"
        if incident.status in ("OPEN", "INVESTIGATING"):
            incident.status = "INVESTIGATING"
    else:
        execution.status = "SUCCEEDED"
        execution.result = result
        job.status = "COMPLETED"
        incident.status = "INVESTIGATING"
        # APPROVED stays selected: order accepted is not goods received.
    execution.completed_at = datetime.now(timezone.utc)
    session.flush()
    return execution, True
