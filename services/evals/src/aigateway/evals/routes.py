from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.config import EvalsSettings
from aigateway.contracts import AuthenticationError, EvaluationCase
from aigateway.evals.db import get_session
from aigateway.evals.golden import load_golden
from aigateway.evals.models import EvaluationRow
from aigateway.evals.score import score_answer
from aigateway.telemetry import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class ScoreRequest(BaseModel):
    tenant_id: str
    correlation_id: str | None = None
    run_id: str | None = None
    case_id: str | None = None
    answer: str = ""
    chunks: list[str] = Field(default_factory=list)
    expected_terms: list[str] = Field(default_factory=list)
    groundedness: float | None = None
    latency_ms: float | None = None
    status: str = "scored"
    feedback: str | None = None


def require_internal(request: Request, settings: EvalsSettings) -> None:
    provided = request.headers.get("x-internal-token", "")
    try:
        ok = secrets.compare_digest(provided, settings.internal_auth_token)
    except ValueError:
        ok = False
    if not ok:
        raise AuthenticationError("invalid internal token")


def get_settings(request: Request) -> EvalsSettings:
    return request.app.state.settings


@router.get("/golden")
async def golden(
    request: Request,
    settings: EvalsSettings = Depends(get_settings),
) -> list[dict]:
    require_internal(request, settings)
    cases = []
    for item in load_golden():
        cases.append(
            {
                "id": item["id"],
                "question": item["question"],
                "expected_terms": list(item.get("expected_terms") or []),
            }
        )
    return cases


@router.post("/evaluations", response_model=EvaluationCase)
async def store_evaluation(
    body: ScoreRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: EvalsSettings = Depends(get_settings),
) -> EvaluationCase:
    require_internal(request, settings)
    faithfulness, recall, precision, correctness = score_answer(
        answer=body.answer,
        chunks=body.chunks,
        expected_terms=body.expected_terms,
        groundedness=body.groundedness,
    )
    status = body.status
    if faithfulness is not None and faithfulness < 0.5 and body.chunks:
        status = "review"
    row = EvaluationRow(
        tenant_id=uuid.UUID(body.tenant_id),
        correlation_id=body.correlation_id,
        run_id=uuid.UUID(body.run_id) if body.run_id else None,
        case_id=body.case_id,
        faithfulness=faithfulness,
        context_recall=recall,
        context_precision=precision,
        answer_correctness=correctness,
        latency_ms=body.latency_ms,
        status=status,
        feedback=body.feedback,
    )
    session.add(row)
    await session.commit()
    logger.info(
        "evaluation stored status=%s case_id=%s tenant_id=%s",
        status,
        body.case_id,
        body.tenant_id,
    )
    return EvaluationCase(
        case_id=body.case_id or str(row.id),
        faithfulness=faithfulness,
        context_recall=recall,
        context_precision=precision,
        answer_correctness=correctness,
        latency_ms=body.latency_ms,
        status=status,
    )


@router.get("/evaluations/{run_id}", response_model=list[EvaluationCase])
async def list_run(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: EvalsSettings = Depends(get_settings),
) -> list[EvaluationCase]:
    require_internal(request, settings)
    result = await session.execute(
        select(EvaluationRow)
        .where(EvaluationRow.run_id == uuid.UUID(run_id))
        .order_by(EvaluationRow.created_at.asc())
    )
    return [
        EvaluationCase(
            case_id=row.case_id or str(row.id),
            faithfulness=row.faithfulness,
            context_recall=row.context_recall,
            context_precision=row.context_precision,
            answer_correctness=row.answer_correctness,
            latency_ms=row.latency_ms,
            status=row.status,
        )
        for row in result.scalars()
    ]
