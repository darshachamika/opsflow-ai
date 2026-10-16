"""Transactional local simulator. Never calls a real ERP or external network."""
from sqlalchemy import select
from app.models.execution import MockERPOrder
from app.services.approval_binding import digest


class MockERPRejected(ValueError):
    """Definitive local rejection; no remote/uncertain outcome is implied."""


def submit_mock_order(*, session, execution, action_type, payload):
    fingerprint = digest(payload)
    existing = session.scalar(select(MockERPOrder).where(MockERPOrder.execution_key == execution.execution_key))
    if existing is not None:
        if existing.payload_hash != fingerprint or existing.execution_id != execution.id:
            raise MockERPRejected("Execution key already belongs to another payload.")
        return existing
    order = MockERPOrder(execution_id=execution.id, execution_key=execution.execution_key,
        external_ref=f"MOCK-{execution.id}", action_type=action_type,
        payload_hash=fingerprint, payload=payload)
    session.add(order)
    session.flush()
    return order
