from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Incident, Location, Product


class IncidentConflictError(Exception):
    """An existing reference belongs to different incident details."""


def _required_text(value: str, name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")

    value = value.strip()

    if not value or len(value) > max_length:
        raise ValueError(
            f"{name} must contain 1 to {max_length} characters."
        )

    return value


def create_or_get_incident(
    *,
    session: Session,
    source_system: str,
    source_ref: str,
    title: str,
    product_id: UUID,
    plant_id: UUID,
    detected_at: datetime,
    description: str | None = None,
) -> tuple[Incident, bool]:
    """Return (incident, created) within the caller's transaction.

    Replays must carry the same original incident details.
    Existing incident status is preserved.
    """
    source_system = _required_text(source_system, "source_system", 64)
    source_ref = _required_text(source_ref, "source_ref", 128)
    title = _required_text(title, "title", 255)

    if description is not None:
        if not isinstance(description, str):
            raise TypeError("description must be a string or None.")
        description = description.strip() or None

    if not isinstance(detected_at, datetime):
        raise TypeError("detected_at must be a datetime.")

    if detected_at.tzinfo is None or detected_at.utcoffset() is None:
        raise ValueError("detected_at must include a timezone.")

    detected_at = detected_at.astimezone(timezone.utc)

    if session.get(Product, product_id) is None:
        raise ValueError("Product not found.")

    plant = session.get(Location, plant_id)

    if plant is None or plant.type != "PLANT":
        raise ValueError("plant_id must reference a valid plant.")

    inserted_id = session.scalar(
        insert(Incident)
        .values(
            id=uuid4(),
            source_system=source_system,
            source_ref=source_ref,
            title=title,
            description=description,
            product_id=product_id,
            plant_id=plant_id,
            detected_at=detected_at,
            status="OPEN",
        )
        .on_conflict_do_nothing(
            index_elements=["source_system", "source_ref"]
        )
        .returning(Incident.id)
    )

    incident = session.scalar(
        select(Incident).where(
            Incident.source_system == source_system,
            Incident.source_ref == source_ref,
        )
    )

    if incident is None:
        raise RuntimeError("Incident could not be read after insert.")

    if inserted_id is not None:
        return incident, True

    existing_details = (
        incident.product_id,
        incident.plant_id,
        incident.title,
        incident.description,
        incident.detected_at,
    )
    requested_details = (
        product_id,
        plant_id,
        title,
        description,
        detected_at,
    )

    if existing_details != requested_details:
        raise IncidentConflictError(
            "This source reference already exists with different details."
        )

    return incident, False