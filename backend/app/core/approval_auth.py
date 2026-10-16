"""Individually provisioned, expiring bearer credentials for the approval MVP."""
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter
from typing import Literal

from app.core.config import settings


class Credential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(pattern=r"^[A-Za-z0-9_.@-]{1,128}$")
    role: Literal["PROCUREMENT_MANAGER", "OPERATOR", "ADMIN"]
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: AwareDatetime
    enabled: bool = True


@dataclass(frozen=True)
class Actor:
    subject: str
    role: str


bearer = HTTPBearer(auto_error=False, scheme_name="ApprovalBearer")


def authenticate_token(token: str, raw_config: str, *, now: datetime) -> Actor:
    if not token or len(token) > 512:
        raise HTTPException(401, "Invalid bearer credential.", headers={"WWW-Authenticate": "Bearer"})
    try:
        credentials = TypeAdapter(list[Credential]).validate_python(json.loads(raw_config))
        hashes = [item.token_sha256 for item in credentials]
        if len(set(hashes)) != len(hashes):
            raise ValueError("Duplicate credential fingerprint.")
        roles = {}
        for item in credentials:
            if item.subject in roles and roles[item.subject] != item.role:
                raise ValueError("Ambiguous subject role.")
            roles[item.subject] = item.role
    except (ValueError, TypeError):
        # Never disclose configuration content or credentials in errors/logs.
        raise HTTPException(503, "Approval authentication is not configured correctly.") from None
    digest = hashlib.sha256(token.encode()).hexdigest()
    match = None
    for credential in credentials:
        if hmac.compare_digest(digest, credential.token_sha256):
            match = credential
    if match is None or not match.enabled or match.expires_at <= now:
        raise HTTPException(401, "Invalid or expired bearer credential.", headers={"WWW-Authenticate": "Bearer"})
    return Actor(subject=match.subject, role=match.role)


def current_actor(
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Actor:
    if credential is None or credential.scheme.lower() != "bearer":
        raise HTTPException(401, "Bearer credential required.", headers={"WWW-Authenticate": "Bearer"})
    return authenticate_token(credential.credentials,
        settings.approval_principals_json.get_secret_value(), now=datetime.now(timezone.utc))


def require_manager(actor: Annotated[Actor, Depends(current_actor)]) -> Actor:
    if actor.role != "PROCUREMENT_MANAGER":
        raise HTTPException(403, "Procurement manager permission required.")
    return actor
