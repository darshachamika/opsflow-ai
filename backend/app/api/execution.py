from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.approval_auth import Actor, current_actor, require_manager
from app.core.database import engine
from app.models.execution import RecoveryExecution
from app.schemas.execution import ExecutionResponse
from app.services.execution import ExecutionConflict, ExecutionNotFound, execute_mock

router = APIRouter(prefix="/api/v1", tags=["Mock execution"])


@router.post("/proposals/{proposal_id}/execute-mock", response_model=ExecutionResponse, status_code=201)
def execute(proposal_id: UUID, response: Response,
            actor: Annotated[Actor, Depends(require_manager)]) -> ExecutionResponse:
    try:
        with engine.connect().execution_options(isolation_level="READ COMMITTED") as connection:
            with Session(bind=connection) as session, session.begin():
                record, created = execute_mock(session=session, proposal_id=proposal_id, actor=actor)
                result = ExecutionResponse.model_validate(record)
        response.status_code = 409 if result.status == "FAILED" else (201 if created else 200)
        return result
    except ExecutionNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except ExecutionConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    except SQLAlchemyError:
        raise HTTPException(503, "Execution transaction failed. Retry the same proposal ID; no new key is needed.") from None


@router.get("/proposals/{proposal_id}/execution", response_model=ExecutionResponse)
def get_execution(proposal_id: UUID, actor: Annotated[Actor, Depends(current_actor)]) -> ExecutionResponse:
    try:
        with Session(engine) as session:
            record = session.scalar(select(RecoveryExecution).where(RecoveryExecution.proposal_id == proposal_id))
            if record is None:
                raise HTTPException(404, "Execution not found.")
            return ExecutionResponse.model_validate(record)
    except SQLAlchemyError:
        raise HTTPException(503, "Execution lookup unavailable.") from None
