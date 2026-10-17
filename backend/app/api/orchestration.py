from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.approval_auth import Actor, current_actor
from app.schemas.orchestration import OrchestrationRequest
from app.services.impact_assessment import ImpactTargetNotFound
from app.services.orchestration import IncidentNotOpen, plan_incident
from app.services.gemini_explanation import add_explanation

router = APIRouter(prefix="/api/v1", tags=["Incident orchestration"])


@router.post("/incidents/{incident_id}/plan")
def incident_plan(incident_id: UUID, body: OrchestrationRequest,
                  actor: Annotated[Actor, Depends(current_actor)]) -> dict:
    try:
        result = plan_incident(incident_id, body)
        # The planning transaction is closed before the external LLM call.
        return add_explanation(result)
    except ImpactTargetNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except IncidentNotOpen as exc:
        raise HTTPException(409, str(exc)) from None
    except SQLAlchemyError:
        raise HTTPException(503, "Planning database temporarily unavailable.") from None
