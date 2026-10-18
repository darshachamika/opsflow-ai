"""Read-only projection of stored records, not an immutable event ledger."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import engine
from app.models import Incident, RecoveryProposal
from app.models.approval import ApprovalDecision, ApprovalResumeJob
from app.models.execution import RecoveryExecution


class HistoryNotFound(LookupError):
    pass


def timestamp(value):
    return value.isoformat() if value is not None else None


def serialize_record(proposal, decision, job, execution):
    return {
        "proposal": {"id": str(proposal.id), "version": proposal.version,
            "action_type": proposal.action_type, "current_status": proposal.status,
            "created_at": timestamp(proposal.created_at),
            "assessed_at": timestamp(proposal.assessed_at), "expires_at": timestamp(proposal.expires_at)},
        "decision": None if decision is None else {
            "id": str(decision.id), "decision": decision.decision,
            "manager_subject": decision.manager_subject, "reason": decision.reason,
            "decided_at": timestamp(decision.decided_at), "proposal_hash": decision.proposal_hash},
        "resume_job": None if job is None else {
            "id": str(job.id), "current_status": job.status,
            "created_at": timestamp(job.created_at), "updated_at": timestamp(job.updated_at),
            "failure_code": job.payload.get("resume_failure_code")},
        "execution": None if execution is None else {
            "id": str(execution.id), "status": execution.status,
            "requested_by": execution.requested_by, "created_at": timestamp(execution.created_at),
            "completed_at": timestamp(execution.completed_at), "failure_reason": execution.failure_reason,
            "mode": execution.result.get("mode"), "order_status": execution.result.get("order_status"),
            "external_ref": execution.result.get("external_ref"), "quantity": execution.result.get("quantity"),
            "physical_receipt_recorded": execution.result.get("physical_receipt_recorded")},
    }


def get_history(incident_id, *, limit=20, before_version=None):
    if not 1 <= limit <= 100 or (before_version is not None and before_version < 1):
        raise ValueError("Invalid history pagination.")
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as session, session.begin():
            incident = session.get(Incident, incident_id)
            if incident is None:
                raise HistoryNotFound("Incident not found.")
            query = (select(RecoveryProposal, ApprovalDecision, ApprovalResumeJob, RecoveryExecution)
                .outerjoin(ApprovalDecision, ApprovalDecision.proposal_id == RecoveryProposal.id)
                .outerjoin(ApprovalResumeJob, ApprovalResumeJob.proposal_id == RecoveryProposal.id)
                .outerjoin(RecoveryExecution, RecoveryExecution.proposal_id == RecoveryProposal.id)
                .where(RecoveryProposal.incident_id == incident_id))
            if before_version is not None:
                query = query.where(RecoveryProposal.version < before_version)
            rows = session.execute(query.order_by(RecoveryProposal.version.desc()).limit(limit + 1)).all()
            has_more = len(rows) > limit
            page = rows[:limit]
            return {"incident_id": str(incident.id), "incident_current_status": incident.status,
                "record_type": "CURRENT_RECORD_HISTORY", "immutable": False,
                "items": [serialize_record(*row) for row in page],
                "next_before_version": page[-1][0].version if has_more else None,
                "limitations": ["Shows stored proposal, decision, resume-job and execution records; not every status transition.",
                    "Current statuses may change between requests. This is not a tamper-evident ledger.",
                    "Execution acceptance does not confirm physical receipt."]}
