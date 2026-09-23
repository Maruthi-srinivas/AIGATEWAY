from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from aigateway.contracts.models import (
    AuthContext,
    EvaluationResult,
    GuardrailCheckResult,
    GuardrailDecision,
    GuardrailText,
    RetrieveResult,
)


@runtime_checkable
class AuthProvider(Protocol):
    async def authenticate(
        self,
        *,
        authorization: str | None = None,
        api_key: str | None = None,
    ) -> AuthContext: ...


@runtime_checkable
class Guardrail(Protocol):
    async def check(
        self,
        text: str,
        context: AuthContext | None = None,
    ) -> GuardrailDecision: ...

    async def check_input(
        self,
        *,
        tenant_id: str,
        texts: list[GuardrailText],
    ) -> GuardrailCheckResult: ...

    async def check_output(
        self,
        *,
        tenant_id: str,
        texts: list[GuardrailText],
    ) -> GuardrailCheckResult: ...


@runtime_checkable
class Retriever(Protocol):
    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 8,
        *,
        role: str = "app_user",
        debug: bool = False,
    ) -> RetrieveResult: ...


@runtime_checkable
class LLMClient(Protocol):
    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
    ) -> str: ...

    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


@runtime_checkable
class Evaluator(Protocol):
    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> EvaluationResult: ...
