from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from aigateway.contracts.errors import (
    AuthenticationError,
    DocumentNotFoundError,
    GuardrailsUnavailableError,
    LlmUnavailableError,
    RagUnavailableError,
)
from aigateway.contracts.models import (
    AuthContext,
    DocumentDetail,
    DocumentIngest,
    DocumentList,
    DocumentOut,
    EvaluationResult,
    GuardrailCheckResult,
    GuardrailDecision,
    GuardrailPolicy,
    GuardrailPolicyUpdate,
    GuardrailText,
    RetrievalDebug,
    RetrievedChunk,
    RetrieveResult,
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
        output_result: GuardrailCheckResult | None = None,
        output_unavailable: bool = False,
    ) -> None:
        self.unavailable = unavailable
        self.result = result
        self.output_result = output_result
        self.output_unavailable = output_unavailable
        self.calls: list[dict] = []
        self.output_calls: list[dict] = []
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

    async def check_output(
        self,
        *,
        tenant_id: str,
        texts: list[GuardrailText],
    ) -> GuardrailCheckResult:
        self.output_calls.append({"tenant_id": tenant_id, "texts": texts})
        if self.unavailable or self.output_unavailable:
            raise GuardrailsUnavailableError()
        if self.output_result is not None:
            return self.output_result
        return GuardrailCheckResult(decision="allow", decisions=[], texts=list(texts))

    async def get_policy(self, tenant_id: str) -> GuardrailPolicy:
        return self.policies.get(tenant_id, GuardrailPolicy(tenant_id=tenant_id))

    async def patch_policy(self, tenant_id: str, update: GuardrailPolicyUpdate) -> GuardrailPolicy:
        current = await self.get_policy(tenant_id)
        updated = current.model_copy(update=update.model_dump(exclude_unset=True))
        self.policies[tenant_id] = updated
        return updated


class FakeRetriever:
    def __init__(
        self,
        *,
        unavailable: bool = False,
        chunks: list[RetrievedChunk] | None = None,
        debug: RetrievalDebug | None = None,
    ) -> None:
        self.unavailable = unavailable
        self.chunks = chunks
        self.debug = debug
        self.calls: list[dict] = []
        self.documents: dict[str, list[DocumentDetail]] = {}

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 8,
        *,
        role: str = "app_user",
        debug: bool = False,
    ) -> RetrieveResult:
        self.calls.append(
            {
                "query": query,
                "tenant_id": tenant_id,
                "top_k": top_k,
                "role": role,
                "debug": debug,
            }
        )
        if self.unavailable:
            raise RagUnavailableError()
        rows = list(self.chunks)[:top_k] if self.chunks is not None else []
        return RetrieveResult(chunks=rows, debug=self.debug if debug else None)

    async def ingest(self, tenant_id: str, body: DocumentIngest, created_by: str) -> DocumentOut:
        _ = created_by
        now = datetime.now(UTC)
        item = DocumentOut(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            title=body.title,
            classification=body.classification,
            acl=list(body.acl),
            chunk_count=1,
            created_at=now,
            updated_at=now,
        )
        self.documents.setdefault(tenant_id, []).append(
            DocumentDetail(**item.model_dump(), body=body.text)
        )
        return item

    async def list_documents(self, tenant_id: str, *, limit: int, offset: int) -> DocumentList:
        rows = self.documents.get(tenant_id, [])
        items = [DocumentOut(**row.model_dump(exclude={"body"})) for row in rows]
        return DocumentList(items=items[offset : offset + limit], offset=offset, limit=limit)

    async def get_document(self, tenant_id: str, document_id: str) -> DocumentDetail:
        for item in self.documents.get(tenant_id, []):
            if item.id == document_id:
                return item
        raise DocumentNotFoundError()

    async def delete_document(self, tenant_id: str, document_id: str) -> None:
        items = self.documents.get(tenant_id, [])
        kept = [item for item in items if item.id != document_id]
        if len(kept) == len(items):
            raise DocumentNotFoundError()
        self.documents[tenant_id] = kept


class FakeLLMClient:
    def __init__(self, delay_ms: float = 0, *, unavailable: bool = False) -> None:
        self.delay_ms = delay_ms
        self.unavailable = unavailable
        self.calls: list[list[dict[str, str]]] = []

    def echo(self, messages: list[dict[str, str]]) -> str:
        for item in messages:
            content = item.get("content") or ""
            if "CONTEXT:" in content:
                excerpt = _context_excerpt(content)
                return f"According to the documents: {excerpt}"
        last = messages[-1]["content"] if messages else ""
        return f"Stub: {last}"

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
    ) -> str:
        _ = stream
        self.calls.append(messages)
        if self.unavailable:
            raise LlmUnavailableError()
        return self.echo(messages)

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        words = self.echo(messages).split()
        for index, word in enumerate(words):
            if self.delay_ms:
                await asyncio.sleep(self.delay_ms / 1000)
            yield word if index == len(words) - 1 else f"{word} "


def _context_excerpt(content: str) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.startswith("[") and index + 1 < len(lines):
            return lines[index + 1][:240]
    return "context"


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
