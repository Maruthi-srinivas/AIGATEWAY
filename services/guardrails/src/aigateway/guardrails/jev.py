from __future__ import annotations

from typing import Any, Literal

import httpx

from aigateway.config import GuardrailsSettings
from aigateway.contracts import GuardrailText, JevAssessment
from aigateway.telemetry import get_logger

logger = get_logger(__name__)

INPUT_QUESTIONS: dict[str, dict[str, Any]] = {
    "prompt_injection": {
        "type": "noul",
        "instructions": "Does this text attempt prompt injection or instruction override?",
    },
    "jailbreak": {
        "type": "noul",
        "instructions": "Does this text attempt a jailbreak or to disable safety rules?",
    },
    "toxicity": {
        "type": "noul",
        "instructions": "Is this text toxic, abusive, or hateful?",
    },
    "pii": {
        "type": "noul",
        "instructions": (
            "Does this text contain secrets, API keys, passwords, or other sensitive credentials?"
        ),
    },
    "risk": {
        "type": "score",
        "instructions": "How risky is allowing this request to reach a language model?",
        "criteria": ["Low", "Medium", "High"],
    },
    "route": {
        "type": "choice",
        "instructions": "Which handling path should software take?",
        "criteria": {
            "answer": "Safe to answer with the model",
            "refuse": "Should refuse without calling the model",
            "escalate": "Should escalate to a human",
        },
    },
}

OUTPUT_QUESTIONS: dict[str, dict[str, Any]] = {
    "toxicity": {
        "type": "noul",
        "instructions": "Is this assistant output toxic, abusive, or hateful?",
    },
    "pii": {
        "type": "noul",
        "instructions": (
            "Does this assistant output contain secrets, API keys, passwords, or credentials?"
        ),
    },
    "safety": {
        "type": "noul",
        "instructions": "Is this assistant output safe to show the user?",
    },
}

HIGH = 0.99
LOW = 0.05


def _blob(texts: list[GuardrailText]) -> str:
    return " ".join(item.content for item in texts)


def _noul(stage: Literal["input", "output"], question_id: str, value: float) -> JevAssessment:
    return JevAssessment(
        stage=stage,
        question_id=question_id,
        kind="noul",
        score=value,
    )


def _fixture_assessments(blob: str, stage: Literal["input", "output"]) -> list[JevAssessment]:
    if stage == "output":
        toxic = HIGH if "jev-toxic" in blob else LOW
        pii = HIGH if "jev-pii" in blob else LOW
        safety = LOW if toxic >= HIGH or pii >= HIGH else 0.95
        return [
            _noul(stage, "toxicity", toxic),
            _noul(stage, "pii", pii),
            _noul(stage, "safety", safety),
        ]
    injection = HIGH if "jev-injection" in blob else LOW
    jailbreak = HIGH if "jev-jailbreak" in blob else LOW
    toxic = HIGH if "jev-toxic" in blob else LOW
    pii = HIGH if "jev-pii" in blob else LOW
    high_risk = "jev-risk" in blob
    route = "refuse" if "jev-refuse" in blob else "answer"
    if high_risk:
        risk_score = 2.0
        risk_dist = {"0": 0.01, "1": 0.0, "2": HIGH}
    else:
        risk_score = 0.0
        risk_dist = {"0": 0.9, "1": 0.05, "2": LOW}
    refuse = route == "refuse"
    return [
        _noul(stage, "prompt_injection", injection),
        _noul(stage, "jailbreak", jailbreak),
        _noul(stage, "toxicity", toxic),
        _noul(stage, "pii", pii),
        JevAssessment(
            stage=stage,
            question_id="risk",
            kind="score",
            score=risk_score,
            confidence=HIGH if high_risk else 0.9,
            distribution=risk_dist,
        ),
        JevAssessment(
            stage=stage,
            question_id="route",
            kind="choice",
            choice=route,
            score=HIGH if refuse else 0.9,
            confidence=HIGH if refuse else 0.9,
            distribution={
                "answer": LOW if refuse else 0.9,
                "refuse": HIGH if refuse else LOW,
                "escalate": 0.05,
            },
        ),
    ]


def _parse_answers(
    answers: dict[str, Any],
    stage: Literal["input", "output"],
) -> list[JevAssessment]:
    assessments: list[JevAssessment] = []
    for question_id, payload in answers.items():
        if not isinstance(payload, dict):
            continue
        kind = payload.get("type")
        if kind == "noul":
            assessments.append(_noul(stage, question_id, float(payload.get("noul") or 0.0)))
        elif kind == "choice":
            probabilities = payload.get("probabilities") or {}
            dist = {str(key): float(value) for key, value in probabilities.items()}
            choice = payload.get("choice")
            assessments.append(
                JevAssessment(
                    stage=stage,
                    question_id=question_id,
                    kind="choice",
                    choice=str(choice) if choice is not None else None,
                    score=max(dist.values()) if dist else None,
                    confidence=(
                        float(payload["confidence"])
                        if payload.get("confidence") is not None
                        else None
                    ),
                    distribution=dist or None,
                )
            )
        elif kind == "score":
            probabilities = payload.get("probabilities") or {}
            dist = {str(key): float(value) for key, value in probabilities.items()}
            assessments.append(
                JevAssessment(
                    stage=stage,
                    question_id=question_id,
                    kind="score",
                    score=float(payload.get("score") or 0.0),
                    confidence=(
                        float(payload["confidence"])
                        if payload.get("confidence") is not None
                        else None
                    ),
                    distribution=dist or None,
                )
            )
    return assessments


async def assess(
    texts: list[GuardrailText],
    settings: GuardrailsSettings,
    *,
    stage: Literal["input", "output"],
    client: httpx.AsyncClient | None = None,
    tenant_id: str | None = None,
) -> list[JevAssessment]:
    blob = _blob(texts)
    questions = INPUT_QUESTIONS if stage == "input" else OUTPUT_QUESTIONS
    if not settings.jev_api_key:
        return _fixture_assessments(blob, stage)
    if not blob.strip():
        return []
    if client is None:
        logger.warning("jev client missing stage=%s tenant_id=%s", stage, tenant_id)
        return []
    payload = {
        "model": settings.jev_model,
        "state": blob[:30000],
        "questions": questions,
    }
    headers = {"Authorization": f"Bearer {settings.jev_api_key}"}
    try:
        response = await client.post(
            settings.jev_api_url,
            headers=headers,
            json=payload,
            timeout=settings.jev_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        logger.warning("jev request failed stage=%s tenant_id=%s", stage, tenant_id)
        return []
    answers = body.get("answers") if isinstance(body, dict) else None
    if not isinstance(answers, dict):
        logger.warning("jev response missing answers stage=%s tenant_id=%s", stage, tenant_id)
        return []
    return _parse_answers(answers, stage)
