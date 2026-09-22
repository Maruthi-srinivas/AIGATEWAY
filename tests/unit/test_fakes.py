from aigateway.contracts import (
    AuthProvider,
    Evaluator,
    Guardrail,
    GuardrailText,
    LLMClient,
    Retriever,
)
from aigateway.testing import (
    FakeAuthProvider,
    FakeEvaluator,
    FakeGuardrail,
    FakeLLMClient,
    FakeRetriever,
)


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(FakeAuthProvider(), AuthProvider)
    assert isinstance(FakeGuardrail(), Guardrail)
    assert isinstance(FakeRetriever(), Retriever)
    assert isinstance(FakeLLMClient(), LLMClient)
    assert isinstance(FakeEvaluator(), Evaluator)


async def test_fake_llm_echoes_stub() -> None:
    client = FakeLLMClient()
    messages = [{"role": "user", "content": "hello"}]
    assert await client.generate(messages) == "Stub: hello"
    chunks = [part async for part in client.stream(messages)]
    assert "".join(chunks) == "Stub: hello"


async def test_fake_llm_echoes_grounded_context() -> None:
    client = FakeLLMClient()
    messages = [
        {
            "role": "system",
            "content": (
                "CONTEXT:\n[1] document_id=d1 chunk_id=c1\nAcme HR paid time off is twenty days."
            ),
        },
        {"role": "user", "content": "how much pto?"},
    ]
    answer = await client.generate(messages)
    assert answer.startswith("According to the documents:")
    assert "twenty days" in answer


async def test_fake_guardrail_allows_by_default() -> None:
    guardrail = FakeGuardrail()
    texts = [GuardrailText(role="user", content="hello")]
    result = await guardrail.check_input(tenant_id="t1", texts=texts)
    assert result.decision == "allow"
    assert result.texts == texts
    output = await guardrail.check_output(tenant_id="t1", texts=texts)
    assert output.decision == "allow"
