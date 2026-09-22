from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.auth.models import ApiKey, User
from aigateway.auth.security import (
    api_key_prefix,
    decode_access_token,
    parse_bearer,
    verify_secret,
)
from aigateway.config import AuthSettings
from aigateway.contracts import AuthContext, AuthenticationError


async def resolve_identity(
    session: AsyncSession,
    settings: AuthSettings,
    *,
    authorization: str | None,
    api_key: str | None,
    touch_api_key: bool = True,
) -> AuthContext:
    if api_key:
        return await _from_api_key(session, api_key, touch=touch_api_key)
    token = parse_bearer(authorization)
    if token:
        return await _from_jwt(session, settings, token)
    raise AuthenticationError("missing credentials")


async def _from_jwt(session: AsyncSession, settings: AuthSettings, token: str) -> AuthContext:
    try:
        payload = decode_access_token(settings, token)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("invalid token") from exc
    if payload.get("typ") != "access":
        raise AuthenticationError("invalid token type")
    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("invalid token")
    user = await session.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise AuthenticationError("invalid token")
    return AuthContext(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role,
        roles=[user.role],
        email=user.email,
        auth_method="jwt",
    )


async def _from_api_key(session: AsyncSession, api_key: str, *, touch: bool) -> AuthContext:
    prefix = api_key_prefix(api_key)
    result = await session.execute(select(ApiKey).where(ApiKey.prefix == prefix))
    row = result.scalar_one_or_none()
    if row is None or row.revoked_at is not None or not verify_secret(row.key_hash, api_key):
        raise AuthenticationError("invalid api key")
    if touch:
        row.last_used_at = datetime.now(UTC)
    placeholder_user = row.user_id or row.id
    return AuthContext(
        user_id=str(placeholder_user),
        tenant_id=str(row.tenant_id),
        role=row.role,
        roles=[row.role],
        key_prefix=row.prefix,
        auth_method="api_key",
    )
