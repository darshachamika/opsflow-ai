from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.api import incident_history as api
from app.core.approval_auth import Actor, current_actor
from app.services.incident_history import serialize_record, HistoryNotFound


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[current_actor] = lambda: Actor("reader", "OPERATOR")
    with TestClient(app) as client:
        yield client


def test_requires_authentication():
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        assert client.get(f"/api/v1/incidents/{uuid4()}/history").status_code == 401


def test_passes_pagination(client, monkeypatch):
    service = Mock(return_value={"items": [], "next_before_version": None})
    monkeypatch.setattr(api, "get_history", service)
    target = uuid4()
    assert client.get(f"/api/v1/incidents/{target}/history?limit=2&before_version=6").status_code == 200
    service.assert_called_once_with(target, limit=2, before_version=6)


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "before_version=0"])
def test_invalid_pagination(client, query):
    assert client.get(f"/api/v1/incidents/{uuid4()}/history?{query}").status_code == 422


@pytest.mark.parametrize("error,status", [(HistoryNotFound("Incident not found."),404),
    (OperationalError("secret SQL", {}, Exception("private")),503)])
def test_error_mapping(client, monkeypatch, error, status):
    monkeypatch.setattr(api, "get_history", Mock(side_effect=error))
    response = client.get(f"/api/v1/incidents/{uuid4()}/history")
    assert response.status_code == status
    assert "private" not in response.text and "secret SQL" not in response.text


def test_missing_related_records_and_no_snapshot_exposure():
    proposal = SimpleNamespace(id=uuid4(), version=1, action_type="WAREHOUSE_TRANSFER", status="PROPOSED",
        created_at=None, assessed_at=None, expires_at=None, plan_snapshot={"private":"excluded"})
    record = serialize_record(proposal, None, None, None)
    assert record["decision"] is None and record["resume_job"] is None and record["execution"] is None
    assert "plan_snapshot" not in record["proposal"]
