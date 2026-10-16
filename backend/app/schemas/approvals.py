from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class DecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=1, max_length=1000)


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    proposal_id: UUID
    manager_subject: str
    decision: Literal["APPROVED", "REJECTED"]
    reason: str
    decided_at: datetime
    proposal_hash: str
    revalidation_snapshot: dict[str, Any]
