from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from aigateway.contracts.errors import AuthenticationError, GuardrailsUnavailableError
from aigateway.contracts.models import (
    AuthContext,
    EvaluationResult,
    GuardrailCheckResult,
    GuardrailDecision,
    GuardrailPolicy,
    GuardrailPolicyUpdate,
    GuardrailText,
    RetrievedChunk,
)


class FakeAuthProvider:
    def __init__(
        self,
        context: AuthContext | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.context = context or AuthContext(
            user_id="11111111-1111-1111-1111-111111111111",
            tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            role="app_user",
            roles=["app_user"],
            email="user@example.com",
            auth_method="jwt",
        )
        self.fail = fail

    async def authenticate(
        self,
        *,
        authorization: str | None = None,
        api_key: str | None = None,
    ) -> AuthContext:
        if self.fail or (not authorization and not api_key):
            raise AuthenticationError()
        return self.context


class FakeGuardrail:
    def __init__(
        self,
        *,
        unavailable: bool = False,
        result: GuardrailCheckResult | None = None,
    ) -> None:
        self.unavailable = unavailable
        self.result = result
        self.calls: list[dict] = []
        self.policies: dict[str, GuardrailPolicy] = {}

    async def check(
        self,
        text: str,
        context: AuthContext | None = None,
    ) -> GuardrailDecision:
        _ = text, context
        return GuardrailDecision(
            decision="allow",
            rule_id="fake.allow",
            score=1.0,
            reason="v1 fake",
        )

    async def check_input(
        self,
        *,
        tenant_id: str,
        texts: list[GuardrailText],
    ) -> GuardrailCheckResult:
        self.calls.append({"tenant_id": tenant_id, "texts": texts})
        if self.unavailable:
            raise GuardrailsUnavailableError()
        if self.result is not None:
            return self.result
        return GuardrailCheckResult(decision="allow", decisions=[], texts=list(texts))

    async def get_policy(self, tenant_id: str) -> GuardrailPolicy:
        return self.policies.get(tenant_id, GuardrailPolicy(tenant_id=tenant_id))

    async def patch_policy(self, tenant_id: str, update: GuardrailPolicyUpdate) -> GuardrailPolicy:
        current = await self.get_policy(tenant_id)
        updated = current.model_copy(update=update.model_dump(exclude_unset=True))
        self.policies[tenant_id] = updated
        return updated


class FakeRetriever:
    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        _ = tenant_id
        return [
            RetrievedChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                content=query,
                score=1.0,
            )
        ][:top_k]


class FakeLLMClient:
    def __init__(self, delay_ms: float = 0) -> None:
        self.delay_ms = delay_ms

    def echo(self, messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        return f"Stub: {last}"

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
    ) -> str:
        _ = stream
        return self.echo(messages)

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        words = self.echo(messages).split()
        for index, word in enumerate(words):
            if self.delay_ms:
                await asyncio.sleep(self.delay_ms / 1000)
            yield word if index == len(words) - 1 else f"{word} "


class FakeEvaluator:
    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> EvaluationResult:
        _ = question, answer, contexts
        return EvaluationResult(
            faithfulness=1.0,
            context_recall=1.0,
            context_precision=1.0,
            answer_correctness=1.0,
            latency_ms=1.0,
        )
