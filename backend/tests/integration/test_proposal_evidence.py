from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.api import proposals as api
from app.core.database import database_url
from app.models import (
    Incident, InventoryBalance, Location, Product, ProductionDemand,
    RecoveryProposal, Supplier, SupplierOffer,
)
from app.services import purchase_recommendation as purchase_service
from app.services import transfer_recommendation as transfer_service


@pytest.fixture
def scenario(monkeypatch):
    engine = create_engine(database_url.set(database="opsflow_test"),
                           connect_args={"connect_timeout": 5})
    monkeypatch.setattr(api, "engine", engine)
    monkeypatch.setattr(purchase_service, "engine", engine)
    monkeypatch.setattr(transfer_service, "engine", engine)
    ids = {key: uuid4() for key in ("product", "plant", "warehouse", "supplier", "offer", "incident")}
    suffix = uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    app = FastAPI()
    app.include_router(api.router)
    try:
        with Session(engine) as session, session.begin():
            session.add_all([
                Product(id=ids["product"], sku=f"EVID-{suffix}", name="Test motor", unit_of_measure="UNIT"),
                Location(id=ids["plant"], code=f"PLANT-{suffix}", name="Test plant", type="PLANT"),
                Location(id=ids["warehouse"], code=f"WH-{suffix}", name="Test warehouse", type="WAREHOUSE"),
                Supplier(id=ids["supplier"], code=f"SUP-{suffix}", name="Test supplier", approval_status="APPROVED"),
            ])
            session.flush()
            session.add_all([
                InventoryBalance(product_id=ids["product"], location_id=ids[loc],
                    on_hand_qty=Decimal(qty), reserved_qty=Decimal("0"), observed_at=now,
                    source_system="TEST", source_version="1")
                for loc, qty in (("plant", "20"), ("warehouse", "100"))
            ])
            session.add(ProductionDemand(source_system="TEST", source_ref=suffix,
                plant_id=ids["plant"], product_id=ids["product"], required_qty=Decimal("100"),
                fulfilled_qty=Decimal("0"), required_at=now + timedelta(hours=8), status="OPEN"))
            session.add(SupplierOffer(id=ids["offer"], supplier_id=ids["supplier"], product_id=ids["product"],
                unit_price=Decimal("2100"), currency="LKR", available_qty=Decimal("100"),
                lead_time_hours=1, observed_at=now, valid_until=now + timedelta(hours=24)))
            session.add(Incident(id=ids["incident"], source_system="TEST", source_ref=suffix,
                title="Evidence test", description="Isolated fixture", product_id=ids["product"],
                plant_id=ids["plant"], status="OPEN", detected_at=now))
        with TestClient(app) as client:
            yield {"engine": engine, "client": client, "ids": ids, "suffix": suffix}
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(RecoveryProposal).where(RecoveryProposal.incident_id == ids["incident"]))
            session.execute(delete(Incident).where(Incident.id == ids["incident"]))
            session.execute(delete(SupplierOffer).where(SupplierOffer.product_id == ids["product"]))
            session.execute(delete(ProductionDemand).where(ProductionDemand.product_id == ids["product"]))
            session.execute(delete(InventoryBalance).where(InventoryBalance.product_id == ids["product"]))
            session.execute(delete(Product).where(Product.id == ids["product"]))
            session.execute(delete(Location).where(Location.id.in_([ids["plant"], ids["warehouse"]])))
            session.execute(delete(Supplier).where(Supplier.id == ids["supplier"]))
        engine.dispose()


def purchase(scenario, key="purchase-test", **changes):
    body = {"offer_id": str(scenario["ids"]["offer"]), "freight_cost": "12000", "currency": "LKR"}
    body.update(changes)
    return scenario["client"].post(
        f'/api/v1/incidents/{scenario["ids"]["incident"]}/proposals/purchase',
        headers={"Idempotency-Key": key}, json=body,
    )


def test_purchase_persists_inputs_and_replays_after_live_data_changes(scenario):
    first = purchase(scenario)
    assert first.status_code == 201, first.text
    saved = first.json()
    evidence = saved["evidence_snapshot"]
    assert saved["action_type"] == "SUPPLIER_PURCHASE"
    assert evidence["scope"]["selected_offer_id"] == str(scenario["ids"]["offer"])
    assert Decimal(evidence["supplier_offers"][0]["unit_price"]) == Decimal("2100")
    assert len(evidence["production_demands"]) == 1
    assert len(evidence["inventory_balances"]) == 1
    with Session(scenario["engine"]) as session, session.begin():
        session.get(SupplierOffer, scenario["ids"]["offer"]).unit_price = Decimal("2500")
    replay = purchase(scenario, freight_cost="12000.00")
    assert replay.status_code == 200, replay.text
    assert replay.json() == saved


def test_changed_purchase_inputs_conflict(scenario):
    assert purchase(scenario).status_code == 201
    assert purchase(scenario, freight_cost="15000").status_code == 409


@pytest.mark.parametrize("case", ["stale", "suspended", "unknown_offer"])
def test_unusable_purchase_does_not_persist(scenario, case):
    changes = {}
    with Session(scenario["engine"]) as session, session.begin():
        if case == "stale":
            session.get(SupplierOffer, scenario["ids"]["offer"]).observed_at = datetime.now(timezone.utc) - timedelta(hours=1)
        elif case == "suspended":
            session.get(Supplier, scenario["ids"]["supplier"]).approval_status = "SUSPENDED"
        else:
            changes["offer_id"] = str(uuid4())
    response = purchase(scenario, **changes)
    assert response.status_code == 409, response.text
    with Session(scenario["engine"]) as session:
        assert session.scalar(select(RecoveryProposal).where(
            RecoveryProposal.incident_id == scenario["ids"]["incident"])) is None


def test_transfer_captures_both_balances_and_key_is_shared_across_actions(scenario):
    response = scenario["client"].post(
        f'/api/v1/incidents/{scenario["ids"]["incident"]}/proposals/transfer',
        headers={"Idempotency-Key": "shared"},
        json={"warehouse_code": f'WH-{scenario["suffix"]}', "lead_time_hours": 1,
              "fixed_transport_cost": "18000", "currency": "LKR"},
    )
    assert response.status_code == 201, response.text
    evidence = response.json()["evidence_snapshot"]
    assert {row["location_id"] for row in evidence["inventory_balances"]} == {
        str(scenario["ids"]["plant"]), str(scenario["ids"]["warehouse"])}
    assert purchase(scenario, key="shared").status_code == 409


def test_evaluation_and_evidence_share_repeatable_read_snapshot(scenario, monkeypatch):
    original = purchase_service._recommend_purchases

    def change_live_data_after_calculation(**kwargs):
        result = original(**kwargs)
        # Commit a new relevant demand between calculation and evidence capture.
        with Session(scenario["engine"]) as writer, writer.begin():
            writer.add(ProductionDemand(
                source_system="TEST", source_ref=uuid4().hex,
                product_id=scenario["ids"]["product"], plant_id=scenario["ids"]["plant"],
                required_qty=Decimal("999"), fulfilled_qty=Decimal("0"),
                required_at=datetime.now(timezone.utc) + timedelta(hours=10), status="OPEN",
            ))
        return result

    monkeypatch.setattr(purchase_service, "_recommend_purchases", change_live_data_after_calculation)
    response = purchase(scenario)
    assert response.status_code == 201, response.text
    assert len(response.json()["evidence_snapshot"]["production_demands"]) == 1
    with Session(scenario["engine"]) as session:
        demands = session.scalars(select(ProductionDemand).where(
            ProductionDemand.product_id == scenario["ids"]["product"])).all()
        assert len(demands) == 2
