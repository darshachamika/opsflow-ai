from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import orchestration as api
from app.core.approval_auth import Actor, current_actor
from app.schemas.orchestration import OrchestrationRequest
from app.services import orchestration as service


def body():
    return dict(warehouse_code="LK-WAT-WH", transfer_lead_time_hours=6,
                transport_cost="18000", purchase_freight_cost="12000", currency="LKR")


@pytest.mark.parametrize("impact,transfer,purchase,expected", [
    ({"status": "INCOMPLETE", "allocations": []}, None, None, "NEEDS_EVIDENCE"),
    ({"status": "NO_OPEN_DEMANDS", "allocations": []}, None, None, "NO_ACTION_NEEDED"),
    ({"status": "ASSESSED", "allocations": [{"shortage_qty": "0"}]}, None, None, "NO_ACTION_NEEDED"),
    ({"status": "ASSESSED", "allocations": [{"shortage_qty": "80"}]}, {"status": "FULL_COVERAGE"}, None, "OPTIONS_READY"),
    ({"status": "ASSESSED", "allocations": [{"shortage_qty": "80"}]}, {"status": "INCOMPLETE"}, {"status": "OPTIONS_AVAILABLE", "options": [{"status": "PARTIAL_COVERAGE"}]}, "OPTIONS_READY"),
    ({"status": "ASSESSED", "allocations": [{"shortage_qty": "80"}]}, {"status": "INCOMPLETE"}, {"status": "NO_OPTIONS", "options": []}, "NEEDS_EVIDENCE"),
    ({"status": "ASSESSED", "allocations": [{"shortage_qty": "80"}]}, {"status": "NO_FEASIBLE_TRANSFER"}, {"status": "NO_OPTIONS", "options": [{"status": "BLOCKED"}]}, "NO_FEASIBLE_OPTION"),
])
def test_decision_boundaries(impact, transfer, purchase, expected):
    assert service.summarize(impact, transfer, purchase)["status"] == expected


@pytest.mark.parametrize("field,value", [("transport_cost", "NaN"), ("purchase_freight_cost", "-1"), ("currency", "lkr"), ("transfer_lead_time_hours", -1)])
def test_invalid_planning_inputs(field, value):
    data = body()
    data[field] = value
    with pytest.raises(ValidationError):
        OrchestrationRequest(**data)


@pytest.mark.parametrize("incomplete", [True, False])
def test_shared_snapshot_and_evidence_gate(monkeypatch, incomplete):
    incident_id = uuid4()
    session = Mock()
    session.get.side_effect = [SimpleNamespace(id=incident_id, product_id=uuid4(), plant_id=uuid4(), status="OPEN"), SimpleNamespace(sku="MOTOR"), SimpleNamespace(code="PLANT", type="PLANT")]
    impact = Mock(return_value={"status": "INCOMPLETE" if incomplete else "ASSESSED", "allocations": [{"shortage_qty": "80"}]})
    transfer = Mock(return_value={"status": "FULL_COVERAGE"})
    purchase = Mock(return_value={"status": "OPTIONS_AVAILABLE", "options": []})
    monkeypatch.setattr(service, "_assess", impact)
    monkeypatch.setattr(service, "_recommend_transfer", transfer)
    monkeypatch.setattr(service, "_recommend_purchases", purchase)
    now = datetime.now(timezone.utc)
    result = service._plan(session, incident_id, OrchestrationRequest(**body()), now)
    if incomplete:
        transfer.assert_not_called()
        purchase.assert_not_called()
    else:
        for call in (impact, transfer, purchase):
            assert call.call_args.kwargs["session"] is session
            assert call.call_args.kwargs["as_of"] == now
    session.add.assert_not_called()
    assert result["persisted"] is False and result["llm_used"] is False


def test_authentication_required(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    planner = Mock()
    monkeypatch.setattr(api, "plan_incident", planner)
    with TestClient(app) as client:
        assert client.post(f"/api/v1/incidents/{uuid4()}/plan", json=body()).status_code == 401
    planner.assert_not_called()


def test_authenticated_preview(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[current_actor] = lambda: Actor("test.operator", "OPERATOR")
    monkeypatch.setattr(api, "plan_incident", lambda *_: {"status": "OPTIONS_READY", "persisted": False})
    with TestClient(app) as client:
        response = client.post(f"/api/v1/incidents/{uuid4()}/plan", json=body())
    assert response.status_code == 200
    assert response.json()["persisted"] is False
