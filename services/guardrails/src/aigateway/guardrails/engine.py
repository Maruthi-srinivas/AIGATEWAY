from __future__ import annotations

from typing import Literal

import httpx

from aigateway.config import GuardrailsSettings
from aigateway.contracts import (
    GuardrailCheckResult,
    GuardrailDecision,
    GuardrailPolicy,
    GuardrailsUnavailableError,
    GuardrailText,
)
from aigateway.guardrails.perspective import check_perspective
from aigateway.guardrails.rules import (
    apply_pii,
    check_fixture_moderation,
    check_jailbreak,
    check_prompt_injection,
    check_token_limit,
)


def _overall(decisions: list[GuardrailDecision]) -> Literal["allow", "redact", "block"]:
    if any(item.decision == "block" for item in decisions):
        return "block"
    if any(item.decision == "redact" for item in decisions):
        return "redact"
    return "allow"


async def evaluate(
    texts: list[GuardrailText],
    policy: GuardrailPolicy,
    settings: GuardrailsSettings,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> GuardrailCheckResult:
    working = list(texts)
    decisions: list[GuardrailDecision] = []
    if policy.prompt_injection:
        hit = check_prompt_injection(working)
        if hit:
            decisions.append(hit)
    if policy.jailbreak:
        hit = check_jailbreak(working)
        if hit:
            decisions.append(hit)
    if policy.token_limit:
        hit = check_token_limit(working, policy.max_input_chars)
        if hit:
            decisions.append(hit)
    if policy.pii:
        hit, working = apply_pii(working, policy.pii_action)
        if hit:
            decisions.append(hit)
    if policy.moderation:
        if settings.guardrails_mode == "live":
            if http_client is None:
                raise GuardrailsUnavailableError("moderation client missing")
            hit = await check_perspective(working, settings, client=http_client)
        else:
            hit = check_fixture_moderation(working)
        if hit:
            decisions.append(hit)
    return GuardrailCheckResult(
        decision=_overall(decisions),
        decisions=decisions,
        texts=working,
    )
