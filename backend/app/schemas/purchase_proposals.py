from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PurchaseProposalRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    offer_id: UUID
    freight_cost: Decimal = Field(
        ge=0, max_digits=18, decimal_places=4, allow_inf_nan=False
    )
    currency: str = Field(pattern=r"^[A-Z]{3}$")
