"""Read-only incident planning. No proposal, approval, or execution is created."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Incident, Location, Product
from app.schemas.orchestration import OrchestrationRequest
from app.services.impact_assessment import ImpactTargetNotFound, _assess
from app.services.purchase_recommendation import _recommend_purchases
from app.services.transfer_recommendation import _recommend_transfer


class IncidentNotOpen(ValueError):
    pass


USABLE = {"FULL_COVERAGE", "PARTIAL_COVERAGE"}


def summarize(impact: dict, transfer: dict | None, purchase: dict | None) -> dict:
    """Deterministic decision boundary; explanations cannot alter calculations."""
    if impact["status"] not in {"ASSESSED", "NO_OPEN_DEMANDS"}:
        return {"status": "NEEDS_EVIDENCE", "explanation": "Update supply evidence before planning recovery.", "next_action": "REFRESH_EVIDENCE"}
    shortage = sum((Decimal(a["shortage_qty"]) for a in impact["allocations"]), Decimal("0"))
    if shortage == 0:
        return {"status": "NO_ACTION_NEEDED", "explanation": "The assessed demand pool has no uncovered shortage.", "next_action": "NONE"}
    transfer_usable = transfer is not None and transfer["status"] in USABLE
    purchase_usable = purchase is not None and any(o["status"] in USABLE for o in purchase["options"])
    if transfer_usable or purchase_usable:
        return {"status": "OPTIONS_READY", "explanation": f"Assessed shortage is {shortage}. Review the independent recovery alternatives, then create a proposal for manager approval.", "next_action": "SELECT_AND_CREATE_PROPOSAL"}
    incomplete = any(r is not None and r["status"] == "INCOMPLETE" for r in (transfer, purchase))
    return {
        "status": "NEEDS_EVIDENCE" if incomplete else "NO_FEASIBLE_OPTION",
        "explanation": "No usable recovery alternative was established. Review evidence, timing, capacity, and supplier eligibility.",
        "next_action": "REFRESH_EVIDENCE" if incomplete else "MANUAL_REVIEW",
    }


def plan_incident(incident_id: UUID, request: OrchestrationRequest) -> dict:
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as session, session.begin():
            return _plan(session, incident_id, request, datetime.now(timezone.utc))


def _plan(session: Session, incident_id: UUID, request: OrchestrationRequest, as_of: datetime) -> dict:
    incident = session.get(Incident, incident_id)
    if incident is None:
        raise ImpactTargetNotFound("Incident not found.")
    if incident.status not in {"OPEN", "INVESTIGATING"}:
        raise IncidentNotOpen("Incident must be open or investigating.")
    product = session.get(Product, incident.product_id)
    plant = session.get(Location, incident.plant_id)
    if product is None or plant is None or plant.type != "PLANT":
        raise ImpactTargetNotFound("Incident product or plant is invalid.")
    common = dict(session=session, as_of=as_of, sku=product.sku, plant_code=plant.code)
    impact = _assess(**common)
    transfer = purchase = None
    trace = ["ASSESS_IMPACT"]
    if impact["status"] == "ASSESSED" and any(Decimal(a["shortage_qty"]) > 0 for a in impact["allocations"]):
        transfer = _recommend_transfer(
            **common, warehouse_code=request.warehouse_code,
            lead_time=timedelta(hours=request.transfer_lead_time_hours),
            fixed_transport_cost=request.transport_cost, currency=request.currency,
        )
        trace.append("EVALUATE_TRANSFER")
        purchase = _recommend_purchases(**common, freight_cost=request.purchase_freight_cost, currency=request.currency)
        trace.append("EVALUATE_PURCHASE")
    decision = summarize(impact, transfer, purchase)
    return {
        "incident_id": str(incident.id), "assessed_at": as_of.isoformat(),
        **decision, "impact": impact, "transfer": transfer, "purchase": purchase,
        "inputs": request.model_dump(mode="json"), "steps": trace,
        "explanation_source": "DETERMINISTIC_TEMPLATE", "llm_used": False,
        "execution_status": "NOT_EXECUTED", "persisted": False,
        "limitations": [
            "Options are independent alternatives; do not sum their coverage.",
            "Transfer transport cost and purchase total cost have different cost bases; no automatic price ranking is performed.",
            "This is a snapshot preview. Proposal creation, approval and execution must revalidate evidence.",
            "No durable workflow pause or resume is created by this endpoint.",
        ],
    }
