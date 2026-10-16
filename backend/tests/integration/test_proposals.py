from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import database_url
from app.models import Incident, Location, Product, RecoveryProposal
from app.services.incidents import (
    IncidentConflictError,
    create_or_get_incident,
)
from app.services.proposals import (
    ProposalConflictError,
    save_proposal,
)


@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine(
        database_url.set(database="opsflow_test"),
        isolation_level="READ COMMITTED",
        connect_args={"connect_timeout": 5},
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(test_engine):
    with test_engine.connect() as connection:
        transaction = connection.begin()

        try:
            with Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
            ) as session:
                yield session
        finally:
            transaction.rollback()


@pytest.fixture
def incident_request(db_session):
    suffix = uuid4().hex[:12]

    product = Product(
        sku=f"PROP-SKU-{suffix}",
        name="Proposal Test Product",
        unit_of_measure="UNIT",
        is_active=True,
    )
    plant = Location(
        code=f"PROP-PLANT-{suffix}",
        name="Proposal Test Plant",
        type="PLANT",
    )
    db_session.add_all([product, plant])
    db_session.flush()

    return {
        "source_system": "TEST_TRIAGE",
        "source_ref": f"INC-{suffix}",
        "title": "Test supply disruption",
        "description": "Integration test incident.",
        "product_id": product.id,
        "plant_id": plant.id,
        "detected_at": datetime.now(timezone.utc) - timedelta(minutes=5),
    }


@pytest.fixture
def incident(db_session, incident_request):
    record, _ = create_or_get_incident(
        session=db_session,
        **incident_request,
    )
    return record


def proposal_arguments(incident):
    now = datetime.now(timezone.utc)

    return {
        "incident_id": incident.id,
        "action_type": "WAREHOUSE_TRANSFER",
        "assessed_at": now - timedelta(seconds=1),
        "expires_at": now + timedelta(minutes=10),
        # Minimal persistence fixtures, not executable recovery plans.
        "plan_snapshot": {
            "transfer_qty": "80.000",
            "transport_cost": "18000.00",
            "currency": "LKR",
        },
        "evidence_snapshot": {
            "product_id": str(incident.product_id),
            "plant_id": str(incident.plant_id),
            "available_qty": "100.000",
        },
    }


def test_incident_replay_returns_same_record(db_session, incident_request):
    first, first_created = create_or_get_incident(
        session=db_session,
        **incident_request,
    )
    second, second_created = create_or_get_incident(
        session=db_session,
        **incident_request,
    )

    assert first_created is True
    assert second_created is False
    assert first.id == second.id


def test_incident_replay_preserves_status(
    db_session, incident, incident_request
):
    incident.status = "INVESTIGATING"
    db_session.flush()

    replay, created = create_or_get_incident(
        session=db_session,
        **incident_request,
    )

    assert created is False
    assert replay.status == "INVESTIGATING"


def test_changed_incident_replay_is_rejected(
    db_session, incident, incident_request
):
    changed = {
        **incident_request,
        "title": "Different incident details",
    }

    with pytest.raises(IncidentConflictError):
        create_or_get_incident(session=db_session, **changed)


def test_proposals_get_sequential_versions(db_session, incident):
    arguments = proposal_arguments(incident)

    first = save_proposal(session=db_session, **arguments)
    second = save_proposal(session=db_session, **arguments)

    assert first.id != second.id
    assert first.version == 1
    assert second.version == 2
    assert first.status == "PROPOSED"
    assert second.status == "PROPOSED"


def test_snapshots_are_persisted_and_detached_from_input(
    db_session, incident
):
    arguments = proposal_arguments(incident)
    record = save_proposal(session=db_session, **arguments)
    proposal_id = record.id

    arguments["plan_snapshot"]["transfer_qty"] = "999.000"
    arguments["evidence_snapshot"]["available_qty"] = "999.000"

    db_session.flush()
    db_session.expire_all()

    stored = db_session.get(RecoveryProposal, proposal_id)

    assert stored.plan_snapshot["transfer_qty"] == "80.000"
    assert stored.evidence_snapshot["available_qty"] == "100.000"


@pytest.mark.parametrize("status", ["RESOLVED", "CANCELLED"])
def test_closed_incident_rejects_proposals(db_session, incident, status):
    incident.status = status
    db_session.flush()

    with pytest.raises(ProposalConflictError):
        save_proposal(
            session=db_session,
            **proposal_arguments(incident),
        )


def test_expired_proposal_is_rejected(db_session, incident):
    arguments = proposal_arguments(incident)
    now = datetime.now(timezone.utc)
    arguments["assessed_at"] = now - timedelta(minutes=10)
    arguments["expires_at"] = now - timedelta(minutes=1)

    with pytest.raises(ValueError, match="expired"):
        save_proposal(session=db_session, **arguments)


def test_future_assessment_is_rejected(db_session, incident):
    arguments = proposal_arguments(incident)
    now = datetime.now(timezone.utc)
    arguments["assessed_at"] = now + timedelta(minutes=1)
    arguments["expires_at"] = now + timedelta(minutes=10)

    with pytest.raises(ValueError, match="future"):
        save_proposal(session=db_session, **arguments)


@pytest.mark.parametrize(
    "snapshot",
    [
        {},
        {"quantity": Decimal("80")},
        {"quantity": float("nan")},
    ],
)
def test_invalid_json_snapshot_is_rejected(
    db_session, incident, snapshot
):
    arguments = proposal_arguments(incident)
    arguments["plan_snapshot"] = snapshot

    with pytest.raises(ValueError):
        save_proposal(session=db_session, **arguments)


def test_unknown_incident_is_rejected(db_session, incident):
    arguments = proposal_arguments(incident)
    arguments["incident_id"] = uuid4()

    with pytest.raises(ValueError, match="Incident not found"):
        save_proposal(session=db_session, **arguments)


def test_caller_can_roll_back_proposal(db_session, incident):
    with db_session.begin_nested() as savepoint:
        record = save_proposal(
            session=db_session,
            **proposal_arguments(incident),
        )
        proposal_id = record.id
        savepoint.rollback()

    stored_id = db_session.scalar(
        select(RecoveryProposal.id).where(
            RecoveryProposal.id == proposal_id
        )
    )

    assert stored_id is None