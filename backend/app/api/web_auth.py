from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.database import engine
from app.core.session_config import COOKIE_NAME, COOKIE_PATH, session_settings
from app.core.web_config import web_settings
from app.models.web_identity import WebSession
from app.services.web_sessions import fingerprint, sign_in

router = APIRouter(prefix='/api/v1/auth', tags=['Browser login'])


def require_browser_origin(request: Request):
    origin = request.headers.get('origin')
    if not origin or origin not in web_settings.cors_allowed_origins:
        raise HTTPException(403, 'Browser origin is not allowed.')


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    subject: str = Field(pattern=r'^[A-Za-z0-9_.@-]{1,128}$')
    password: SecretStr = Field(min_length=1, max_length=256)


@router.post('/login')
def login(body: LoginRequest, request: Request, response: Response):
    require_browser_origin(request)
    try:
        with Session(engine) as session, session.begin():
            result = sign_in(session, body.subject, body.password.get_secret_value(),
                             now=datetime.now(timezone.utc), hours=session_settings.session_hours)
        if result is None:
            raise HTTPException(401, 'Invalid login or temporarily locked account. Try again later or contact your administrator.')
    except SQLAlchemyError:
        raise HTTPException(503, 'Login service unavailable.') from None
    token, identity = result
    response.set_cookie(COOKIE_NAME, token, max_age=session_settings.session_hours * 3600,
        httponly=True, secure=session_settings.session_cookie_secure, samesite='lax', path=COOKIE_PATH)
    response.headers['Cache-Control'] = 'no-store'
    return identity


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response):
    require_browser_origin(request)
    token = request.cookies.get(COOKIE_NAME)
    try:
        if token:
            with Session(engine) as session, session.begin():
                session.execute(delete(WebSession).where(WebSession.token_hash == fingerprint(token)))
    except SQLAlchemyError:
        raise HTTPException(503, 'Logout unavailable; retry to revoke the session.') from None
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, secure=session_settings.session_cookie_secure,
                           httponly=True, samesite='lax')
    response.headers['Cache-Control'] = 'no-store'
