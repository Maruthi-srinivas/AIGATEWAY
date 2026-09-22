from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.auth.models import ApiKey, Tenant, User
from aigateway.auth.security import (
    PLATFORM_ROLE,
    PLATFORM_SLUG,
    api_key_prefix,
    hash_secret,
)
from aigateway.config import AuthSettings
from aigateway.telemetry import get_logger

logger = get_logger(__name__)

SEED_USERS = (
    ("admin@platform.local", PLATFORM_SLUG, PLATFORM_ROLE, "Platform"),
    ("user@hr.local", "acme-hr", "app_user", "Acme HR"),
    ("user@eng.local", "acme-eng", "app_user", "Acme Engineering"),
    ("sec@hr.local", "acme-hr", "security_admin", "Acme HR"),
    ("view@eng.local", "acme-eng", "viewer", "Acme Engineering"),
)

SEED_TENANTS = (
    (PLATFORM_SLUG, "Platform"),
    ("acme-hr", "Acme HR"),
    ("acme-eng", "Acme Engineering"),
)


async def seed_if_needed(session: AsyncSession, settings: AuthSettings) -> None:
    if not settings.seed_enabled:
        return
    tenants: dict[str, Tenant] = {}
    for slug, name in SEED_TENANTS:
        result = await session.execute(select(Tenant).where(Tenant.slug == slug))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(slug=slug, name=name)
            session.add(tenant)
            await session.flush()
        tenants[slug] = tenant

    for email, slug, role, _name in SEED_USERS:
        result = await session.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none() is None:
            session.add(
                User(
                    tenant_id=tenants[slug].id,
                    email=email,
                    password_hash=hash_secret(settings.seed_password),
                    role=role,
                    is_active=True,
                )
            )

    await _seed_api_key(session, tenants["acme-hr"], "demo-hr", settings.seed_hr_api_key)
    await _seed_api_key(session, tenants["acme-eng"], "demo-eng", settings.seed_eng_api_key)
    await session.commit()
    logger.info("auth seed ensured")


async def _seed_api_key(session: AsyncSession, tenant: Tenant, name: str, key: str) -> None:
    prefix = api_key_prefix(key)
    result = await session.execute(select(ApiKey).where(ApiKey.prefix == prefix))
    if result.scalar_one_or_none() is not None:
        return
    if not secrets.compare_digest(prefix, api_key_prefix(key)):
        return
    session.add(
        ApiKey(
            tenant_id=tenant.id,
            user_id=None,
            name=name,
            prefix=prefix,
            key_hash=hash_secret(key),
            role="service_account",
        )
    )
