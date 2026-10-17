from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError
from app.core.approval_auth import Actor, current_actor
from app.schemas.orchestration import OrchestrationRequest
from app.services import workflows
from app.services.impact_assessment import ImpactTargetNotFound
from app.services.orchestration import IncidentNotOpen

router = APIRouter(prefix="/api/v1", tags=["Workflow history"])
ActorDependency = Annotated[Actor, Depends(current_actor)]


def invoke(call):
    try:
        return call()
    except ImpactTargetNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except (workflows.WorkflowConflict, IncidentNotOpen) as exc:
        raise HTTPException(409, str(exc)) from None
    except SQLAlchemyError:
        raise HTTPException(503, "Workflow database unavailable. Retry using the same idempotency key.") from None


@router.post("/incidents/{incident_id}/runs", status_code=201)
def start_run(incident_id: UUID, body: OrchestrationRequest, response: Response,
              actor: ActorDependency,
              key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]):
    run, created = invoke(lambda: workflows.create_run(incident_id, body, actor.subject, key))
    response.status_code = 202 if run["status"] == "RUNNING" else (201 if created else 200)
    response.headers["Location"] = f'/api/v1/runs/{run["id"]}'
    return run


@router.get("/runs/{run_id}")
def read_run(run_id: UUID, actor: ActorDependency):
    return invoke(lambda: workflows.get_run(run_id))


@router.get("/incidents/{incident_id}/runs")
def history(incident_id: UUID, actor: ActorDependency,
            limit: Annotated[int, Query(ge=1, le=100)] = 20,
            offset: Annotated[int, Query(ge=0)] = 0):
    return invoke(lambda: workflows.list_runs(incident_id, limit, offset))
