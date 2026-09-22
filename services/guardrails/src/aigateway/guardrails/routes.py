from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.config import GuardrailsSettings
from aigateway.contracts import (
    AuthenticationError,
    GuardrailCheckResult,
    GuardrailPolicy,
    GuardrailPolicyUpdate,
    GuardrailText,
)
from aigateway.guardrails.db import get_session
from aigateway.guardrails.engine import evaluate, evaluate_output
from aigateway.guardrails.policy import get_policy, patch_policy
from aigateway.telemetry import get_logger, tenant_id_var

logger = get_logger(__name__)

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class CheckRequest(BaseModel):
    tenant_id: str
    texts: list[GuardrailText] = Field(default_factory=list)


def require_internal(request: Request, settings: GuardrailsSettings) -> None:
    provided = request.headers.get("x-internal-token", "")
    if not secrets.compare_digest(provided, settings.internal_auth_token):
        raise AuthenticationError("invalid internal token")


def get_settings(request: Request) -> GuardrailsSettings:
    return request.app.state.settings


@router.post("/check")
async def check(
    body: CheckRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: GuardrailsSettings = Depends(get_settings),
) -> GuardrailCheckResult:
    require_internal(request, settings)
    tenant_token = tenant_id_var.set(body.tenant_id)
    try:
        policy = await get_policy(session, body.tenant_id)
        result = await evaluate(
            body.texts,
            policy,
            settings,
            http_client=request.app.state.http_client,
        )
    finally:
        tenant_id_var.reset(tenant_token)
    logger.info(
        "guardrail check decision=%s rules=%s tenant_id=%s",
        result.decision,
        [item.rule_id for item in result.decisions],
        body.tenant_id,
    )
    return result


@router.post("/check-output")
async def check_output(
    body: CheckRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: GuardrailsSettings = Depends(get_settings),
) -> GuardrailCheckResult:
    require_internal(request, settings)
    tenant_token = tenant_id_var.set(body.tenant_id)
    try:
        policy = await get_policy(session, body.tenant_id)
        result = await evaluate_output(
            body.texts,
            policy,
            settings,
            http_client=request.app.state.http_client,
        )
    finally:
        tenant_id_var.reset(tenant_token)
    logger.info(
        "guardrail output decision=%s rules=%s tenant_id=%s",
        result.decision,
        [item.rule_id for item in result.decisions],
        body.tenant_id,
    )
    return result


@router.get("/policy")
async def read_policy(
    request: Request,
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
    settings: GuardrailsSettings = Depends(get_settings),
) -> GuardrailPolicy:
    require_internal(request, settings)
    return await get_policy(session, tenant_id)


@router.patch("/policy")
async def update_policy(
    request: Request,
    tenant_id: str,
    body: GuardrailPolicyUpdate,
    session: AsyncSession = Depends(get_session),
    settings: GuardrailsSettings = Depends(get_settings),
) -> GuardrailPolicy:
    require_internal(request, settings)
    return await patch_policy(session, tenant_id, body)
