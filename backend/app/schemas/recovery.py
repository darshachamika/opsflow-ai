from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.schemas.impact import EvidenceIssue

class RecoveryRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    sku: str = Field(min_length=1, max_length=64)
    plant_code: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class TransferEvaluationRequest(RecoveryRequest):
    warehouse_code: str = Field(min_length=1, max_length=64)

    lead_time_hours: int = Field(
        ge=0,
        le=8760,
        description="Includes preparation, transport and receiving.",
    )

    fixed_transport_cost: Decimal = Field(
        ge=0,
        max_digits=18,
        decimal_places=4,
        allow_inf_nan=False,
    )


class PurchaseEvaluationRequest(RecoveryRequest):
    freight_cost: Decimal = Field(
        ge=0,
        max_digits=18,
        decimal_places=4,
        allow_inf_nan=False,
        description="Estimated freight per independent purchase option.",
    )

class RecoveryAllocationResponse(BaseModel):
    demand_id: UUID
    source_ref: str
    allocated_qty: str
    remaining_shortage_qty: str
    arrives_by_deadline: bool


class TransferPlanResponse(BaseModel):
    warehouse_name: str
    warehouse_observed_at: datetime
    arrival_at: datetime
    available_qty: str
    transfer_qty: str
    remaining_warehouse_qty: str
    remaining_shortage_qty: str
    transport_cost: str
    currency: str
    allocations: list[RecoveryAllocationResponse]


class TransferEvaluationResponse(BaseModel):
    status: Literal[
        "INCOMPLETE",
        "NO_ACTION_NEEDED",
        "NO_FEASIBLE_TRANSFER",
        "PARTIAL_COVERAGE",
        "FULL_COVERAGE",
    ]
    assessed_at: datetime
    sku: str
    plant_code: str
    warehouse_code: str
    issues: list[EvidenceIssue]
    plan: TransferPlanResponse | None
    assumptions: list[str]
    execution_status: Literal["NOT_EXECUTED"]


class PurchasePlanResponse(BaseModel):
    arrival_at: datetime | None
    purchase_qty: str
    items_cost: str
    freight_cost: str
    total_cost: str
    allocations: list[RecoveryAllocationResponse]


class PurchaseOptionResponse(BaseModel):
    offer_id: UUID
    supplier_code: str
    supplier_name: str
    observed_at: datetime
    valid_until: datetime
    unit_price: str
    currency: str
    status: Literal[
        "BLOCKED",
        "NO_ACTION_NEEDED",
        "NO_FEASIBLE_PURCHASE",
        "PARTIAL_COVERAGE",
        "FULL_COVERAGE",
    ]
    reasons: list[str]
    plan: PurchasePlanResponse | None


class PurchaseEvaluationResponse(BaseModel):
    status: Literal[
        "INCOMPLETE",
        "NO_ACTION_NEEDED",
        "NO_OFFERS",
        "OPTIONS_AVAILABLE",
        "NO_ELIGIBLE_OPTIONS",
    ]
    assessed_at: datetime
    sku: str
    plant_code: str
    issues: list[EvidenceIssue]
    options: list[PurchaseOptionResponse]
    assumptions: list[str]
    execution_status: Literal["NOT_EXECUTED"]
