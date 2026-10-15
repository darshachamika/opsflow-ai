from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app
from app.services.impact_assessment import ImpactTargetNotFound


TRANSFER_URL = "/api/v1/recovery/transfers/evaluate"
PURCHASE_URL = "/api/v1/recovery/purchases/evaluate"

TRANSFER_SERVICE = "app.api.recovery.recommend_warehouse_transfer"
PURCHASE_SERVICE = "app.api.recovery.recommend_supplier_purchases"

TRANSFER_BODY = {
    "sku": "FAN-MOTOR-45W",
    "plant_code": "LK-HOM-PLANT",
    "warehouse_code": "LK-WAT-WH",
    "lead_time_hours": 6,
    "fixed_transport_cost": "18000.00",
    "currency": "LKR",
}

PURCHASE_BODY = {
    "sku": "FAN-MOTOR-45W",
    "plant_code": "LK-HOM-PLANT",
    "freight_cost": "12000.00",
    "currency": "LKR",
}


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def base_response():
    return {
        "status": "INCOMPLETE",
        "assessed_at": "2026-10-16T10:00:00+00:00",
        "sku": "FAN-MOTOR-45W",
        "plant_code": "LK-HOM-PLANT",
        "issues": [],
        "assumptions": [],
        "execution_status": "NOT_EXECUTED",
    }


def test_transfer_returns_typed_plan(client):
    payload = base_response()
    payload.update({
        "status": "FULL_COVERAGE",
        "warehouse_code": "LK-WAT-WH",
        "plan": {
            "warehouse_name": "Wattala Distribution Warehouse",
            "warehouse_observed_at": "2026-10-16T10:00:00+00:00",
            "arrival_at": "2026-10-16T16:00:00+00:00",
            "available_qty": "380.000",
            "transfer_qty": "280.000",
            "remaining_warehouse_qty": "100.000",
            "remaining_shortage_qty": "0.000",
            "transport_cost": "18000.00",
            "currency": "LKR",
            "allocations": [
                {
                    "demand_id": "11111111-1111-4111-8111-111111111111",
                    "source_ref": "TEST-DEMAND",
                    "allocated_qty": "280.000",
                    "remaining_shortage_qty": "0.000",
                    "arrives_by_deadline": True,
                }
            ],
        },
    })

    with patch(TRANSFER_SERVICE, return_value=payload) as service:
        response = client.post(TRANSFER_URL, json=TRANSFER_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FULL_COVERAGE"
    assert body["plan"]["transport_cost"] == "18000.00"
    assert body["plan"]["transfer_qty"] == "280.000"
    assert body["execution_status"] == "NOT_EXECUTED"

    from datetime import timedelta
    from decimal import Decimal

    service.assert_called_once_with(
        sku="FAN-MOTOR-45W",
        plant_code="LK-HOM-PLANT",
        warehouse_code="LK-WAT-WH",
        lead_time=timedelta(hours=6),
        fixed_transport_cost=Decimal("18000.00"),
        currency="LKR",
    )


def test_purchase_preserves_option_costs(client):
    payload = base_response()
    payload.update({
        "status": "OPTIONS_AVAILABLE",
        "options": [
            {
                "offer_id": "22222222-2222-4222-8222-222222222222",
                "supplier_code": "SUP-LK-002",
                "supplier_name": "Demo Supplier",
                "observed_at": "2026-10-16T10:00:00+00:00",
                "valid_until": "2026-10-17T10:00:00+00:00",
                "unit_price": "2100.0000",
                "currency": "LKR",
                "status": "FULL_COVERAGE",
                "reasons": [],
                "plan": {
                    "arrival_at": "2026-10-16T17:00:00+00:00",
                    "purchase_qty": "280.000",
                    "items_cost": "588000.0000",
                    "freight_cost": "12000.00",
                    "total_cost": "600000.0000",
                    "allocations": [
                        {
                            "demand_id": (
                                "11111111-1111-4111-8111-111111111111"
                            ),
                            "source_ref": "TEST-DEMAND",
                            "allocated_qty": "280.000",
                            "remaining_shortage_qty": "0.000",
                            "arrives_by_deadline": True,
                        }
                    ],
                },
            }
        ],
    })

    with patch(PURCHASE_SERVICE, return_value=payload):
        response = client.post(PURCHASE_URL, json=PURCHASE_BODY)

    assert response.status_code == 200
    option = response.json()["options"][0]
    assert option["unit_price"] == "2100.0000"
    assert option["plan"]["total_cost"] == "600000.0000"


@pytest.mark.parametrize("kind", ["transfer", "purchase"])
def test_incomplete_response_has_no_plan(client, kind):
    payload = base_response()
    payload["issues"] = [{
        "code": "INVENTORY_STALE",
        "reference": "LK-HOM-PLANT",
        "message": "Refresh inventory evidence.",
    }]

    if kind == "transfer":
        url, service, request = TRANSFER_URL, TRANSFER_SERVICE, TRANSFER_BODY
        payload.update({"warehouse_code": "LK-WAT-WH", "plan": None})
    else:
        url, service, request = PURCHASE_URL, PURCHASE_SERVICE, PURCHASE_BODY
        payload["options"] = []

    with patch(service, return_value=payload):
        response = client.post(url, json=request)

    assert response.status_code == 200
    assert response.json()["status"] == "INCOMPLETE"
    assert response.json()["issues"][0]["code"] == "INVENTORY_STALE"


@pytest.mark.parametrize(
    "field, value",
    [
        ("fixed_transport_cost", "-1"),
        ("fixed_transport_cost", "NaN"),
        ("lead_time_hours", -1),
        ("sku", "   "),
        ("currency", "lkr"),
        ("unexpected_field", "not allowed"),
    ],
)
def test_invalid_transfer_request_is_rejected(client, field, value):
    request = {**TRANSFER_BODY, field: value}

    with patch(TRANSFER_SERVICE) as service:
        response = client.post(TRANSFER_URL, json=request)

    assert response.status_code == 422
    service.assert_not_called()


@pytest.mark.parametrize("value", ["-1", "Infinity"])
def test_invalid_freight_is_rejected(client, value):
    request = {**PURCHASE_BODY, "freight_cost": value}

    with patch(PURCHASE_SERVICE) as service:
        response = client.post(PURCHASE_URL, json=request)

    assert response.status_code == 422
    service.assert_not_called()

@pytest.mark.parametrize(
    "url, service, request_body",
    [
        (TRANSFER_URL, TRANSFER_SERVICE, TRANSFER_BODY),
        (PURCHASE_URL, PURCHASE_SERVICE, PURCHASE_BODY),
    ],
)
def test_missing_target_returns_404(
    client,
    url,
    service,
    request_body,
):
    with patch(
        service,
        side_effect=ImpactTargetNotFound("Product not found."),
    ):
        response = client.post(url, json=request_body)

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found."


@pytest.mark.parametrize(
    "url, service, request_body",
    [
        (TRANSFER_URL, TRANSFER_SERVICE, TRANSFER_BODY),
        (PURCHASE_URL, PURCHASE_SERVICE, PURCHASE_BODY),
    ],
)
def test_database_failure_returns_safe_503(
    client,
    url,
    service,
    request_body,
):
    error = OperationalError(
        "private_test_sql",
        {},
        Exception("private_test_details"),
    )

    with patch(service, side_effect=error):
        response = client.post(url, json=request_body)

    assert response.status_code == 503
    assert "private_test" not in response.text