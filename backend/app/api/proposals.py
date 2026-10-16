import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Incident, Location, Product, RecoveryProposal
from app.schemas.proposals import (
    ProposalResponse,
    TransferProposalRequest,
)
from app.schemas.purchase_proposals import PurchaseProposalRequest
from app.services.purchase_recommendation import recommend_supplier_purchases
from app.services.proposal_validity import proposal_expiry
from app.services.impact_assessment import ImpactTargetNotFound
from app.services.proposals import ProposalConflictError, save_proposal
from app.services.transfer_recommendation import (
    recommend_warehouse_transfer,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Proposals"],
)


def _request_hash(request: TransferProposalRequest | PurchaseProposalRequest) -> str:
    parameters = request.model_dump(mode="json")

    # Equivalent monetary inputs, such as 18000 and 18000.00,
    # must produce the same fingerprint.
    is_purchase = isinstance(request, PurchaseProposalRequest)
    amount_field = "freight_cost" if is_purchase else "fixed_transport_cost"
    amount = getattr(request, amount_field)
    parameters[amount_field] = (
        "0" if amount == 0 else format(amount.normalize(), "f")
    )

    payload = {
        "action_type": "SUPPLIER_PURCHASE" if is_purchase else "WAREHOUSE_TRANSFER",
        "parameters": parameters,
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _find_replay(
    session: Session,
    incident_id: UUID,
    key: str,
    request_hash: str,
) -> RecoveryProposal | None:
    proposal = session.scalar(
        select(RecoveryProposal).where(
            RecoveryProposal.incident_id == incident_id,
            RecoveryProposal.idempotency_key == key,
        )
    )

    if proposal is not None and proposal.request_hash != request_hash:
        raise HTTPException(
            status_code=409,
            detail="Idempotency key already used with different inputs.",
        )

    return proposal


@router.post(
    "/incidents/{incident_id}/proposals/transfer",
    response_model=ProposalResponse,
    status_code=201,
    responses={
        200: {"description": "Previously saved proposal returned"},
        409: {"description": "Conflicting request or unusable assessment"},
    },
)
def create_transfer_proposal(
    incident_id: UUID,
    request: TransferProposalRequest,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ],
) -> ProposalResponse:
    key = idempotency_key.strip()

    if not key:
        raise HTTPException(422, "Idempotency-Key must not be blank.")

    fingerprint = _request_hash(request)

    try:
        with Session(engine) as session:
            incident = session.get(Incident, incident_id)

            if incident is None:
                raise HTTPException(404, "Incident not found.")

            replay = _find_replay(
                session, incident_id, key, fingerprint
            )

            if replay is not None:
                response.status_code = 200
                return ProposalResponse.model_validate(replay)

            if incident.status not in ("OPEN", "INVESTIGATING"):
                raise HTTPException(409, "Incident is not open.")

            product = session.get(Product, incident.product_id)
            plant = session.get(Location, incident.plant_id)

            if product is None or plant is None:
                raise HTTPException(409, "Incident scope is invalid.")

            product_id = product.id
            plant_id = plant.id
            sku = product.sku
            plant_code = plant.code

        evaluation = recommend_warehouse_transfer(
            sku=sku,
            plant_code=plant_code,
            warehouse_code=request.warehouse_code,
            lead_time=timedelta(hours=request.lead_time_hours),
            fixed_transport_cost=request.fixed_transport_cost,
            currency=request.currency,
            include_evidence=True,
        )

        # READ COMMITTED transaction: lock before assigning a version
        # and checking whether another request already saved this key.
        with Session(engine) as session:
            with session.begin():
                incident = session.scalar(
                    select(Incident)
                    .where(Incident.id == incident_id)
                    .with_for_update()
                )

                if incident is None:
                    raise HTTPException(404, "Incident not found.")

                replay = _find_replay(
                    session, incident_id, key, fingerprint
                )

                if replay is not None:
                    result = ProposalResponse.model_validate(replay)
                    created = False
                else:
                    if (
                        incident.product_id != product_id
                        or incident.plant_id != plant_id
                    ):
                        raise HTTPException(
                            409,
                            "Incident scope changed. Evaluate again.",
                        )

                    if evaluation["status"] not in (
                        "FULL_COVERAGE",
                        "PARTIAL_COVERAGE",
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "message": "No usable transfer proposal.",
                                "assessment_status": evaluation["status"],
                                "issues": evaluation["issues"],
                            },
                        )

                    evidence = evaluation.pop("_evidence", None)
                    if not evidence or evidence["scope"]["product_id"] != str(product_id) or evidence["scope"]["plant_id"] != str(plant_id):
                        raise HTTPException(409, "Assessment evidence does not match incident scope.")
                    evidence["assumptions"] = list(evaluation["assumptions"])
                    evidence["parameters"] = request.model_dump(mode="json")
                    evidence["policy"] = {
                        "max_proposal_age_seconds": 300,
                        "max_supply_age_seconds": 1800,
                        "allocation": "EARLIEST_DEADLINE_FIRST",
                        "execution_status": "NOT_EXECUTED",
                    }
                    assessed_at = datetime.fromisoformat(
                        evaluation["assessed_at"]
                    )

                    proposal = save_proposal(
                        session=session,
                        incident_id=incident_id,
                        action_type="WAREHOUSE_TRANSFER",
                        assessed_at=assessed_at,
                        expires_at=proposal_expiry(
                            assessed_at=assessed_at, evidence=evidence,
                            plan=evaluation["plan"],
                            lead_time=timedelta(hours=request.lead_time_hours),
                        ),
                        plan_snapshot={
                            "schema_version": 2,
                            "evaluation": evaluation,
                            "parameters": request.model_dump(mode="json"),
                        },
                        evidence_snapshot=evidence,
                    )

                    # Both fields are persisted atomically with the proposal.
                    proposal.idempotency_key = key
                    proposal.request_hash = fingerprint
                    session.flush()

                    result = ProposalResponse.model_validate(proposal)
                    created = True

            response.status_code = 201 if created else 200
            return result

    except ImpactTargetNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except ProposalConflictError as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except SQLAlchemyError as exc:
        logger.error(
            "Proposal create database error: %s",
            type(exc).__name__,
        )
        raise HTTPException(503, "Unable to save proposal.") from None


@router.post(
    "/incidents/{incident_id}/proposals/purchase",
    response_model=ProposalResponse,
    status_code=201,
    responses={
        200: {"description": "Previously saved proposal returned"},
        409: {"description": "Conflicting request or unusable assessment"},
    },
)
def create_purchase_proposal(
    incident_id: UUID,
    request: PurchaseProposalRequest,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ],
) -> ProposalResponse:
    key = idempotency_key.strip()

    if not key:
        raise HTTPException(422, "Idempotency-Key must not be blank.")

    fingerprint = _request_hash(request)

    try:
        with Session(engine) as session:
            incident = session.get(Incident, incident_id)

            if incident is None:
                raise HTTPException(404, "Incident not found.")

            replay = _find_replay(
                session, incident_id, key, fingerprint
            )

            if replay is not None:
                response.status_code = 200
                return ProposalResponse.model_validate(replay)

            if incident.status not in ("OPEN", "INVESTIGATING"):
                raise HTTPException(409, "Incident is not open.")

            product = session.get(Product, incident.product_id)
            plant = session.get(Location, incident.plant_id)

            if product is None or plant is None:
                raise HTTPException(409, "Incident scope is invalid.")

            product_id = product.id
            plant_id = plant.id
            sku = product.sku
            plant_code = plant.code

        evaluation = recommend_supplier_purchases(
            sku=sku, plant_code=plant_code,
            freight_cost=request.freight_cost, currency=request.currency,
            include_evidence=True,
        )


        # READ COMMITTED transaction: lock before assigning a version
        # and checking whether another request already saved this key.
        with Session(engine) as session:
            with session.begin():
                incident = session.scalar(
                    select(Incident)
                    .where(Incident.id == incident_id)
                    .with_for_update()
                )

                if incident is None:
                    raise HTTPException(404, "Incident not found.")

                replay = _find_replay(
                    session, incident_id, key, fingerprint
                )

                if replay is not None:
                    result = ProposalResponse.model_validate(replay)
                    created = False
                else:
                    if (
                        incident.product_id != product_id
                        or incident.plant_id != plant_id
                    ):
                        raise HTTPException(
                            409,
                            "Incident scope changed. Evaluate again.",
                        )

                    option = next((item for item in evaluation["options"]
                                   if item["offer_id"] == str(request.offer_id)), None)
                    if option is None or option["status"] not in ("FULL_COVERAGE", "PARTIAL_COVERAGE"):
                        raise HTTPException(409, detail={
                            "message": "Selected offer has no usable purchase proposal.",
                            "assessment_status": evaluation["status"],
                            "issues": evaluation["issues"],
                            "reasons": option["reasons"] if option else ["OFFER_NOT_AVAILABLE"],
                        })

                    evidence = evaluation.pop("_evidence", None)
                    if not evidence or evidence["scope"]["product_id"] != str(product_id) or evidence["scope"]["plant_id"] != str(plant_id):
                        raise HTTPException(409, "Assessment evidence does not match incident scope.")
                    evidence["assumptions"] = list(evaluation["assumptions"])
                    evidence["parameters"] = request.model_dump(mode="json")
                    evidence["policy"] = {
                        "max_proposal_age_seconds": 300,
                        "max_supply_age_seconds": 1800,
                        "allocation": "EARLIEST_DEADLINE_FIRST",
                        "execution_status": "NOT_EXECUTED",
                    }
                    assessed_at = datetime.fromisoformat(
                        evaluation["assessed_at"]
                    )

                    selected_offer = next(row for row in evidence["supplier_offers"]
                                          if row["id"] == str(request.offer_id))
                    evidence["scope"]["selected_offer_id"] = str(request.offer_id)
                    proposal = save_proposal(
                        session=session,
                        incident_id=incident_id,
                        action_type="SUPPLIER_PURCHASE",
                        assessed_at=assessed_at,
                        expires_at=proposal_expiry(
                            assessed_at=assessed_at, evidence=evidence,
                            plan=option["plan"],
                            lead_time=timedelta(hours=selected_offer["lead_time_hours"]),
                            offer_id=request.offer_id,
                        ),
                        plan_snapshot={
                            "schema_version": 2,
                            "evaluation": evaluation,
                            "selected_offer_id": str(request.offer_id),
                            "selected_option": option,
                            "parameters": request.model_dump(mode="json"),
                        },
                        evidence_snapshot=evidence,
                    )

                    # Both fields are persisted atomically with the proposal.
                    proposal.idempotency_key = key
                    proposal.request_hash = fingerprint
                    session.flush()

                    result = ProposalResponse.model_validate(proposal)
                    created = True

            response.status_code = 201 if created else 200
            return result

    except ImpactTargetNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except ProposalConflictError as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except SQLAlchemyError as exc:
        logger.error(
            "Proposal create database error: %s",
            type(exc).__name__,
        )
        raise HTTPException(503, "Unable to save proposal.") from None


@router.get(
    "/proposals/{proposal_id}",
    response_model=ProposalResponse,
)
def get_proposal(proposal_id: UUID) -> ProposalResponse:
    try:
        with Session(engine) as session:
            proposal = session.get(RecoveryProposal, proposal_id)

            if proposal is None:
                raise HTTPException(404, "Proposal not found.")

            return ProposalResponse.model_validate(proposal)

    except SQLAlchemyError as exc:
        logger.error(
            "Proposal read database error: %s",
            type(exc).__name__,
        )
        raise HTTPException(503, "Unable to read proposal.") from None