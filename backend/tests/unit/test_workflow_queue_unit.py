from uuid import uuid4
from unittest.mock import Mock
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.api import workflow_queue as api
from app.core.approval_auth import Actor,current_actor
from app.services import workflow_queue as service
from app.services.orchestration import IncidentNotOpen


def body():
    return dict(warehouse_code="WH",transfer_lead_time_hours=6,transport_cost="18000",purchase_freight_cost="12000",currency="LKR")


@pytest.fixture
def client():
    app=FastAPI();app.include_router(api.router)
    app.dependency_overrides[current_actor]=lambda:Actor("worker.test","OPERATOR")
    with TestClient(app) as c: yield c


@pytest.mark.parametrize("state,http",[("RUNNING",202),("SUCCEEDED",200),("FAILED",200)])
def test_http_queue_contract(monkeypatch,client,state,http):
    run_id=uuid4()
    monkeypatch.setattr(service,"enqueue",lambda *_:run_id)
    monkeypatch.setattr(api.workflows,"get_run",lambda _:dict(id=str(run_id),status=state))
    response=client.post(f"/api/v1/incidents/{uuid4()}/queued-runs",json=body(),headers={"Idempotency-Key":"job-1"})
    assert response.status_code==http
    assert response.headers["Location"]==f"/api/v1/runs/{run_id}"


def test_queue_requires_key(client):
    assert client.post(f"/api/v1/incidents/{uuid4()}/queued-runs",json=body()).status_code==422


def test_job_history_requires_authentication():
    app=FastAPI();app.include_router(api.router)
    with TestClient(app) as c:
        assert c.get(f"/api/v1/runs/{uuid4()}/job").status_code==401


@pytest.mark.parametrize("error,retryable",[(IncidentNotOpen("closed"),False),(RuntimeError("sensitive"),True)])
def test_worker_error_classification(monkeypatch,error,retryable):
    claim=SimpleNamespace(incident_id=uuid4(),inputs=body())
    monkeypatch.setattr(service,"claim_one",lambda _:claim)
    planner=Mock(side_effect=error);finish=Mock()
    monkeypatch.setattr(service,"plan_incident",planner)
    monkeypatch.setattr(service,"finish",finish)
    assert service.process_one("worker-test")
    assert finish.call_args.kwargs.get("retryable",False)==retryable
    assert "sensitive" not in str(finish.call_args)


def test_database_failure_leaves_lease_for_recovery(monkeypatch):
    claim=SimpleNamespace(incident_id=uuid4(),inputs=body())
    monkeypatch.setattr(service,"claim_one",lambda _:claim)
    monkeypatch.setattr(service,"plan_incident",Mock(side_effect=OperationalError("",{},Exception())))
    finish=Mock();monkeypatch.setattr(service,"finish",finish)
    with pytest.raises(OperationalError):service.process_one("worker-test")
    finish.assert_not_called()


def test_idle_worker_does_no_work(monkeypatch):
    monkeypatch.setattr(service,"claim_one",lambda _:None)
    planner=Mock();monkeypatch.setattr(service,"plan_incident",planner)
    assert service.process_one("test") is False
    planner.assert_not_called()
