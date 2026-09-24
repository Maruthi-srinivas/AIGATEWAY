from __future__ import annotations

import json
from pathlib import Path

from aigateway.contracts import EvaluationCase


def load_golden() -> list[dict]:
    bundled = Path(__file__).with_name("hr.json")
    source = Path(__file__).resolve().parents[3] / "golden" / "hr.json"
    docker = Path("/app/services/evals/golden/hr.json")
    for path in (bundled, source, docker):
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return payload
    raise FileNotFoundError("golden set missing")


def case_from_row(
    case_id: str,
    *,
    faithfulness: float | None,
    context_recall: float | None,
    context_precision: float | None,
    answer_correctness: float | None,
    latency_ms: float | None,
    status: str,
) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        faithfulness=faithfulness,
        context_recall=context_recall,
        context_precision=context_precision,
        answer_correctness=answer_correctness,
        latency_ms=latency_ms,
        status=status,
    )
