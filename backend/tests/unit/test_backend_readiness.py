import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from starlette.middleware.cors import CORSMiddleware
from app.main import app
from app.core.config import settings
from app.core.web_config import WebSettings


API_OPERATIONS = [(method.upper(), path) for path, operations in app.openapi()['paths'].items()
                  if path.startswith('/api/v1/') and path not in {'/api/v1/auth/login','/api/v1/auth/logout'} for method in operations
                  if method in {'get', 'post', 'put', 'patch', 'delete'}]

@pytest.mark.parametrize('method,path', API_OPERATIONS)
def test_every_business_operation_requires_auth(method, path):
    import re
    path = re.sub(r'\{[^}]+\}', str(uuid4()), path)
    with TestClient(app) as client:
        response = client.request(method, path)
    assert response.status_code == 401, response.text
    assert response.headers['www-authenticate'] == 'Bearer'


def test_real_token_auth_and_manager_boundary(monkeypatch):
    token = 'readiness-test-token'
    monkeypatch.setattr(settings, 'approval_principals_json', SecretStr(json.dumps([{
        'subject': 'readiness.operator', 'role': 'OPERATOR',
        'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }])))
    with TestClient(app) as client:
        headers = {'Authorization': f'Bearer {token}'}
        assert client.get('/api/v1/auth/me', headers=headers).json()['role'] == 'OPERATOR'
        for endpoint in ['decision', 'execute-mock']:
            response = client.post(f'/api/v1/proposals/{uuid4()}/{endpoint}', headers=headers,
                                   json={'decision': 'APPROVED', 'reason': 'test'})
            assert response.status_code == 403
        assert client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer wrong'}).status_code == 401
        assert client.get('/health/live').status_code == 200


@pytest.mark.parametrize('origin', ['*', 'https://example.com/path', 'https://user:pass@example.com', 'ftp://example.com'])
def test_unsafe_origins_rejected(origin):
    with pytest.raises(ValidationError):
        WebSettings(_env_file=None, cors_allowed_origins=[origin])


def test_cors_preflight_and_unauthenticated_actual_request():
    # Wrap the actual application in the same middleware with explicit test configuration.
    wrapped = CORSMiddleware(app, allow_origins=['http://localhost:3000'],
        allow_credentials=False, allow_methods=['GET', 'POST'],
        allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key'])
    with TestClient(wrapped) as client:
        headers = {'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'POST',
                   'Access-Control-Request-Headers': 'authorization,content-type,idempotency-key'}
        response = client.options('/api/v1/incidents', headers=headers)
        assert response.status_code == 200
        assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'
        headers['Origin'] = 'https://untrusted.example'
        response = client.options('/api/v1/incidents', headers=headers)
        assert response.status_code == 400
        assert 'access-control-allow-origin' not in response.headers
        response = client.get('/api/v1/auth/me', headers={'Origin': 'http://localhost:3000'})
        assert response.status_code == 401
        assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'
