from __future__ import annotations

import httpx

from aigateway.config import GuardrailsSettings
from aigateway.contracts import GuardrailDecision, GuardrailsUnavailableError, GuardrailText
from aigateway.telemetry import get_logger

logger = get_logger(__name__)

ATTRIBUTES = (
    "TOXICITY",
    "SEVERE_TOXICITY",
    "IDENTITY_ATTACK",
    "INSULT",
    "THREAT",
    "PROFANITY",
    "SEXUALLY_EXPLICIT",
)


async def check_perspective(
    texts: list[GuardrailText],
    settings: GuardrailsSettings,
    *,
    client: httpx.AsyncClient,
) -> GuardrailDecision | None:
    if not settings.guardrails_api_key:
        raise GuardrailsUnavailableError("moderation key missing")
    blob = " ".join(item.content for item in texts)
    if not blob.strip():
        return None
    url = settings.guardrails_api_url
    params = {"key": settings.guardrails_api_key}
    payload = {
        "comment": {"text": blob[:30000]},
        "requestedAttributes": {name: {} for name in ATTRIBUTES},
    }
    try:
        response = await client.post(
            url,
            params=params,
            json=payload,
            timeout=settings.guardrails_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("perspective request failed")
        raise GuardrailsUnavailableError("moderation provider failed") from exc
    scores = body.get("attributeScores") or {}
    threshold = settings.guardrails_moderation_threshold
    for name, data in scores.items():
        value = float(((data or {}).get("summaryScore") or {}).get("value") or 0)
        if value >= threshold:
            return GuardrailDecision(
                decision="block",
                rule_id="moderation",
                score=value,
                reason=f"perspective {name} above threshold",
            )
    return None
