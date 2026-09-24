from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.auth.audit import select_audit, write_audit
from aigateway.auth.db import get_session
from aigateway.auth.deps import get_auth_context, get_settings, tenant_scope
from aigateway.auth.models import ApiKey, RefreshToken, User
from aigateway.auth.schemas import (
    ApiKeyCreated,
    AuditOut,
    CreateApiKeyRequest,
    LogoutRequest,
    TokenResponse,
    UserOut,
)
from aigateway.auth.security import (
    api_key_prefix,
    hash_secret,
    mint_access_token,
    new_api_key,
    new_refresh_secret,
    verify_secret,
)
from aigateway.config import AuthSettings
from aigateway.contracts import (
    AuthContext,
    AuthenticationError,
    AuthorizationError,
    LoginRequest,
    RefreshRequest,
)

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _issue_tokens(
    session: AsyncSession,
    settings: AuthSettings,
    user: User,
) -> TokenResponse:
    access = mint_access_token(
        settings,
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role,
    )
    token_id, refresh_plain = new_refresh_secret()
    session.add(
        RefreshToken(
            id=token_id,
            user_id=user.id,
            token_hash=hash_secret(refresh_plain),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_ttl_seconds),
        )
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh_plain,
        expires_in=settings.access_ttl_seconds,
        user=UserOut.model_validate(user),
    )


@router.post("/v1/auth/login", tags=["auth"])
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: AuthSettings = Depends(get_settings),
) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not user.password_hash
        or not verify_secret(user.password_hash, body.password)
    ):
        await write_audit(
            session,
            action="auth.login",
            resource="/v1/auth/login",
            success=False,
            status_code=401,
            ip=_client_ip(request),
            metadata={"email": body.email},
        )
        await session.commit()
        raise AuthenticationError("invalid credentials")
    tokens = await _issue_tokens(session, settings, user)
    await write_audit(
        session,
        action="auth.login",
        resource="/v1/auth/login",
        success=True,
        status_code=200,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        ip=_client_ip(request),
    )
    await session.commit()
    return tokens


@router.post("/v1/auth/refresh", tags=["auth"])
async def refresh(
    body: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: AuthSettings = Depends(get_settings),
) -> TokenResponse:
    token_id_str, _, _rest = body.refresh_token.partition(".")
    try:
        token_id = uuid.UUID(token_id_str)
    except ValueError as exc:
        raise AuthenticationError("invalid refresh token") from exc
    row = await session.get(RefreshToken, token_id)
    now = datetime.now(UTC)
    if (
        row is None
        or row.revoked_at is not None
        or row.expires_at <= now
        or not verify_secret(row.token_hash, body.refresh_token)
    ):
        await write_audit(
            session,
            action="auth.refresh",
            resource="/v1/auth/refresh",
            success=False,
            status_code=401,
            ip=_client_ip(request),
        )
        await session.commit()
        raise AuthenticationError("invalid refresh token")
    row.revoked_at = now
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        await session.commit()
        raise AuthenticationError("invalid refresh token")
    tokens = await _issue_tokens(session, settings, user)
    await write_audit(
        session,
        action="auth.refresh",
        resource="/v1/auth/refresh",
        success=True,
        status_code=200,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        ip=_client_ip(request),
    )
    await session.commit()
    return tokens


@router.post("/v1/auth/logout", tags=["auth"])
async def logout(
    body: LogoutRequest,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if body.refresh_token:
        token_id_str, _, _rest = body.refresh_token.partition(".")
        try:
            token_id = uuid.UUID(token_id_str)
        except ValueError as exc:
            raise AuthenticationError("invalid refresh token") from exc
        row = await session.get(RefreshToken, token_id)
        if row is not None and str(row.user_id) == ctx.user_id:
            row.revoked_at = datetime.now(UTC)
    await write_audit(
        session,
        action="auth.logout",
        resource="/v1/auth/logout",
        success=True,
        status_code=200,
        context=ctx,
        ip=_client_ip(request),
    )
    await session.commit()
    return {"status": "ok"}


@router.get("/v1/me", tags=["auth"])
async def me(ctx: AuthContext = Depends(get_auth_context)) -> dict:
    return {
        "user_id": ctx.user_id,
        "tenant_id": ctx.tenant_id,
        "role": ctx.role,
        "roles": ctx.roles,
        "email": ctx.email,
        "auth_method": ctx.auth_method,
    }


@router.post("/v1/me/api-keys", tags=["auth"])
async def create_my_api_key(
    body: CreateApiKeyRequest,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreated:
    if ctx.role in {"viewer", "service_account"}:
        raise AuthorizationError()
    key = new_api_key()
    prefix = api_key_prefix(key)
    row = ApiKey(
        tenant_id=uuid.UUID(ctx.tenant_id),
        user_id=uuid.UUID(ctx.user_id) if ctx.auth_method == "jwt" else None,
        name=body.name,
        prefix=prefix,
        key_hash=hash_secret(key),
        role="app_user",
    )
    session.add(row)
    await session.flush()
    await write_audit(
        session,
        action="apikey.create",
        resource=f"/v1/me/api-keys/{row.id}",
        success=True,
        status_code=200,
        context=ctx,
        ip=_client_ip(request),
    )
    await session.commit()
    return ApiKeyCreated(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        key=key,
        role=row.role,
        tenant_id=row.tenant_id,
    )


@router.get("/v1/audit", tags=["auth"])
async def list_audit(
    request: Request,
    tenant_id: str | None = None,
    correlation_id: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> list[AuditOut]:
    try:
        scoped = tenant_scope(ctx, tenant_id)
    except AuthorizationError:
        await write_audit(
            session,
            action="audit.read",
            resource="/v1/audit",
            success=False,
            status_code=403,
            context=ctx,
            ip=_client_ip(request),
            metadata={"requested_tenant_id": tenant_id},
        )
        await session.commit()
        raise
    result = await session.execute(select_audit(scoped, correlation_id))
    return [AuditOut.model_validate(row) for row in result.scalars()]
