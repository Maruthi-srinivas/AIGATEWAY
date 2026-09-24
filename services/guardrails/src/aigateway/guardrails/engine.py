from __future__ import annotations

import hashlib
import json
from typing import Literal

import httpx

from aigateway.config import GuardrailsSettings
from aigateway.contracts import (
    GuardrailCheckResult,
    GuardrailDecision,
    GuardrailPolicy,
    GuardrailsUnavailableError,
    GuardrailText,
    JevAssessment,
)
from aigateway.guardrails.jev import assess
from aigateway.guardrails.perspective import check_perspective
from aigateway.guardrails.rules import (
    apply_pii,
    check_fixture_moderation,
    check_jailbreak,
    check_prompt_injection,
    check_token_limit,
)

INPUT_JEV_RULES: dict[str, tuple[str, str]] = {
    "prompt_injection": ("jev_prompt_injection", "jev_injection_threshold"),
    "jailbreak": ("jev_jailbreak", "jev_jailbreak_threshold"),
    "toxicity": ("jev_toxicity", "jev_toxicity_threshold"),
    "pii": ("jev_pii", "jev_pii_threshold"),
    "risk": ("jev_risk", "jev_risk_threshold"),
}

OUTPUT_JEV_RULES: dict[str, tuple[str, str]] = {
    "toxicity": ("jev_output_toxicity", "jev_output_toxicity_threshold"),
    "pii": ("jev_output_pii", "jev_output_pii_threshold"),
}


def policy_hash(policy: GuardrailPolicy) -> str:
    raw = json.dumps(policy.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _overall(decisions: list[GuardrailDecision]) -> Literal["allow", "redact", "block"]:
    if any(item.decision == "block" for item in decisions):
        return "block"
    if any(item.decision == "redact" for item in decisions):
        return "redact"
    return "allow"


def _probability(assessment: JevAssessment) -> float | None:
    if assessment.kind == "noul":
        return assessment.score
    if assessment.kind == "score":
        if assessment.distribution and "2" in assessment.distribution:
            return float(assessment.distribution["2"])
        if assessment.score is None:
            return None
        return min(max(assessment.score / 2.0, 0.0), 1.0)
    return None


def _jev_decisions(
    assessments: list[JevAssessment],
    policy: GuardrailPolicy,
    mapping: dict[str, tuple[str, str]],
    *,
    pii_blocks: bool,
) -> list[GuardrailDecision]:
    decisions: list[GuardrailDecision] = []
    for item in assessments:
        spec = mapping.get(item.question_id)
        if spec is None:
            continue
        rule_id, threshold_attr = spec
        value = _probability(item)
        if value is None:
            continue
        threshold = float(getattr(policy, threshold_attr))
        if value < threshold:
            continue
        if item.question_id == "pii" and not pii_blocks:
            continue
        decisions.append(
            GuardrailDecision(
                decision="block",
                rule_id=rule_id,
                score=value,
                reason=f"jev {item.question_id} above threshold",
            )
        )
    return decisions


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
    assessments: list[JevAssessment] = []
    if policy.jev_enabled:
        assessments = await assess(
            working,
            settings,
            stage="input",
            client=http_client,
            tenant_id=policy.tenant_id,
        )
        decisions.extend(
            _jev_decisions(
                assessments,
                policy,
                INPUT_JEV_RULES,
                pii_blocks=policy.pii_action == "block",
            )
        )
    return GuardrailCheckResult(
        decision=_overall(decisions),
        decisions=decisions,
        texts=working,
        assessments=assessments,
        policy_hash=policy_hash(policy),
    )


async def evaluate_output(
    texts: list[GuardrailText],
    policy: GuardrailPolicy,
    settings: GuardrailsSettings,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> GuardrailCheckResult:
    assessments: list[JevAssessment] = []
    decisions: list[GuardrailDecision] = []
    if policy.jev_enabled:
        assessments = await assess(
            texts,
            settings,
            stage="output",
            client=http_client,
            tenant_id=policy.tenant_id,
        )
        decisions = _jev_decisions(
            assessments,
            policy,
            OUTPUT_JEV_RULES,
            pii_blocks=True,
        )
    return GuardrailCheckResult(
        decision=_overall(decisions),
        decisions=decisions,
        texts=list(texts),
        assessments=assessments,
        policy_hash=policy_hash(policy),
    )
