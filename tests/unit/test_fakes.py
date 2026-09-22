from aigateway.contracts import (
    AuthProvider,
    Evaluator,
    Guardrail,
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
