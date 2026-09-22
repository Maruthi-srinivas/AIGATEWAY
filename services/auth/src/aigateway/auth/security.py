from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from aigateway.config import AuthSettings

hasher = PasswordHasher()

API_KEY_PREFIX_LEN = 16
ROLES = (
    "platform_admin",
    "security_admin",
    "app_user",
    "viewer",
    "service_account",
)
PLATFORM_ROLE = "platform_admin"
PLATFORM_SLUG = "platform"


def hash_secret(value: str) -> str:
    return hasher.hash(value)


def verify_secret(hashed: str, plain: str) -> bool:
    try:
        return hasher.verify(hashed, plain)
    except (VerifyMismatchError, ValueError):
        return False


def new_api_key() -> str:
    return "agt_" + secrets.token_urlsafe(32)


def api_key_prefix(key: str) -> str:
    return key[:API_KEY_PREFIX_LEN]


def mint_access_token(settings: AuthSettings, *, user_id: str, tenant_id: str, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "typ": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.access_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(settings: AuthSettings, token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def new_refresh_secret() -> tuple[uuid.UUID, str]:
    token_id = uuid.uuid4()
    secret = secrets.token_urlsafe(32)
    return token_id, f"{token_id}.{secret}"


def parse_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip()
