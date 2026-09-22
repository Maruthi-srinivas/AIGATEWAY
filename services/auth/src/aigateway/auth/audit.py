from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.auth.models import AuditLog
from aigateway.contracts import AuthContext
from aigateway.telemetry import correlation_id_var


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    resource: str,
    success: bool,
    status_code: int,
    tenant_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_key_prefix: str | None = None,
    ip: str | None = None,
    metadata: dict[str, Any] | None = None,
    context: AuthContext | None = None,
) -> None:
    if context is not None:
        tenant_id = tenant_id or uuid.UUID(context.tenant_id)
        actor_user_id = actor_user_id or uuid.UUID(context.user_id)
        actor_key_prefix = actor_key_prefix or context.key_prefix
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_key_prefix=actor_key_prefix,
            action=action,
            resource=resource,
            success=success,
            status_code=status_code,
            correlation_id=correlation_id_var.get(),
            ip=ip,
            metadata_json=metadata,
        )
    )
    await session.flush()
