from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    proposal_id: UUID
    execution_key: str
    requested_by: str
    status: Literal["RUNNING", "SUCCEEDED", "FAILED"]
    completed_at: datetime | None
    failure_reason: str | None
    result: dict[str, Any]
