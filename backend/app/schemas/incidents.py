from datetime import datetime
from uuid import UUID
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class IncidentCreateRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    source_system: str = Field(min_length=1, max_length=64)
    source_ref: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    product_id: UUID
    plant_id: UUID
    detected_at: AwareDatetime


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_system: str
    source_ref: str
    title: str
    description: str | None
    product_id: UUID
    plant_id: UUID
    status: Literal[
        "OPEN",
        "INVESTIGATING",
        "RESOLVED",
        "CANCELLED",
    ]
    detected_at: datetime
    created_at: datetime
    updated_at: datetime