"""PostgreSQL queue for planning-only jobs. No ERP execution is performed."""
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, or_, and_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Incident
from app.models.workflow import WorkflowRun, WorkflowStep
from app.models.workflow_job import WorkflowJob, WorkflowAttempt
from app.schemas.orchestration import OrchestrationRequest
from app.services import workflows
from app.services.orchestration import plan_incident, IncidentNotOpen
from app.services.impact_assessment import ImpactTargetNotFound
from app.services.gemini_explanation import add_explanation

MAX_ATTEMPTS = 3
LEASE_SECONDS = 120


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    run_id: UUID
    incident_id: UUID
    token: UUID
    inputs: dict


def enqueue(incident_id, body, subject, key):
    inputs = workflows.normalize_inputs(body)
    digest = workflows.fingerprint(incident_id, inputs)
    try:
        with Session(engine) as session, session.begin():
            previous = workflows._existing(session, subject, key, digest)
            if previous is not None:
                return previous.id
            incident = session.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
            if incident is None:
                raise ImpactTargetNotFound("Incident not found.")
            previous = workflows._existing(session, subject, key, digest)
            if previous is not None:
                return previous.id
            if incident.status not in {"OPEN", "INVESTIGATING"}:
                raise IncidentNotOpen("Incident must be open or investigating.")
            now = session.scalar(select(func.clock_timestamp()))
            run = WorkflowRun(incident_id=incident_id, requested_by=subject, idempotency_key=key,
                request_hash=digest, inputs=inputs, status="RUNNING")
            session.add(run)
            session.flush()
            session.add(WorkflowJob(run_id=run.id, status="QUEUED", attempts=0, available_at=now))
            # Run and job are committed atomically. No Gemini call in the HTTP request.
            return run.id
    except IntegrityError:
        with Session(engine) as session:
            previous = workflows._existing(session, subject, key, digest)
            if previous is not None:
                return previous.id
        raise


def _fail_run(session, run_id, now, code):
    run = session.get(WorkflowRun, run_id)
    run.status = "FAILED"
    run.completed_at = now
    run.error_code = code


def claim_one(worker_id: str) -> Claim | None:
    if not worker_id or len(worker_id) > 128:
        raise ValueError("Worker ID must have 1-128 characters.")
    with Session(engine) as session, session.begin():
        now = session.scalar(select(func.clock_timestamp()))
        job = session.scalar(select(WorkflowJob).where(or_(
            and_(WorkflowJob.status == "QUEUED", WorkflowJob.available_at <= now),
            and_(WorkflowJob.status == "RUNNING", WorkflowJob.lease_until <= now),
        )).order_by(WorkflowJob.available_at, WorkflowJob.id).with_for_update(skip_locked=True).limit(1))
        if job is None:
            return None
        if job.status == "RUNNING":
            old = session.scalar(select(WorkflowAttempt).where(WorkflowAttempt.job_id == job.id, WorkflowAttempt.number == job.attempts))
            old.status = "LEASE_EXPIRED"
            old.finished_at = now
            old.error_code = "WORKER_LEASE_EXPIRED"
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "FAILED"
            job.lease_until = job.lease_token = None
            _fail_run(session, job.run_id, now, "RETRY_EXHAUSTED")
            return None
        run = session.get(WorkflowRun, job.run_id)
        job.attempts += 1
        job.status = "RUNNING"
        job.lease_token = uuid4()
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        session.add(WorkflowAttempt(job_id=job.id, number=job.attempts, worker_id=worker_id,
            status="RUNNING", started_at=now))
        return Claim(job.id, job.run_id, run.incident_id, job.lease_token, dict(run.inputs))


def finish(claim: Claim, result=None, error_code=None, retryable=False) -> bool:
    with Session(engine) as session, session.begin():
        job = session.scalar(select(WorkflowJob).where(WorkflowJob.id == claim.job_id).with_for_update())
        now = session.scalar(select(func.clock_timestamp()))
        # Fencing: an expired or replaced owner cannot write run results.
        if job is None or job.status != "RUNNING" or job.lease_token != claim.token or job.lease_until <= now:
            return False
        attempt = session.scalar(select(WorkflowAttempt).where(WorkflowAttempt.job_id == job.id, WorkflowAttempt.number == job.attempts))
        attempt.finished_at = now
        attempt.error_code = error_code
        job.lease_token = job.lease_until = None
        if error_code:
            attempt.status = "FAILED"
            if retryable and job.attempts < MAX_ATTEMPTS:
                job.status = "QUEUED"
                job.available_at = now + timedelta(seconds=5 * 2 ** (job.attempts - 1))
            else:
                job.status = "FAILED"
                _fail_run(session, job.run_id, now, error_code)
            return True
        if result is None:
            raise ValueError("Successful completion requires a result.")
        # Keep the lease/status constraint valid before session.get() autoflushes.
        job.status = "COMPLETED"
        run = session.get(WorkflowRun, job.run_id)
        run.result = {**result, "persisted": True, "workflow_run_id": str(run.id)}
        run.status = "SUCCEEDED"
        run.error_code = None
        run.completed_at = now
        attempt.status = "SUCCEEDED"
        for sequence, name in enumerate(["PLAN_INCIDENT", *result["steps"], "EXPLAIN_RESULT"], 1):
            session.add(WorkflowStep(run_id=run.id, sequence=sequence, name=name, status="COMPLETED"))
        return True


def process_one(worker_id: str) -> bool:
    claim = claim_one(worker_id)
    if claim is None:
        return False
    try:
        result = plan_incident(claim.incident_id, OrchestrationRequest(**claim.inputs))
        result = add_explanation(result)
    except (ImpactTargetNotFound, IncidentNotOpen):
        finish(claim, error_code="INCIDENT_CHANGED")
    except SQLAlchemyError:
        # No acknowledgement: after DB recovery, the expired lease becomes claimable.
        raise
    except Exception:
        finish(claim, error_code="PLANNING_FAILED", retryable=True)
    else:
        finish(claim, result=result)
    return True


def job_history(run_id):
    with Session(engine) as session:
        if session.get(WorkflowRun, run_id) is None:
            raise ImpactTargetNotFound("Workflow run not found.")
        job = session.scalar(select(WorkflowJob).where(WorkflowJob.run_id == run_id))
        if job is None:
            return {"run_id": str(run_id), "mode": "SYNCHRONOUS", "job": None, "attempts": []}
        attempts = session.scalars(select(WorkflowAttempt).where(WorkflowAttempt.job_id == job.id).order_by(WorkflowAttempt.number)).all()
        return {"run_id": str(run_id), "mode": "QUEUED", "job": {
            "status": job.status, "attempt_count": job.attempts,
            "available_at": job.available_at.isoformat(),
            "lease_until": job.lease_until.isoformat() if job.lease_until else None},
            "attempts": [{"number": a.number, "worker_id": a.worker_id, "status": a.status,
                "started_at": a.started_at.isoformat(), "finished_at": a.finished_at.isoformat() if a.finished_at else None,
                "error_code": a.error_code} for a in attempts]}
