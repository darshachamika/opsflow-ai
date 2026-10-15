from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class EvidenceIssue(BaseModel):
    code: str
    reference: str
    message: str


class InboundAllocationResponse(BaseModel):
    shipment_line_id: UUID
    quantity: str


class DemandAllocationResponse(BaseModel):
    demand_id: UUID
    source_ref: str
    required_at: datetime
    remaining_demand: str
    stock_allocated_qty: str
    inbound_allocated_qty: str
    shortage_qty: str
    inbound_allocations: list[InboundAllocationResponse]


class ImpactResponse(BaseModel):
    status: Literal[
        "ASSESSED",
        "INCOMPLETE",
        "NO_OPEN_DEMANDS",
    ]
    assessed_at: datetime
    sku: str
    plant_code: str
    plant_name: str
    issues: list[EvidenceIssue]
    allocations: list[DemandAllocationResponse]
    assumptions: list[str] = Field(default_factory=list)