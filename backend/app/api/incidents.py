import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Incident
from app.schemas.incidents import (
    IncidentCreateRequest,
    IncidentResponse,
)
from app.services.incidents import (
    IncidentConflictError,
    create_or_get_incident,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["Incidents"],
)


@router.post(
    "",
    response_model=IncidentResponse,
    status_code=201,
    responses={
        200: {"description": "Existing matching incident returned"},
        409: {"description": "Source reference has conflicting details"},
    },
)
def create_incident(
    request: IncidentCreateRequest,
    response: Response,
) -> IncidentResponse:
    try:
        with Session(engine) as session:
            with session.begin():
                incident, created = create_or_get_incident(
                    session=session,
                    **request.model_dump(),
                )

                result = IncidentResponse.model_validate(incident)

            # The transaction has committed before returning success.
            response.status_code = 201 if created else 200
            return result

    except IncidentConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from None

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from None

    except SQLAlchemyError as exc:
        logger.error(
            "Incident create database error: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to save incident.",
        ) from None


@router.get(
    "/{incident_id}",
    response_model=IncidentResponse,
)
def get_incident(incident_id: UUID) -> IncidentResponse:
    try:
        with Session(engine) as session:
            incident = session.get(Incident, incident_id)

            if incident is None:
                raise HTTPException(
                    status_code=404,
                    detail="Incident not found.",
                )

            return IncidentResponse.model_validate(incident)

    except SQLAlchemyError as exc:
        logger.error(
            "Incident read database error: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to read incident.",
        ) from None