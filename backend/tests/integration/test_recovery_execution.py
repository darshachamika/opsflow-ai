from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.api import proposals as api
from app.api import approvals as approval_api
from app.api import execution as execution_api
from app.services import execution as execution_service
from app.models.execution import RecoveryExecution, RecoveryReservation, RecoveryDemandClaim, MockERPOrder
from app.connectors.mock_erp import MockERPRejected
from app.services import approvals as approval_service
from app.core.approval_auth import Actor, current_actor
from app.models.approval import ApprovalDecision, ApprovalResumeJob
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
    extra_locations = []
    suffix = uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(approval_api.router)
    app.include_router(execution_api.router)
    monkeypatch.setattr(execution_api, "engine", engine)
    # Stable within this scenario; isolated from other tests and previous runs.
    manager_subject = f"manager.test.{suffix}"
    app.dependency_overrides[current_actor] = lambda: Actor(manager_subject, "PROCUREMENT_MANAGER")
    monkeypatch.setattr(approval_api, "engine", engine)
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
            yield {"engine": engine, "client": client, "ids": ids, "suffix": suffix, "app": app, "extra_locations": extra_locations}
    finally:
        with Session(engine) as session, session.begin():
            incident_ids = select(Incident.id).where(Incident.product_id == ids["product"])
            proposal_ids = select(RecoveryProposal.id).where(RecoveryProposal.incident_id.in_(incident_ids))
            execution_ids = select(RecoveryExecution.id).where(RecoveryExecution.proposal_id.in_(proposal_ids))
            session.execute(delete(MockERPOrder).where(MockERPOrder.execution_id.in_(execution_ids)))
            session.execute(delete(RecoveryReservation).where(RecoveryReservation.execution_id.in_(execution_ids)))
            session.execute(delete(RecoveryDemandClaim).where(RecoveryDemandClaim.execution_id.in_(execution_ids)))
            session.execute(delete(RecoveryExecution).where(RecoveryExecution.proposal_id.in_(proposal_ids)))
            session.execute(delete(ApprovalResumeJob).where(ApprovalResumeJob.proposal_id.in_(proposal_ids)))
            session.execute(delete(ApprovalDecision).where(ApprovalDecision.proposal_id.in_(proposal_ids)))
            session.execute(delete(RecoveryProposal).where(RecoveryProposal.incident_id.in_(incident_ids)))
            session.execute(delete(Incident).where(Incident.product_id == ids["product"]))
            session.execute(delete(SupplierOffer).where(SupplierOffer.product_id == ids["product"]))
            session.execute(delete(ProductionDemand).where(ProductionDemand.product_id == ids["product"]))
            session.execute(delete(InventoryBalance).where(InventoryBalance.product_id == ids["product"]))
            session.execute(delete(Product).where(Product.id == ids["product"]))
            session.execute(delete(Location).where(Location.id.in_([ids["plant"], ids["warehouse"], *extra_locations])))
            session.execute(delete(Supplier).where(Supplier.id == ids["supplier"]))
        engine.dispose()



def create_proposal(scenario, key="proposal-1"):
    result = scenario["client"].post(
        f'/api/v1/incidents/{scenario["ids"]["incident"]}/proposals/transfer',
        headers={"Idempotency-Key": key},
        json={"warehouse_code": f'WH-{scenario["suffix"]}', "lead_time_hours": 1,
              "fixed_transport_cost": "18000", "currency": "LKR"})
    assert result.status_code == 201, result.text
    return result.json()["id"]


def decide(scenario, proposal_id, decision="APPROVED", key="decision-1", reason="Reviewed supply evidence"):
    return scenario["client"].post(f"/api/v1/proposals/{proposal_id}/decision",
        headers={"Idempotency-Key": key}, json={"decision": decision, "reason": reason})



def approved(scenario, action="transfer"):
    if action == "transfer":
        proposal_id = create_proposal(scenario)
    else:
        result = scenario["client"].post(
            f'/api/v1/incidents/{scenario["ids"]["incident"]}/proposals/purchase',
            headers={"Idempotency-Key": "purchase"},
            json={"offer_id": str(scenario["ids"]["offer"]), "freight_cost": "12000", "currency": "LKR"})
        assert result.status_code == 201, result.text
        proposal_id = result.json()["id"]
    result = decide(scenario, proposal_id)
    assert result.status_code == 201, result.text
    return proposal_id


def execute(scenario, proposal_id):
    return scenario["client"].post(f"/api/v1/proposals/{proposal_id}/execute-mock")


@pytest.mark.parametrize("action", ["transfer", "purchase"])
def test_accepted_order_and_reservation_are_idempotent(scenario, action):
    from uuid import UUID
    proposal_id = approved(scenario, action)
    first = execute(scenario, proposal_id)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "SUCCEEDED"
    assert first.json()["result"]["physical_receipt_recorded"] is False
    replay = execute(scenario, proposal_id)
    assert replay.status_code == 200 and replay.json() == first.json()
    with Session(scenario["engine"]) as session:
        execution_id = UUID(first.json()["id"])
        assert len(session.scalars(select(MockERPOrder).where(MockERPOrder.execution_id == execution_id)).all()) == 1
        hold = session.scalar(select(RecoveryReservation).where(RecoveryReservation.execution_id == execution_id))
        assert hold.quantity == Decimal("80") and hold.status == "ACTIVE"
        assert session.scalar(select(ApprovalResumeJob).where(ApprovalResumeJob.proposal_id == UUID(proposal_id))).status == "COMPLETED"
        assert session.get(RecoveryProposal, UUID(proposal_id)).status == "APPROVED"
        if action == "transfer":
            balance = session.get(InventoryBalance, hold.inventory_balance_id)
            assert balance.reserved_qty == Decimal("80") and balance.on_hand_qty == Decimal("100")
        else:
            assert session.get(SupplierOffer, hold.supplier_offer_id).available_qty == Decimal("100")


def test_unapproved_proposal_cannot_execute(scenario):
    assert execute(scenario, create_proposal(scenario)).status_code == 409


@pytest.mark.parametrize("case", ["expired", "stock", "closed"])
def test_failed_revalidation_creates_no_order_or_hold(scenario, case):
    from uuid import UUID
    proposal_id = approved(scenario)
    with Session(scenario["engine"]) as session, session.begin():
        if case == "expired":
            # Preserve the signed payload: advance the service clock instead of mutating expiry.
            pass
        elif case == "stock":
            balance = session.scalar(select(InventoryBalance).where(InventoryBalance.location_id == scenario["ids"]["warehouse"]))
            balance.on_hand_qty = Decimal("0")
        else:
            session.get(Incident, scenario["ids"]["incident"]).status = "RESOLVED"
    if case == "expired":
        from unittest.mock import patch
        from datetime import datetime as real_datetime
        class FutureClock(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return real_datetime.now(tz) + timedelta(minutes=6)
        with patch.object(execution_service, "datetime", FutureClock):
            result = execute(scenario, proposal_id)
    else:
        result = execute(scenario, proposal_id)
    assert result.status_code == 409, result.text
    assert result.json()["status"] == "FAILED"
    with Session(scenario["engine"]) as session:
        execution_id = UUID(result.json()["id"])
        assert session.scalar(select(MockERPOrder).where(MockERPOrder.execution_id == execution_id)) is None
        assert session.scalar(select(RecoveryReservation).where(RecoveryReservation.execution_id == execution_id)) is None
        assert session.scalar(select(ApprovalResumeJob).where(ApprovalResumeJob.proposal_id == UUID(proposal_id))).status == "FAILED"
    assert execute(scenario, proposal_id).json()["id"] == result.json()["id"]


def test_mutated_approved_payload_is_blocked(scenario):
    from uuid import UUID
    from copy import deepcopy
    proposal_id = approved(scenario)
    with Session(scenario["engine"]) as session, session.begin():
        proposal = session.get(RecoveryProposal, UUID(proposal_id))
        snapshot = deepcopy(proposal.plan_snapshot)
        snapshot["parameters"]["fixed_transport_cost"] = "1"
        proposal.plan_snapshot = snapshot
    result = execute(scenario, proposal_id)
    assert result.status_code == 409 and "binding" in result.json()["detail"]


def test_definitive_mock_rejection_rolls_back_holds(scenario, monkeypatch):
    proposal_id = approved(scenario)
    def reject(**kwargs):
        raise MockERPRejected("Simulated definitive rejection")
    monkeypatch.setattr(execution_service, "submit_mock_order", reject)
    result = execute(scenario, proposal_id)
    assert result.status_code == 409 and result.json()["status"] == "FAILED"
    with Session(scenario["engine"]) as session:
        balance = session.scalar(select(InventoryBalance).where(InventoryBalance.location_id == scenario["ids"]["warehouse"]))
        assert balance.reserved_qty == Decimal("0")
        assert session.scalar(select(RecoveryDemandClaim).where(RecoveryDemandClaim.demand_id.in_(
            select(ProductionDemand.id).where(ProductionDemand.product_id == scenario["ids"]["product"])))) is None


def test_crash_after_local_order_write_rolls_back_everything(scenario, monkeypatch):
    from uuid import UUID
    proposal_id = approved(scenario)
    original = execution_service.submit_mock_order
    def crash(**kwargs):
        original(**kwargs)
        raise RuntimeError("Simulated crash after local order insert")
    monkeypatch.setattr(execution_service, "submit_mock_order", crash)
    with pytest.raises(RuntimeError, match="Simulated crash"):
        execute(scenario, proposal_id)
    with Session(scenario["engine"]) as session:
        assert session.scalar(select(RecoveryExecution).where(RecoveryExecution.proposal_id == UUID(proposal_id))) is None
        assert session.scalar(select(ApprovalResumeJob).where(ApprovalResumeJob.proposal_id == UUID(proposal_id))).status == "PENDING"
        balance = session.scalar(select(InventoryBalance).where(InventoryBalance.location_id == scenario["ids"]["warehouse"]))
        assert balance.reserved_qty == Decimal("0")
    monkeypatch.setattr(execution_service, "submit_mock_order", original)
    assert execute(scenario, proposal_id).status_code == 201


def test_concurrent_execution_requests_create_one_order(scenario):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    proposal_id = approved(scenario)
    barrier = Barrier(2)
    def send(_):
        with TestClient(scenario["app"]) as client:
            barrier.wait(timeout=10)
            return client.post(f"/api/v1/proposals/{proposal_id}/execute-mock")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, range(2)))
    assert sorted(row.status_code for row in results) == [200, 201]
    assert results[0].json()["id"] == results[1].json()["id"]


@pytest.mark.parametrize("role", ["ADMIN", "OPERATOR"])
def test_execution_requires_manager(scenario, role):
    proposal_id = approved(scenario)
    scenario["app"].dependency_overrides[current_actor] = lambda: Actor("test", role)
    assert execute(scenario, proposal_id).status_code == 403


def test_execution_requires_bearer(scenario):
    scenario["app"].dependency_overrides.clear()
    assert execute(scenario, uuid4()).status_code == 401


def test_two_incidents_cannot_buy_for_the_same_demand_pool(scenario):
    first = approved(scenario, "purchase")
    other_id = uuid4()
    with Session(scenario["engine"]) as session, session.begin():
        session.add(Incident(id=other_id, source_system="TEST", source_ref=uuid4().hex,
            title="Overlapping incident", product_id=scenario["ids"]["product"],
            plant_id=scenario["ids"]["plant"], status="OPEN", detected_at=datetime.now(timezone.utc)))
    result = scenario["client"].post(f"/api/v1/incidents/{other_id}/proposals/purchase",
        headers={"Idempotency-Key": "other-purchase"},
        json={"offer_id": str(scenario["ids"]["offer"]), "freight_cost": "12000", "currency": "LKR"})
    assert result.status_code == 201, result.text
    second = result.json()["id"]
    assert decide(scenario, second, key="other-decision").status_code == 201
    assert execute(scenario, first).status_code == 201
    denied = execute(scenario, second)
    assert denied.status_code == 409, denied.text
    assert "planning pool" in denied.json()["failure_reason"]


def test_supplier_capacity_is_shared_across_different_plants(scenario):
    other_plant, other_incident = uuid4(), uuid4()
    scenario["extra_locations"].append(other_plant)
    now = datetime.now(timezone.utc)
    with Session(scenario["engine"]) as session, session.begin():
        session.add(Location(id=other_plant, code=f"OTHER-{uuid4().hex[:12]}", name="Other plant", type="PLANT"))
        session.flush()
        session.add(InventoryBalance(product_id=scenario["ids"]["product"], location_id=other_plant,
            on_hand_qty=Decimal("20"), reserved_qty=Decimal("0"), observed_at=now,
            source_system="TEST", source_version="1"))
        session.add(ProductionDemand(product_id=scenario["ids"]["product"], plant_id=other_plant,
            source_system="TEST", source_ref=uuid4().hex, required_qty=Decimal("100"),
            fulfilled_qty=Decimal("0"), required_at=now + timedelta(hours=8), status="OPEN"))
        session.add(Incident(id=other_incident, source_system="TEST", source_ref=uuid4().hex,
            title="Other plant shortage", product_id=scenario["ids"]["product"], plant_id=other_plant,
            status="OPEN", detected_at=now))
    first = approved(scenario, "purchase")
    result = scenario["client"].post(f"/api/v1/incidents/{other_incident}/proposals/purchase",
        headers={"Idempotency-Key": "other-plant-purchase"},
        json={"offer_id": str(scenario["ids"]["offer"]), "freight_cost": "12000", "currency": "LKR"})
    assert result.status_code == 201, result.text
    second = result.json()["id"]
    assert decide(scenario, second, key="other-plant-decision").status_code == 201
    assert execute(scenario, first).status_code == 201
    rejected = execute(scenario, second)
    assert rejected.status_code == 409, rejected.text
    assert "supplier offer quantity" in rejected.json()["failure_reason"]
