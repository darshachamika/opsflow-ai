from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.connectors.mock_erp import MockERPRejected, submit_mock_order
from app.services.approval_binding import digest
from app.core.approval_auth import Actor
from app.services.execution import execute_mock


def test_existing_key_returns_original_order():
    execution = SimpleNamespace(id=uuid4(), execution_key="key")
    payload = {"quantity": "80", "currency": "LKR"}
    order = SimpleNamespace(execution_id=execution.id, payload_hash=digest(payload))
    session = SimpleNamespace(scalar=lambda query: order)
    assert submit_mock_order(session=session, execution=execution, action_type="WAREHOUSE_TRANSFER", payload=payload) is order


def test_same_key_with_changed_payload_is_rejected():
    execution = SimpleNamespace(id=uuid4(), execution_key="key")
    order = SimpleNamespace(execution_id=execution.id, payload_hash=digest({"quantity": "80"}))
    session = SimpleNamespace(scalar=lambda query: order)
    with pytest.raises(MockERPRejected):
        submit_mock_order(session=session, execution=execution, action_type="WAREHOUSE_TRANSFER", payload={"quantity": "81"})


@pytest.mark.parametrize("role", ["ADMIN", "OPERATOR"])
def test_internal_execution_service_checks_role_before_database_access(role):
    with pytest.raises(PermissionError):
        execute_mock(session=None, proposal_id=uuid4(), actor=Actor("test", role))
