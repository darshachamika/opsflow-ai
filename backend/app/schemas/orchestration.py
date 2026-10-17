from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrchestrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    warehouse_code: str = Field(min_length=1, max_length=64)
    transfer_lead_time_hours: int = Field(ge=0, le=8760)
    transport_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=4, allow_inf_nan=False)
    purchase_freight_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=4, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
