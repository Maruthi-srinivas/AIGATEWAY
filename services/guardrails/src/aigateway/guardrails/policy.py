from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.contracts import GuardrailPolicy, GuardrailPolicyUpdate
from aigateway.guardrails.models import TenantPolicy

DEFAULT_POLICY = GuardrailPolicy(
    tenant_id="00000000-0000-0000-0000-000000000000",
    prompt_injection=True,
    jailbreak=True,
    moderation=True,
    token_limit=True,
    pii=True,
    pii_action="redact",
    max_input_chars=4000,
)


def defaults_for(tenant_id: str) -> GuardrailPolicy:
    return DEFAULT_POLICY.model_copy(update={"tenant_id": tenant_id})


def _to_policy(row: TenantPolicy) -> GuardrailPolicy:
    return GuardrailPolicy(
        tenant_id=str(row.tenant_id),
        prompt_injection=row.prompt_injection,
        jailbreak=row.jailbreak,
        moderation=row.moderation,
        token_limit=row.token_limit,
        pii=row.pii,
        pii_action=row.pii_action,  # type: ignore[arg-type]
        max_input_chars=row.max_input_chars,
        jev_enabled=row.jev_enabled,
        jev_injection_threshold=row.jev_injection_threshold,
        jev_jailbreak_threshold=row.jev_jailbreak_threshold,
        jev_toxicity_threshold=row.jev_toxicity_threshold,
        jev_pii_threshold=row.jev_pii_threshold,
        jev_risk_threshold=row.jev_risk_threshold,
        jev_output_toxicity_threshold=row.jev_output_toxicity_threshold,
        jev_output_pii_threshold=row.jev_output_pii_threshold,
    )


async def get_policy(session: AsyncSession, tenant_id: str) -> GuardrailPolicy:
    row = await session.get(TenantPolicy, uuid.UUID(tenant_id))
    if row is None:
        return defaults_for(tenant_id)
    return _to_policy(row)


async def patch_policy(
    session: AsyncSession,
    tenant_id: str,
    update: GuardrailPolicyUpdate,
) -> GuardrailPolicy:
    tid = uuid.UUID(tenant_id)
    row = await session.get(TenantPolicy, tid)
    if row is None:
        current = defaults_for(tenant_id)
        row = TenantPolicy(
            tenant_id=tid,
            prompt_injection=current.prompt_injection,
            jailbreak=current.jailbreak,
            moderation=current.moderation,
            token_limit=current.token_limit,
            pii=current.pii,
            pii_action=current.pii_action,
            max_input_chars=current.max_input_chars,
            jev_enabled=current.jev_enabled,
            jev_injection_threshold=current.jev_injection_threshold,
            jev_jailbreak_threshold=current.jev_jailbreak_threshold,
            jev_toxicity_threshold=current.jev_toxicity_threshold,
            jev_pii_threshold=current.jev_pii_threshold,
            jev_risk_threshold=current.jev_risk_threshold,
            jev_output_toxicity_threshold=current.jev_output_toxicity_threshold,
            jev_output_pii_threshold=current.jev_output_pii_threshold,
        )
        session.add(row)
    data = update.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return _to_policy(row)
