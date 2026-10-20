from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.approval_auth import current_actor
from app.core.web_config import web_settings
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.impact import router as impact_router
from app.core.database import engine
from app.api.recovery import router as recovery_router
from app.api.incidents import router as incidents_router
from app.api.proposals import router as proposals_router
from app.api.incident_history import router as incident_history_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(
    title="OpsFlow AI API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=web_settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

app.include_router(impact_router, dependencies=[Depends(current_actor)])
app.include_router(recovery_router, dependencies=[Depends(current_actor)])
app.include_router(incidents_router, dependencies=[Depends(current_actor)])
app.include_router(proposals_router, dependencies=[Depends(current_actor)])
app.include_router(incident_history_router, dependencies=[Depends(current_actor)])


@app.get("/health/live", tags=["Health"])
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
def health_ready() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from None

    return {"status": "ready", "database": "connected"}

from app.api.approvals import router as approvals_router
app.include_router(approvals_router, dependencies=[Depends(current_actor)])

from app.api.execution import router as execution_router
app.include_router(execution_router, dependencies=[Depends(current_actor)])

from app.api.orchestration import router as orchestration_router
app.include_router(orchestration_router, dependencies=[Depends(current_actor)])

from app.api.workflows import router as workflows_router
app.include_router(workflows_router, dependencies=[Depends(current_actor)])

from app.api.workflow_queue import router as workflow_queue_router
app.include_router(workflow_queue_router, dependencies=[Depends(current_actor)])

from app.api.web_auth import router as web_auth_router
app.include_router(web_auth_router)
from app.api.workspace import router as workspace_router
app.include_router(workspace_router, dependencies=[Depends(current_actor)])
