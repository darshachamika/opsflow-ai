from uuid import uuid4
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import workflows as api
from app.core.approval_auth import Actor, current_actor
from app.schemas.orchestration import OrchestrationRequest
from app.services import workflows as service


def body():
    return dict(warehouse_code="WH", transfer_lead_time_hours=6, transport_cost="18000", purchase_freight_cost="12000", currency="LKR")


def test_equivalent_decimal_inputs_have_same_hash():
    incident = uuid4()
    a=OrchestrationRequest(**body())
    b=OrchestrationRequest(**{**body(), "transport_cost": "18000.0000"})
    assert service.fingerprint(incident, service.normalize_inputs(a)) == service.fingerprint(incident, service.normalize_inputs(b))
    assert service.fingerprint(uuid4(), service.normalize_inputs(a)) != service.fingerprint(incident, service.normalize_inputs(a))


def test_replay_never_calls_planner_or_llm(monkeypatch):
    run_id=uuid4()
    monkeypatch.setattr(service, "_claim", lambda *_:(run_id,False))
    monkeypatch.setattr(service, "get_run", lambda _: {"id":str(run_id),"status":"SUCCEEDED"})
    planner=Mock(side_effect=AssertionError("Do not plan again"))
    monkeypatch.setattr(service,"plan_incident",planner)
    monkeypatch.setattr(service,"add_explanation",planner)
    result,created=service.create_run(uuid4(),OrchestrationRequest(**body()),"actor","key")
    assert not created and result["id"]==str(run_id)
    planner.assert_not_called()


@pytest.fixture
def client():
    app=FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[current_actor]=lambda:Actor("test.manager","PROCUREMENT_MANAGER")
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("status,created,expected",[("SUCCEEDED",True,201),("SUCCEEDED",False,200),("RUNNING",False,202),("FAILED",False,200)])
def test_http_replay_contract(monkeypatch,client,status,created,expected):
    monkeypatch.setattr(service,"create_run",lambda *_:({"id":str(uuid4()),"status":status},created))
    r=client.post(f"/api/v1/incidents/{uuid4()}/runs",json=body(),headers={"Idempotency-Key":"demo-1"})
    assert r.status_code==expected
    assert r.headers["location"].startswith("/api/v1/runs/")


def test_key_required(client):
    assert client.post(f"/api/v1/incidents/{uuid4()}/runs",json=body()).status_code==422


def test_auth_required():
    app=FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        assert client.get(f"/api/v1/runs/{uuid4()}").status_code==401


def test_changed_key_is_conflict(monkeypatch,client):
    def conflict(*_): raise service.WorkflowConflict("Different inputs")
    monkeypatch.setattr(service,"create_run",conflict)
    assert client.post(f"/api/v1/incidents/{uuid4()}/runs",json=body(),headers={"Idempotency-Key":"demo-1"}).status_code==409
