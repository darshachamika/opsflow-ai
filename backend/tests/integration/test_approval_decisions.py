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
    suffix = uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(approval_api.router)
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
            yield {"engine": engine, "client": client, "ids": ids, "suffix": suffix, "app": app}
    finally:
        with Session(engine) as session, session.begin():
            proposal_ids = select(RecoveryProposal.id).where(RecoveryProposal.incident_id == ids["incident"])
            session.execute(delete(ApprovalResumeJob).where(ApprovalResumeJob.proposal_id.in_(proposal_ids)))
            session.execute(delete(ApprovalDecision).where(ApprovalDecision.proposal_id.in_(proposal_ids)))
            session.execute(delete(RecoveryProposal).where(RecoveryProposal.incident_id == ids["incident"]))
            session.execute(delete(Incident).where(Incident.id == ids["incident"]))
            session.execute(delete(SupplierOffer).where(SupplierOffer.product_id == ids["product"]))
            session.execute(delete(ProductionDemand).where(ProductionDemand.product_id == ids["product"]))
            session.execute(delete(InventoryBalance).where(InventoryBalance.product_id == ids["product"]))
            session.execute(delete(Product).where(Product.id == ids["product"]))
            session.execute(delete(Location).where(Location.id.in_([ids["plant"], ids["warehouse"]])))
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


def test_approval_is_atomic_idempotent_and_supersedes_alternatives(scenario):
    from uuid import UUID
    first, second = create_proposal(scenario), create_proposal(scenario, "proposal-2")
    response = decide(scenario, first)
    assert response.status_code == 201, response.text
    replay = decide(scenario, first)
    assert replay.status_code == 200 and replay.json() == response.json()
    with Session(scenario["engine"]) as session:
        assert session.get(RecoveryProposal, UUID(first)).status == "APPROVED"
        assert session.get(RecoveryProposal, UUID(second)).status == "SUPERSEDED"
        jobs = session.scalars(select(ApprovalResumeJob).where(ApprovalResumeJob.proposal_id == UUID(first))).all()
        assert len(jobs) == 1 and jobs[0].status == "PENDING"
        assert jobs[0].payload["proposal_hash"] == response.json()["proposal_hash"]
    assert decide(scenario, second, key="decision-2").status_code == 409
    assert decide(scenario, first, reason="Changed inputs").status_code == 409


def test_rejection_does_not_enqueue_job(scenario):
    from uuid import UUID
    proposal_id = create_proposal(scenario)
    result = decide(scenario, proposal_id, decision="REJECTED")
    assert result.status_code == 201, result.text
    with Session(scenario["engine"]) as session:
        assert session.get(RecoveryProposal, UUID(proposal_id)).status == "REJECTED"
        assert session.scalar(select(ApprovalResumeJob).where(ApprovalResumeJob.proposal_id == UUID(proposal_id))) is None


@pytest.mark.parametrize("change", ["stock", "stale", "expired", "closed"])
def test_invalidated_proposal_is_not_approved(scenario, change):
    from uuid import UUID
    proposal_id = create_proposal(scenario)
    with Session(scenario["engine"]) as session, session.begin():
        if change in ("stock", "stale"):
            balance = session.scalar(select(InventoryBalance).where(
                InventoryBalance.product_id == scenario["ids"]["product"],
                InventoryBalance.location_id == scenario["ids"]["warehouse"]))
            if change == "stock": balance.on_hand_qty = Decimal("0")
            else: balance.observed_at -= timedelta(hours=1)
        elif change == "expired":
            proposal = session.get(RecoveryProposal, UUID(proposal_id))
            proposal.assessed_at -= timedelta(hours=1)
            proposal.expires_at -= timedelta(hours=1)
        else:
            session.get(Incident, scenario["ids"]["incident"]).status = "RESOLVED"
    result = decide(scenario, proposal_id)
    assert result.status_code == 409, result.text
    with Session(scenario["engine"]) as session:
        assert session.get(RecoveryProposal, UUID(proposal_id)).status == "PROPOSED"
        assert session.scalar(select(ApprovalDecision).where(ApprovalDecision.proposal_id == UUID(proposal_id))) is None


@pytest.mark.parametrize("role", ["OPERATOR", "ADMIN"])
def test_non_manager_denied_at_http_boundary(scenario, role):
    proposal_id = create_proposal(scenario)
    scenario["app"].dependency_overrides[current_actor] = lambda: Actor("test.actor", role)
    assert decide(scenario, proposal_id).status_code == 403


def test_missing_bearer_denied(scenario):
    proposal_id = create_proposal(scenario)
    scenario["app"].dependency_overrides.clear()
    assert decide(scenario, proposal_id).status_code == 401


def test_job_failure_rolls_back_decision_and_status(scenario, monkeypatch):
    from uuid import UUID
    proposal_id = create_proposal(scenario)
    def fail_job(**kwargs):
        raise RuntimeError("Simulated outbox failure")
    monkeypatch.setattr(approval_service, "ApprovalResumeJob", fail_job)
    with pytest.raises(RuntimeError, match="outbox failure"):
        decide(scenario, proposal_id)
    with Session(scenario["engine"]) as session:
        assert session.get(RecoveryProposal, UUID(proposal_id)).status == "PROPOSED"
        assert session.scalar(select(ApprovalDecision).where(ApprovalDecision.proposal_id == UUID(proposal_id))) is None


def test_concurrent_approvals_select_one_action(scenario):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    first, second = create_proposal(scenario), create_proposal(scenario, "proposal-2")
    barrier = Barrier(2)
    def send(pair):
        proposal_id, key = pair
        with TestClient(scenario["app"]) as client:
            barrier.wait(timeout=10)
            return client.post(f"/api/v1/proposals/{proposal_id}/decision",
                headers={"Idempotency-Key": key},
                json={"decision": "APPROVED", "reason": "Concurrent review"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, [(first, "one"), (second, "two")]))
    assert sorted(result.status_code for result in results) == [201, 409]
    with Session(scenario["engine"]) as session:
        approved = session.scalars(select(RecoveryProposal).where(
            RecoveryProposal.incident_id == scenario["ids"]["incident"],
            RecoveryProposal.status == "APPROVED")).all()
        assert len(approved) == 1


@pytest.mark.parametrize("change_price", [False, True])
def test_purchase_approval_revalidates_selected_offer(scenario, change_price):
    result = scenario["client"].post(
        f'/api/v1/incidents/{scenario["ids"]["incident"]}/proposals/purchase',
        headers={"Idempotency-Key": "purchase-proposal"},
        json={"offer_id": str(scenario["ids"]["offer"]), "freight_cost": "12000", "currency": "LKR"})
    assert result.status_code == 201, result.text
    if change_price:
        with Session(scenario["engine"]) as session, session.begin():
            session.get(SupplierOffer, scenario["ids"]["offer"]).unit_price = Decimal("2500")
    decision = decide(scenario, result.json()["id"])
    assert decision.status_code == (409 if change_price else 201), decision.text
