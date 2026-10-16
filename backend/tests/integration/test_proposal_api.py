from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import (
    Incident,
    InventoryBalance,
    Location,
    Product,
    ProductionDemand,
    RecoveryProposal,
)


@pytest.fixture
def api_scenario(monkeypatch):
    from app.core.database import database_url
    from app.api import incidents as incident_api
    from app.api import proposals as proposal_api
    from app.services import transfer_recommendation

    engine = create_engine(
        database_url.set(database="opsflow_test"),
        isolation_level="READ COMMITTED",
        connect_args={"connect_timeout": 5},
    )

    monkeypatch.setattr(incident_api, "engine", engine)
    monkeypatch.setattr(proposal_api, "engine", engine)
    monkeypatch.setattr(transfer_recommendation, "engine", engine)

    suffix = uuid4().hex[:12]
    created = {}

    try:
        with Session(engine) as session:
            with session.begin():
                now = datetime.now(timezone.utc)

                product = Product(
                    sku=f"API-SKU-{suffix}",
                    name="API Test Product",
                    unit_of_measure="UNIT",
                    is_active=True,
                )
                plant = Location(
                    code=f"API-PLANT-{suffix}",
                    name="API Test Plant",
                    type="PLANT",
                )
                warehouse = Location(
                    code=f"API-WH-{suffix}",
                    name="API Test Warehouse",
                    type="WAREHOUSE",
                )

                session.add_all([product, plant, warehouse])
                session.flush()

                for location, quantity in (
                    (plant, "20"),
                    (warehouse, "100"),
                ):
                    session.add(
                        InventoryBalance(
                            product_id=product.id,
                            location_id=location.id,
                            on_hand_qty=Decimal(quantity),
                            reserved_qty=Decimal("0"),
                            observed_at=now,
                            source_system="TEST_WMS",
                            source_version="1",
                        )
                    )

                session.add(
                    ProductionDemand(
                        source_system="TEST_ERP",
                        source_ref=f"API-DEMAND-{suffix}",
                        product_id=product.id,
                        plant_id=plant.id,
                        required_qty=Decimal("100"),
                        fulfilled_qty=Decimal("0"),
                        required_at=now + timedelta(hours=8),
                        status="OPEN",
                    )
                )

                created = {
                    "engine": engine,
                    "product_id": product.id,
                    "plant_id": plant.id,
                    "warehouse_id": warehouse.id,
                    "warehouse_code": warehouse.code,
                    "incident_body": {
                        "source_system": "TEST_API",
                        "source_ref": f"API-INCIDENT-{suffix}",
                        "title": "API integration test incident",
                        "description": "Test fixture",
                        "product_id": str(product.id),
                        "plant_id": str(plant.id),
                        "detected_at": now.isoformat(),
                    },
                }

        yield created

    finally:
        try:
            if created:
                with Session(engine) as session:
                    with session.begin():
                        incident_ids = select(Incident.id).where(
                            Incident.product_id == created["product_id"]
                        )

                        session.execute(
                            delete(RecoveryProposal).where(
                                RecoveryProposal.incident_id.in_(incident_ids)
                            )
                        )
                        session.execute(
                            delete(Incident).where(
                                Incident.product_id == created["product_id"]
                            )
                        )
                        session.execute(
                            delete(ProductionDemand).where(
                                ProductionDemand.product_id
                                == created["product_id"]
                            )
                        )
                        session.execute(
                            delete(InventoryBalance).where(
                                InventoryBalance.product_id
                                == created["product_id"]
                            )
                        )
                        session.execute(
                            delete(Product).where(
                                Product.id == created["product_id"]
                            )
                        )
                        session.execute(
                            delete(Location).where(
                                Location.id.in_([
                                    created["plant_id"],
                                    created["warehouse_id"],
                                ])
                            )
                        )
        finally:
            engine.dispose()


def create_incident(client, scenario):
    response = client.post(
        "/api/v1/incidents",
        json=scenario["incident_body"],
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def transfer_body(scenario):
    return {
        "warehouse_code": scenario["warehouse_code"],
        "lead_time_hours": 1,
        "fixed_transport_cost": "18000.00",
        "currency": "LKR",
    }


def proposal_url(incident_id):
    return f"/api/v1/incidents/{incident_id}/proposals/transfer"


def proposal_count(scenario):
    with Session(scenario["engine"]) as session:
        return session.scalar(
            select(func.count())
            .select_from(RecoveryProposal)
            .join(
                Incident,
                RecoveryProposal.incident_id == Incident.id,
            )
            .where(Incident.product_id == scenario["product_id"])
        )


def test_incident_create_replay_and_get(api_scenario):
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/incidents",
            json=api_scenario["incident_body"],
        )
        second = client.post(
            "/api/v1/incidents",
            json=api_scenario["incident_body"],
        )

        assert first.status_code == 201
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]

        response = client.get(
            f"/api/v1/incidents/{first.json()['id']}"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "OPEN"


def test_proposal_retry_returns_same_saved_record(api_scenario):
    with TestClient(app) as client:
        incident_id = create_incident(client, api_scenario)
        url = proposal_url(incident_id)
        headers = {"Idempotency-Key": "retry-test"}

        first = client.post(
            url,
            headers=headers,
            json=transfer_body(api_scenario),
        )
        assert first.status_code == 201, first.text

        second = client.post(
            url,
            headers=headers,
            json=transfer_body(api_scenario),
        )

        assert second.status_code == 200, second.text
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["version"] == first.json()["version"]
        assert first.json()["status"] == "PROPOSED"

        saved = client.get(
            f"/api/v1/proposals/{first.json()['id']}"
        )
        assert saved.status_code == 200
        assert saved.json()["plan_snapshot"] == first.json()["plan_snapshot"]

    assert proposal_count(api_scenario) == 1


def test_same_key_with_changed_inputs_returns_409(api_scenario):
    with TestClient(app) as client:
        incident_id = create_incident(client, api_scenario)
        url = proposal_url(incident_id)
        headers = {"Idempotency-Key": "conflict-test"}

        first = client.post(
            url,
            headers=headers,
            json=transfer_body(api_scenario),
        )
        assert first.status_code == 201, first.text

        changed = {
            **transfer_body(api_scenario),
            "fixed_transport_cost": "19000.00",
        }
        response = client.post(url, headers=headers, json=changed)

        assert response.status_code == 409

    assert proposal_count(api_scenario) == 1


def test_equivalent_cost_formats_replay_same_proposal(api_scenario):
    with TestClient(app) as client:
        incident_id = create_incident(client, api_scenario)
        url = proposal_url(incident_id)
        headers = {"Idempotency-Key": "decimal-test"}

        first = client.post(
            url,
            headers=headers,
            json=transfer_body(api_scenario),
        )
        assert first.status_code == 201, first.text

        body = {
            **transfer_body(api_scenario),
            "fixed_transport_cost": "18000",
        }
        second = client.post(url, headers=headers, json=body)

        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]


def test_missing_key_is_rejected_without_saving(api_scenario):
    with TestClient(app) as client:
        incident_id = create_incident(client, api_scenario)

        response = client.post(
            proposal_url(incident_id),
            json=transfer_body(api_scenario),
        )

        assert response.status_code == 422

    assert proposal_count(api_scenario) == 0


def test_stale_evidence_does_not_save_proposal(api_scenario):
    with Session(api_scenario["engine"]) as session:
        with session.begin():
            balances = session.scalars(
                select(InventoryBalance).where(
                    InventoryBalance.product_id
                    == api_scenario["product_id"]
                )
            ).all()

            for balance in balances:
                balance.observed_at = (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                )

    with TestClient(app) as client:
        incident_id = create_incident(client, api_scenario)

        response = client.post(
            proposal_url(incident_id),
            headers={"Idempotency-Key": "stale-test"},
            json=transfer_body(api_scenario),
        )

        assert response.status_code == 409
        assert response.json()["detail"]["assessment_status"] == "INCOMPLETE"

    assert proposal_count(api_scenario) == 0


def test_concurrent_retries_create_one_proposal(
    api_scenario,
    monkeypatch,
):
    from app.api import proposals as proposal_api

    original_evaluate = proposal_api.recommend_warehouse_transfer
    barrier = Barrier(2)

    def synchronized_evaluate(**kwargs):
        # Force both requests past their initial replay check.
        barrier.wait(timeout=15)
        return original_evaluate(**kwargs)

    monkeypatch.setattr(
        proposal_api,
        "recommend_warehouse_transfer",
        synchronized_evaluate,
    )

    with TestClient(app) as client:
        incident_id = create_incident(client, api_scenario)

    def send_request():
        with TestClient(app) as client:
            return client.post(
                proposal_url(incident_id),
                headers={"Idempotency-Key": "concurrent-test"},
                json=transfer_body(api_scenario),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(send_request) for _ in range(2)]
        responses = [future.result(timeout=30) for future in futures]

    assert sorted(r.status_code for r in responses) == [200, 201], [
        r.text for r in responses
    ]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert proposal_count(api_scenario) == 1