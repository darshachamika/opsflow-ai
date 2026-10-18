from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from app.core.approval_auth import Actor, current_actor
from app.services.incident_history import get_history, HistoryNotFound

router = APIRouter(prefix="/api/v1", tags=["Incident history"])


@router.get("/incidents/{incident_id}/history")
def history(incident_id: UUID, actor: Annotated[Actor, Depends(current_actor)],
            limit: Annotated[int, Query(ge=1, le=100)] = 20,
            before_version: Annotated[int | None, Query(ge=1)] = None):
    try:
        return get_history(incident_id, limit=limit, before_version=before_version)
    except HistoryNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except SQLAlchemyError:
        raise HTTPException(503, "Incident history unavailable.") from None
