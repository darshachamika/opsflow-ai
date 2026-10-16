import hashlib
import json
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException
from app.core.approval_auth import Actor, authenticate_token, require_manager

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
TOKEN = "unit-test-only-never-a-real-credential"


def config(**changes):
    row = {"subject": "manager.test", "role": "PROCUREMENT_MANAGER",
           "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
           "expires_at": (NOW + timedelta(hours=1)).isoformat(), "enabled": True}
    row.update(changes)
    return json.dumps([row])


def test_valid_identity_is_server_assigned():
    assert authenticate_token(TOKEN, config(), now=NOW) == Actor("manager.test", "PROCUREMENT_MANAGER")


@pytest.mark.parametrize("case", ["unknown", "expired", "disabled", "empty"])
def test_invalid_credentials_fail_closed(case):
    raw, token = config(), TOKEN
    if case == "unknown": token = "wrong"
    elif case == "expired": raw = config(expires_at=NOW.isoformat())
    elif case == "disabled": raw = config(enabled=False)
    else: raw = "[]"
    with pytest.raises(HTTPException) as exc:
        authenticate_token(token, raw, now=NOW)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("role", ["ADMIN", "OPERATOR"])
def test_admin_or_operator_cannot_approve(role):
    with pytest.raises(HTTPException) as exc:
        require_manager(Actor("someone", role))
    assert exc.value.status_code == 403


def test_manager_can_approve():
    actor = Actor("manager", "PROCUREMENT_MANAGER")
    assert require_manager(actor) == actor


@pytest.mark.parametrize("raw", ["broken-json", '{}', '[{"token":"secret"}]'])
def test_bad_configuration_is_unavailable(raw):
    with pytest.raises(HTTPException) as exc:
        authenticate_token(TOKEN, raw, now=NOW)
    assert exc.value.status_code == 503
    assert "secret" not in exc.value.detail


def test_duplicate_token_rejected():
    rows = json.loads(config())
    with pytest.raises(HTTPException) as exc:
        authenticate_token(TOKEN, json.dumps(rows * 2), now=NOW)
    assert exc.value.status_code == 503


def test_bearer_header_authenticates_through_fastapi(monkeypatch):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from app.core import approval_auth
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    monkeypatch.setattr(approval_auth.settings, "approval_principals_json", SecretStr(config(expires_at=future.isoformat())))
    app = FastAPI()
    @app.get("/protected")
    def protected(actor=Depends(require_manager)):
        return {"subject": actor.subject}
    with TestClient(app) as client:
        assert client.get("/protected").status_code == 401
        result = client.get("/protected", headers={"Authorization": f"Bearer {TOKEN}"})
        assert result.status_code == 200
        assert result.json() == {"subject": "manager.test"}
