from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TransferProposalRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    warehouse_code: str = Field(min_length=1, max_length=64)
    lead_time_hours: int = Field(ge=0, le=8760)
    fixed_transport_cost: Decimal = Field(
        ge=0,
        max_digits=18,
        decimal_places=4,
        allow_inf_nan=False,
    )
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    version: int
    action_type: Literal["WAREHOUSE_TRANSFER", "SUPPLIER_PURCHASE"]
    status: Literal[
        "PROPOSED", "APPROVED", "REJECTED", "SUPERSEDED", "EXPIRED"
    ]
    assessed_at: datetime
    expires_at: datetime
    plan_snapshot: dict[str, Any]
    evidence_snapshot: dict[str, Any]
    created_at: datetime