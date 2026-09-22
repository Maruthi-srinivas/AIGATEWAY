from __future__ import annotations

import re

from aigateway.contracts import GuardrailDecision, GuardrailText

INJECTION_PHRASES = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "reveal the system prompt",
    "reveal your system prompt",
)

JAILBREAK_PHRASES = (
    "jailbreak",
    "do anything now",
    "dan mode",
)

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"agt_[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)password=\S+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)

TOXIC_FIXTURE = "toxic-fixture"


def _joined(texts: list[GuardrailText]) -> str:
    return " ".join(item.content for item in texts).lower()


def check_prompt_injection(texts: list[GuardrailText]) -> GuardrailDecision | None:
    blob = _joined(texts)
    for phrase in INJECTION_PHRASES:
        if phrase in blob:
            return GuardrailDecision(
                decision="block",
                rule_id="prompt_injection",
                score=1.0,
                reason="prompt injection pattern matched",
            )
    return None


def check_jailbreak(texts: list[GuardrailText]) -> GuardrailDecision | None:
    blob = _joined(texts)
    for phrase in JAILBREAK_PHRASES:
        if phrase in blob:
            return GuardrailDecision(
                decision="block",
                rule_id="jailbreak",
                score=1.0,
                reason="jailbreak pattern matched",
            )
    return None


def check_token_limit(texts: list[GuardrailText], max_input_chars: int) -> GuardrailDecision | None:
    for item in texts:
        if len(item.content) > max_input_chars:
            return GuardrailDecision(
                decision="block",
                rule_id="token_limit",
                score=1.0,
                reason="input exceeds tenant max_input_chars",
            )
    return None


def apply_pii(
    texts: list[GuardrailText], pii_action: str
) -> tuple[GuardrailDecision | None, list[GuardrailText]]:
    hit = False
    updated: list[GuardrailText] = []
    for item in texts:
        content = item.content
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                hit = True
                content = pattern.sub("[SECRET]", content)
        updated.append(GuardrailText(role=item.role, content=content))
    if not hit:
        return None, texts
    decision = GuardrailDecision(
        decision="block" if pii_action == "block" else "redact",
        rule_id="pii",
        score=1.0,
        reason="secret pattern matched",
    )
    if pii_action == "block":
        return decision, texts
    return decision, updated


def check_fixture_moderation(texts: list[GuardrailText]) -> GuardrailDecision | None:
    blob = _joined(texts)
    if TOXIC_FIXTURE in blob:
        return GuardrailDecision(
            decision="block",
            rule_id="moderation",
            score=1.0,
            reason="fixture moderation denylist",
        )
    return None
