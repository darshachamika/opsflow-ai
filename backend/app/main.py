from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.impact import router as impact_router
from app.core.database import engine
from app.api.recovery import router as recovery_router
from app.api.incidents import router as incidents_router
from app.api.proposals import router as proposals_router

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

app.include_router(impact_router)
app.include_router(recovery_router)
app.include_router(incidents_router)
app.include_router(proposals_router)


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
app.include_router(approvals_router)

from app.api.execution import router as execution_router
app.include_router(execution_router)

from app.api.orchestration import router as orchestration_router
app.include_router(orchestration_router)

from app.api.workflows import router as workflows_router
app.include_router(workflows_router)

from app.api.workflow_queue import router as workflow_queue_router
app.include_router(workflow_queue_router)
