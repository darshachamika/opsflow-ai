import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.recovery import (
    PurchaseEvaluationRequest,
    PurchaseEvaluationResponse,
    TransferEvaluationRequest,
    TransferEvaluationResponse,
)
from app.services.impact_assessment import ImpactTargetNotFound
from app.services.purchase_recommendation import (
    recommend_supplier_purchases,
)
from app.services.transfer_recommendation import (
    recommend_warehouse_transfer,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/recovery",
    tags=["Recovery"],
)


@router.post(
    "/transfers/evaluate",
    response_model=TransferEvaluationResponse,
)
def evaluate_transfer(request: TransferEvaluationRequest) -> dict:
    try:
        return recommend_warehouse_transfer(
            sku=request.sku,
            plant_code=request.plant_code,
            warehouse_code=request.warehouse_code,
            lead_time=timedelta(hours=request.lead_time_hours),
            fixed_transport_cost=request.fixed_transport_cost,
            currency=request.currency,
        )
    except ImpactTargetNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from None
    except SQLAlchemyError as exc:
        logger.error(
            "Transfer evaluation database error: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to read recovery data from the database.",
        ) from None


@router.post(
    "/purchases/evaluate",
    response_model=PurchaseEvaluationResponse,
)
def evaluate_purchase(request: PurchaseEvaluationRequest) -> dict:
    try:
        return recommend_supplier_purchases(
            sku=request.sku,
            plant_code=request.plant_code,
            freight_cost=request.freight_cost,
            currency=request.currency,
        )
    except ImpactTargetNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from None
    except SQLAlchemyError as exc:
        logger.error(
            "Purchase evaluation database error: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to read recovery data from the database.",
        ) from None