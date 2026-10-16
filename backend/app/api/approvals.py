import logging
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.database import engine
from app.core.approval_auth import Actor, current_actor, require_manager
from app.models.approval import ApprovalDecision
from app.schemas.approvals import DecisionRequest, DecisionResponse
from app.services.approval_binding import ApprovalConflict
from app.services.approvals import ApprovalNotFound, decide_proposal

router = APIRouter(prefix="/api/v1", tags=["Approvals"])
logger = logging.getLogger(__name__)


@router.get("/auth/me")
def auth_me(actor: Annotated[Actor, Depends(current_actor)]) -> dict[str, str]:
    return {"subject": actor.subject, "role": actor.role}


@router.post("/proposals/{proposal_id}/decision", response_model=DecisionResponse, status_code=201)
def submit_decision(proposal_id: UUID, request: DecisionRequest, response: Response,
    actor: Annotated[Actor, Depends(require_manager)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> DecisionResponse:
    if not idempotency_key.strip():
        raise HTTPException(422, "Idempotency-Key must not be blank.")
    try:
        with engine.connect().execution_options(isolation_level="READ COMMITTED") as connection:
            with Session(bind=connection) as session, session.begin():
                event, created = decide_proposal(session=session, proposal_id=proposal_id,
                    actor=actor, decision=request.decision, reason=request.reason,
                    idempotency_key=idempotency_key)
                result = DecisionResponse.model_validate(event)
            response.status_code = 201 if created else 200
            return result
    except ApprovalNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except (ApprovalConflict, ValueError) as exc:
        raise HTTPException(409, str(exc)) from None
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    except IntegrityError:
        raise HTTPException(409, "Conflicting decision. Retry the original request with the same key.") from None
    except SQLAlchemyError as exc:
        logger.error("Approval database failure: %s", type(exc).__name__)
        raise HTTPException(503, "Unable to persist approval decision.") from None


@router.get("/proposals/{proposal_id}/decision", response_model=DecisionResponse)
def get_decision(proposal_id: UUID, actor: Annotated[Actor, Depends(current_actor)]) -> DecisionResponse:
    try:
        with Session(engine) as session:
            event = session.scalar(select(ApprovalDecision).where(ApprovalDecision.proposal_id == proposal_id))
            if event is None:
                raise HTTPException(404, "Decision not found.")
            return DecisionResponse.model_validate(event)
    except SQLAlchemyError:
        raise HTTPException(503, "Unable to read decision.") from None
