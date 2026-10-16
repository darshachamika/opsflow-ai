import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Incident, RecoveryProposal


class ProposalConflictError(Exception):
    """The incident cannot accept a new proposal."""


def _aware_utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime.")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone.")

    return value.astimezone(timezone.utc)


def _copy_json_object(value: dict[str, Any], name: str) -> dict:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{name} must be a nonempty JSON object.")

    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must use string keys.")

    try:
        # Reject NaN/Infinity and unsupported values.
        # Decimal, UUID and datetime values must be serialized beforehand.
        encoded = json.dumps(value, allow_nan=False)
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must contain valid JSON values."
        ) from exc


def save_proposal(
    *,
    session: Session,
    incident_id: UUID,
    action_type: str,
    assessed_at: datetime,
    expires_at: datetime,
    plan_snapshot: dict[str, Any],
    evidence_snapshot: dict[str, Any],
) -> RecoveryProposal:
    """Save a new proposal within the caller's transaction.

    Internal persistence function: caller must validate recommendation
    scope, evidence and expiry policy before calling.

    Each call creates a new version. This is not an idempotent API.
    """
    if action_type not in (
        "WAREHOUSE_TRANSFER",
        "SUPPLIER_PURCHASE",
    ):
        raise ValueError("Unsupported action_type.")

    assessed_at = _aware_utc(assessed_at, "assessed_at")
    expires_at = _aware_utc(expires_at, "expires_at")

    if expires_at <= assessed_at:
        raise ValueError("expires_at must be after assessed_at.")

    plan = _copy_json_object(plan_snapshot, "plan_snapshot")
    evidence = _copy_json_object(
        evidence_snapshot,
        "evidence_snapshot",
    )

    # Serialize version assignment for this incident.
    # populate_existing refreshes an incident already in the identity map.
    incident = session.scalar(
        select(Incident)
        .where(Incident.id == incident_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    if incident is None:
        raise ValueError("Incident not found.")

    if incident.status not in ("OPEN", "INVESTIGATING"):
        raise ProposalConflictError(
            "Only open or investigating incidents accept proposals."
        )

    # Check after acquiring the lock, because lock acquisition may wait.
    now = datetime.now(timezone.utc)

    if assessed_at > now:
        raise ValueError("assessed_at cannot be in the future.")

    if expires_at <= now:
        raise ValueError("Cannot save an already expired proposal.")

    latest_version = session.scalar(
        select(func.max(RecoveryProposal.version)).where(
            RecoveryProposal.incident_id == incident_id
        )
    )

    proposal = RecoveryProposal(
        incident_id=incident_id,
        version=(latest_version or 0) + 1,
        action_type=action_type,
        status="PROPOSED",
        assessed_at=assessed_at,
        expires_at=expires_at,
        plan_snapshot=plan,
        evidence_snapshot=evidence,
    )

    session.add(proposal)
    session.flush()

    return proposal