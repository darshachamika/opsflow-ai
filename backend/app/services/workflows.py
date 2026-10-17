"""Persist synchronous planning runs, with no automatic execution or crash resume."""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Incident
from app.models.workflow import WorkflowRun, WorkflowStep
from app.schemas.orchestration import OrchestrationRequest
from app.services.orchestration import IncidentNotOpen, plan_incident
from app.services.impact_assessment import ImpactTargetNotFound
from app.services.gemini_explanation import add_explanation


class WorkflowConflict(ValueError):
    pass


def normalize_inputs(body: OrchestrationRequest) -> dict:
    inputs = body.model_dump(mode="json")
    for key in ("transport_cost", "purchase_freight_cost"):
        value = Decimal(inputs[key])
        inputs[key] = "0" if value == 0 else format(value.normalize(), "f")
    return inputs


def fingerprint(incident_id: UUID, inputs: dict) -> str:
    return sha256(json.dumps({"schema": 1, "incident_id": str(incident_id), "inputs": inputs}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def serialize(session: Session, run: WorkflowRun) -> dict:
    steps = session.scalars(select(WorkflowStep).where(WorkflowStep.run_id == run.id).order_by(WorkflowStep.sequence)).all()
    return {"id": str(run.id), "incident_id": str(run.incident_id), "requested_by": run.requested_by,
            "status": run.status, "inputs": run.inputs, "result": run.result,
            "error_code": run.error_code, "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "steps": [{"sequence": step.sequence, "name": step.name, "status": step.status} for step in steps]}


def get_run(run_id: UUID) -> dict:
    with Session(engine) as session:
        run = session.get(WorkflowRun, run_id)
        if run is None:
            raise ImpactTargetNotFound("Workflow run not found.")
        return serialize(session, run)


def list_runs(incident_id: UUID, limit: int, offset: int) -> dict:
    with Session(engine) as session:
        if session.get(Incident, incident_id) is None:
            raise ImpactTargetNotFound("Incident not found.")
        runs = session.scalars(select(WorkflowRun).where(WorkflowRun.incident_id == incident_id)
            .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc()).limit(limit).offset(offset)).all()
        return {"items": [{"id": str(r.id), "status": r.status, "created_at": r.created_at.isoformat(),
                           "error_code": r.error_code} for r in runs], "limit": limit, "offset": offset}


def _existing(session, subject, key, digest):
    row = session.scalar(select(WorkflowRun).where(WorkflowRun.requested_by == subject, WorkflowRun.idempotency_key == key))
    if row is not None and row.request_hash != digest:
        raise WorkflowConflict("Idempotency key already used with different inputs.")
    return row


def _claim(incident_id, body, subject, key):
    inputs = normalize_inputs(body)
    digest = fingerprint(incident_id, inputs)
    try:
        with Session(engine) as session, session.begin():
            previous = _existing(session, subject, key, digest)
            if previous is not None:
                return previous.id, False
            # Short lock only for creation; no LLM call or planning while held.
            incident = session.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
            if incident is None:
                raise ImpactTargetNotFound("Incident not found.")
            previous = _existing(session, subject, key, digest)
            if previous is not None:
                return previous.id, False
            if incident.status not in {"OPEN", "INVESTIGATING"}:
                raise IncidentNotOpen("Incident must be open or investigating.")
            run = WorkflowRun(incident_id=incident_id, requested_by=subject, idempotency_key=key,
                request_hash=digest, inputs=inputs, status="RUNNING")
            session.add(run)
            session.flush()
            session.add(WorkflowStep(run_id=run.id, sequence=1, name="PLAN_INCIDENT", status="RUNNING"))
            return run.id, True
    except IntegrityError:
        # Handles the same actor/key racing across different incidents as well.
        with Session(engine) as session:
            previous = _existing(session, subject, key, digest)
            if previous is not None:
                return previous.id, False
        raise


def _save_plan(run_id, result):
    with Session(engine) as session, session.begin():
        run = session.get(WorkflowRun, run_id)
        run.result = {**result, "persisted": True, "workflow_run_id": str(run_id)}
        step = session.scalar(select(WorkflowStep).where(WorkflowStep.run_id == run_id, WorkflowStep.sequence == 1))
        step.status = "COMPLETED"
        for sequence, name in enumerate(result["steps"], 2):
            session.add(WorkflowStep(run_id=run_id, sequence=sequence, name=name, status="COMPLETED"))
        session.add(WorkflowStep(run_id=run_id, sequence=len(result["steps"]) + 2, name="EXPLAIN_RESULT", status="RUNNING"))


def _finish(run_id, result=None, error_code=None):
    with Session(engine) as session, session.begin():
        run = session.get(WorkflowRun, run_id)
        if result is not None:
            run.result = {**result, "persisted": True, "workflow_run_id": str(run_id)}
        run.status = "FAILED" if error_code else "SUCCEEDED"
        run.error_code = error_code
        run.completed_at = datetime.now(timezone.utc)
        steps = session.scalars(select(WorkflowStep).where(WorkflowStep.run_id == run_id, WorkflowStep.status == "RUNNING")).all()
        for step in steps:
            step.status = "FAILED" if error_code else "COMPLETED"


def create_run(incident_id: UUID, body: OrchestrationRequest, subject: str, key: str) -> tuple[dict, bool]:
    run_id, created = _claim(incident_id, body, subject, key)
    if not created:
        return get_run(run_id), False
    try:
        result = plan_incident(incident_id, body)
        _save_plan(run_id, result)
        # All DB transactions have closed before the external provider call.
        result = add_explanation(result)
        _finish(run_id, result=result)
    except (ImpactTargetNotFound, IncidentNotOpen):
        _finish(run_id, error_code="INCIDENT_CHANGED")
    except SQLAlchemyError:
        # Do not claim completion if the database cannot persist it.
        raise
    except Exception:
        # Never store exception text, SQL parameters, keys or source payloads.
        _finish(run_id, error_code="PLANNING_FAILED")
    return get_run(run_id), True
