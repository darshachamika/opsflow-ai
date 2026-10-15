import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.impact import ImpactResponse
from app.services.impact_assessment import (
    ImpactTargetNotFound,
    assess_product_impact,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Impact"],
)


@router.get(
    "/impact",
    response_model=ImpactResponse,
    responses={
        404: {"description": "Product or plant not found"},
        503: {"description": "Database operation failed"},
    },
)
def get_impact(
    sku: str = Query(
        ...,
        min_length=1,
        max_length=64,
        description="Product SKU, for example FAN-MOTOR-45W",
    ),
    plant_code: str = Query(
        ...,
        min_length=1,
        max_length=64,
        description="Plant code, for example LK-HOM-PLANT",
    ),
) -> ImpactResponse:
    sku = sku.strip()
    plant_code = plant_code.strip()

    if not sku or not plant_code:
        raise HTTPException(
            status_code=422,
            detail="sku and plant_code must not be blank.",
        )

    try:
        result = assess_product_impact(
            sku=sku,
            plant_code=plant_code,
        )
    except ImpactTargetNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from None
    except SQLAlchemyError as exc:
        # Log the error type without logging SQL parameters or credentials.
        logger.error(
            "Impact database operation failed: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to read impact data from the database.",
        ) from None

    return ImpactResponse.model_validate(result)