from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Header, Response
from app.api.workflows import ActorDependency, invoke
from app.schemas.orchestration import OrchestrationRequest
from app.services import workflows, workflow_queue

router = APIRouter(prefix="/api/v1", tags=["Workflow queue"])


@router.post("/incidents/{incident_id}/queued-runs", status_code=202)
def queue_run(incident_id: UUID, body: OrchestrationRequest, response: Response,
              actor: ActorDependency,
              key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]):
    run_id = invoke(lambda: workflow_queue.enqueue(incident_id, body, actor.subject, key))
    run = invoke(lambda: workflows.get_run(run_id))
    response.status_code = 202 if run["status"] == "RUNNING" else 200
    response.headers["Location"] = f"/api/v1/runs/{run_id}"
    return run


@router.get("/runs/{run_id}/job")
def queue_status(run_id: UUID, actor: ActorDependency):
    return invoke(lambda: workflow_queue.job_history(run_id))
