from __future__ import annotations

import json
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from aigateway.contracts import (
    AuthorizationError,
    ChatRequest,
    EvalsUnavailableError,
    EvaluateRequest,
    EvaluationCase,
    EvaluationReport,
)
from aigateway.gateway.chat import handle_chat
from aigateway.gateway.deps import effective_tenant_id, require_auth
from aigateway.telemetry import correlation_id_var

EVALUATE_ROLES = frozenset({"security_admin", "platform_admin"})


async def handle_evaluate(request: Request, body: EvaluateRequest) -> EvaluationReport:
    ctx = await require_auth(request)
    if ctx.role not in EVALUATE_ROLES:
        raise AuthorizationError("evaluation is forbidden")
    tenant_id = effective_tenant_id(ctx, body.tenant_id)
    cases = await request.app.state.evals_client.golden()
    run_id = str(uuid.uuid4())
    stored: list[EvaluationCase] = []
    for case in cases:
        started = time.perf_counter()
        chat_body = ChatRequest(message=case["question"])
        if ctx.role == "platform_admin" and body.tenant_id:
            chat_body = ChatRequest(message=case["question"], tenant_id=body.tenant_id)
        response = await handle_chat(request, chat_body)
        if not isinstance(response, JSONResponse):
            raise EvalsUnavailableError("evaluation case did not complete")
        payload = json.loads(response.body)
        latency_ms = (time.perf_counter() - started) * 1000
        chunks = list(getattr(request.state, "eval_chunks", []))
        scored = await request.app.state.evals_client.store(
            {
                "tenant_id": tenant_id,
                "correlation_id": correlation_id_var.get(),
                "run_id": run_id,
                "case_id": case["id"],
                "answer": payload.get("answer", ""),
                "chunks": chunks,
                "expected_terms": list(case.get("expected_terms") or []),
                "groundedness": payload.get("groundedness"),
                "latency_ms": latency_ms,
                "status": "scored",
                "feedback": body.feedback,
            }
        )
        stored.append(scored)
    values = [item.faithfulness for item in stored if item.faithfulness is not None]
    mean = sum(values) / len(values) if values else None
    return EvaluationReport(
        run_id=run_id,
        met_target=mean is not None and mean >= 0.95,
        mean_faithfulness=mean,
        cases=stored,
    )
