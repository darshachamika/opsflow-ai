from datetime import datetime, timedelta, timezone
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api import web_auth
from app.core import database
from app.core.approval_auth import current_actor, require_manager
from app.core.passwords import hash_password, verify_password
from app.models.web_identity import WebUser, WebSession
from app.services.web_sessions import session_identity, fingerprint

PASSWORD = 'A long test-only password 123'
ORIGIN = {'Origin':'http://localhost:3000'}

@pytest.fixture
def auth(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    WebUser.__table__.create(engine)
    WebSession.__table__.create(engine)
    with Session(engine) as s, s.begin():
        s.add(WebUser(subject='operator', role='OPERATOR', password_hash=hash_password(PASSWORD)))
        s.add(WebUser(subject='manager', role='PROCUREMENT_MANAGER', password_hash=hash_password(PASSWORD)))
    monkeypatch.setattr(web_auth, 'engine', engine)
    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(web_auth.web_settings, 'cors_allowed_origins', ['http://localhost:3000'])
    monkeypatch.setattr(web_auth.session_settings, 'session_cookie_secure', False)
    app=FastAPI()
    app.include_router(web_auth.router)
    @app.get('/api/v1/who')
    def who(actor=Depends(current_actor)):
        return {'subject':actor.subject,'role':actor.role}
    @app.post('/api/v1/action')
    def action(actor=Depends(require_manager)):
        return {'ok':True}
    with TestClient(app) as client:
        yield client,engine
    engine.dispose()

def login(client, subject='manager', password=PASSWORD):
    return client.post('/api/v1/auth/login', json={'subject':subject,'password':password}, headers=ORIGIN)

def test_password_salted_and_verified():
    one=hash_password(PASSWORD)
    assert one!=hash_password(PASSWORD)
    assert verify_password(PASSWORD,one)
    assert not verify_password('wrong',one)
    assert not verify_password(PASSWORD,'broken')

def test_login_cookie_roles_and_logout(auth):
    client,engine=auth
    response=login(client)
    assert response.status_code==200
    assert response.json()=={'subject':'manager','role':'PROCUREMENT_MANAGER'}
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=lax' in response.headers['set-cookie']
    assert response.headers['cache-control']=='no-store'
    assert client.get('/api/v1/who').status_code==200
    assert client.post('/api/v1/action',headers=ORIGIN).status_code==200
    assert client.post('/api/v1/action').status_code==403
    assert client.post('/api/v1/action',headers={'Origin':'https://attacker.example'}).status_code==403
    old=client.cookies.get('opsflow_session')
    assert client.post('/api/v1/auth/logout',headers=ORIGIN).status_code==204
    assert client.get('/api/v1/who').status_code==401
    with Session(engine) as session:
        assert session_identity(session,old,now=datetime.now(timezone.utc)) is None

@pytest.mark.parametrize('subject',['operator','manager'])
def test_current_role_checked_from_database(auth,subject):
    client,engine=auth
    login(client,subject)
    with Session(engine) as s,s.begin():
        s.get(WebUser,subject).role='OPERATOR'
    assert client.post('/api/v1/action',headers=ORIGIN).status_code==403

@pytest.mark.parametrize('origin',[None,'null','https://attacker.example'])
def test_login_rejects_untrusted_origin(auth,origin):
    client,_=auth
    headers={} if origin is None else {'Origin':origin}
    assert client.post('/api/v1/auth/login',json={'subject':'manager','password':PASSWORD},headers=headers).status_code==403

def test_lockout_persisted_and_unknown_generic(auth):
    client,engine=auth
    unknown=login(client,'unknown','wrong').json()
    for _ in range(5):
        response=login(client,'manager','wrong')
        assert response.status_code==401
        assert response.json()==unknown
    assert login(client).status_code==401
    with Session(engine) as s,s.begin():
        s.get(WebUser,'manager').locked_until=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert login(client).status_code==200

def test_new_login_revokes_previous_and_disabled_user(auth):
    client,engine=auth
    login(client); old=client.cookies.get('opsflow_session')
    login(client); new=client.cookies.get('opsflow_session')
    assert old!=new
    with Session(engine) as s,s.begin():
        assert session_identity(s,old,now=datetime.now(timezone.utc)) is None
        s.get(WebUser,'manager').enabled=False
    assert client.get('/api/v1/who').status_code==401

def test_expired_session_denied(auth):
    client,engine=auth
    login(client)
    with Session(engine) as s,s.begin():
        s.get(WebSession,fingerprint(client.cookies.get('opsflow_session'))).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert client.get('/api/v1/who').status_code==401

def test_no_user_selected_role_on_login(auth):
    client,_=auth
    assert client.post('/api/v1/auth/login',json={'subject':'manager','password':PASSWORD,'role':'ADMIN'},headers=ORIGIN).status_code==422
