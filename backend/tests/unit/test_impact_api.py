from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app
from app.services.impact_assessment import ImpactTargetNotFound


SERVICE_PATH = "app.api.impact.assess_product_impact"
URL = "/api/v1/impact"

PARAMS = {
    "sku": "FAN-MOTOR-45W",
    "plant_code": "LK-HOM-PLANT",
}


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def response_payload(status="INCOMPLETE"):
    return {
        "status": status,
        "assessed_at": "2026-10-15T10:00:00+00:00",
        "sku": "FAN-MOTOR-45W",
        "plant_code": "LK-HOM-PLANT",
        "plant_name": "Homagama Assembly Plant",
        "issues": [],
        "allocations": [],
        "assumptions": [
            "Allocations are calculated, not persisted.",
        ],
    }


def test_incomplete_assessment_returns_200(client):
    payload = response_payload()
    payload["issues"] = [
        {
            "code": "INVENTORY_STALE",
            "reference": "LK-HOM-PLANT",
            "message": "Inventory evidence needs an update.",
        }
    ]

    with patch(SERVICE_PATH, return_value=payload) as service:
        response = client.get(URL, params=PARAMS)

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "INCOMPLETE"
    assert body["issues"][0]["code"] == "INVENTORY_STALE"
    assert body["allocations"] == []

    service.assert_called_once_with(**PARAMS)


def test_assessed_response_preserves_quantity_precision(client):
    payload = response_payload("ASSESSED")
    payload["allocations"] = [
        {
            "demand_id": "11111111-1111-4111-8111-111111111111",
            "source_ref": "DEMAND-TEST-001",
            "required_at": "2026-10-15T18:00:00+00:00",
            "remaining_demand": "500.000",
            "stock_allocated_qty": "120.125",
            "inbound_allocated_qty": "300.000",
            "shortage_qty": "79.875",
            "inbound_allocations": [
                {
                    "shipment_line_id": (
                        "22222222-2222-4222-8222-222222222222"
                    ),
                    "quantity": "300.000",
                }
            ],
        }
    ]

    with patch(SERVICE_PATH, return_value=payload):
        response = client.get(URL, params=PARAMS)

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ASSESSED"

    allocation = body["allocations"][0]
    assert allocation["stock_allocated_qty"] == "120.125"
    assert allocation["shortage_qty"] == "79.875"
    assert (
        allocation["inbound_allocations"][0]["quantity"]
        == "300.000"
    )


def test_no_open_demands_returns_200(client):
    with patch(
        SERVICE_PATH,
        return_value=response_payload("NO_OPEN_DEMANDS"),
    ):
        response = client.get(URL, params=PARAMS)

    assert response.status_code == 200
    assert response.json()["status"] == "NO_OPEN_DEMANDS"
    assert response.json()["allocations"] == []


def test_unknown_target_returns_404(client):
    with patch(
        SERVICE_PATH,
        side_effect=ImpactTargetNotFound("Product not found."),
    ):
        response = client.get(URL, params=PARAMS)

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found."


@pytest.mark.parametrize("missing_field", ["sku", "plant_code"])
def test_missing_parameter_returns_422(client, missing_field):
    params = PARAMS.copy()
    params.pop(missing_field)

    with patch(SERVICE_PATH) as service:
        response = client.get(URL, params=params)

    assert response.status_code == 422
    service.assert_not_called()


@pytest.mark.parametrize("field", ["sku", "plant_code"])
def test_blank_parameter_returns_422(client, field):
    params = PARAMS.copy()
    params[field] = "   "

    with patch(SERVICE_PATH) as service:
        response = client.get(URL, params=params)

    assert response.status_code == 422
    service.assert_not_called()


@pytest.mark.parametrize("field", ["sku", "plant_code"])
def test_overlong_parameter_returns_422(client, field):
    params = PARAMS.copy()
    params[field] = "X" * 65

    with patch(SERVICE_PATH) as service:
        response = client.get(URL, params=params)

    assert response.status_code == 422
    service.assert_not_called()


def test_parameters_are_trimmed(client):
    params = {
        "sku": " FAN-MOTOR-45W ",
        "plant_code": " LK-HOM-PLANT ",
    }

    with patch(
        SERVICE_PATH,
        return_value=response_payload(),
    ) as service:
        response = client.get(URL, params=params)

    assert response.status_code == 200
    service.assert_called_once_with(**PARAMS)


def test_database_error_returns_safe_503(client):
    error = OperationalError(
        "SELECT private_test_statement",
        {},
        Exception("private_test_connection_details"),
    )

    with patch(SERVICE_PATH, side_effect=error):
        response = client.get(URL, params=PARAMS)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Unable to read impact data from the database."
    }
    assert "private_test" not in response.text