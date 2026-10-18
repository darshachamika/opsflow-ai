"""Transactional consumer for approved LOCAL MOCK jobs; no external calls."""
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.core.database import engine
from app.models import Incident, RecoveryProposal
from app.models.approval import ApprovalResumeJob
from app.services.execution import execute_mock, ExecutionConflict, ExecutionNotFound


def process_next(actor, *, incident_id=None):
    if actor.role != "PROCUREMENT_MANAGER":
        raise PermissionError("Procurement manager permission required.")
    with engine.connect().execution_options(isolation_level="READ COMMITTED") as connection:
        with Session(bind=connection) as session, session.begin():
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            session.execute(text("SET LOCAL statement_timeout = '15s'"))
            # Same lock order as HTTP execution: incident -> proposal -> resume job.
            # Lock held until local mock effects and job outcome commit together.
            candidate = (
                select(Incident.id)
                .join(RecoveryProposal, RecoveryProposal.incident_id == Incident.id)
                .join(ApprovalResumeJob, ApprovalResumeJob.proposal_id == RecoveryProposal.id)
                .where(ApprovalResumeJob.status == "PENDING")
                .order_by(ApprovalResumeJob.created_at, ApprovalResumeJob.id)
                .with_for_update(of=Incident, skip_locked=True).limit(1)
            )
            if incident_id is not None:
                candidate = candidate.where(Incident.id == incident_id)
            selected_incident_id = session.scalar(candidate)
            if selected_incident_id is None:
                return None
            proposal = session.scalar(
                select(RecoveryProposal)
                .join(ApprovalResumeJob, ApprovalResumeJob.proposal_id == RecoveryProposal.id)
                .where(RecoveryProposal.incident_id == selected_incident_id, ApprovalResumeJob.status == "PENDING")
                .order_by(ApprovalResumeJob.created_at, ApprovalResumeJob.id)
                .with_for_update(of=RecoveryProposal).limit(1)
            )
            # A concurrent HTTP executor may have completed it before our lock was obtained.
            if proposal is None:
                return None
            job = session.scalar(select(ApprovalResumeJob).where(
                ApprovalResumeJob.proposal_id == proposal.id).with_for_update())
            if job.status != "PENDING":
                return None
            try:
                execution, _ = execute_mock(session=session, proposal_id=proposal.id, actor=actor)
            except (ExecutionConflict, ExecutionNotFound):
                # Preconditions rejected before execution record creation. Never retry by
                # bypassing approval binding. Retain the original binding fields.
                job.status = "FAILED"
                job.payload = {**job.payload, "resume_failure_code": "EXECUTION_PRECONDITION_FAILED"}
                outcome = {"job_id": str(job.id), "proposal_id": str(proposal.id),
                           "status": "FAILED", "execution_id": None}
            else:
                # Also reconcile an already-existing idempotent execution record.
                if execution.status not in {"SUCCEEDED", "FAILED"}:
                    raise RuntimeError("Unexpected nonterminal local mock execution.")
                job.status = "COMPLETED" if execution.status == "SUCCEEDED" else "FAILED"
                outcome = {"job_id": str(job.id), "proposal_id": str(proposal.id),
                           "status": job.status, "execution_id": str(execution.id)}
            session.flush()
        return outcome
