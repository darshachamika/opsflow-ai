import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.passwords import DUMMY_HASH, verify_password
from app.models.web_identity import WebUser, WebSession


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sign_in(session: Session, subject: str, password: str, *, now: datetime, hours: int):
    """Caller MUST commit rejected attempts; never raise before committing them."""
    user = session.scalar(select(WebUser).where(WebUser.subject == subject).with_for_update())
    if user is None:
        verify_password(password, DUMMY_HASH)
        return None
    if user.locked_until and utc(user.locked_until) > now:
        verify_password(password, DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash) or not user.enabled:
        user.failed_attempts += 1
        if user.failed_attempts >= 5:
            user.locked_until = now + timedelta(minutes=15)
            user.failed_attempts = 0
        return None
    user.failed_attempts = 0
    user.locked_until = None
    # A new login revokes the previous login, limiting active session proliferation.
    session.execute(delete(WebSession).where(WebSession.subject == subject))
    session.execute(delete(WebSession).where(WebSession.expires_at <= now))
    token = secrets.token_urlsafe(48)
    session.add(WebSession(token_hash=fingerprint(token), subject=subject,
                           expires_at=now + timedelta(hours=hours)))
    return token, {'subject': user.subject, 'role': user.role}


def session_identity(session: Session, token: str, *, now: datetime):
    if not token or len(token) > 512:
        return None
    row = session.execute(select(WebSession, WebUser).join(WebUser)
        .where(WebSession.token_hash == fingerprint(token))).first()
    if row is None or not row[1].enabled or utc(row[0].expires_at) <= now:
        return None
    return {'subject': row[1].subject, 'role': row[1].role}
