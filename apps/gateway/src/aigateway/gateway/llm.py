from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx

from aigateway.config import GatewaySettings
from aigateway.contracts import LlmUnavailableError
from aigateway.gateway.routing import CAPABLE_MODEL, CHEAP_MODEL, route_var
from aigateway.telemetry import get_logger

logger = get_logger(__name__)


class FixtureLLMClient:
    def __init__(self, delay_ms: float = 0) -> None:
        self.delay_ms = delay_ms

    def echo(self, messages: list[dict[str, str]]) -> str:
        for item in messages:
            content = item.get("content") or ""
            if "CONTEXT:" in content:
                sentences = _context_sentences(content)
                if sentences:
                    return " ".join(sentences)
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


class OpenAICompatLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        client: httpx.AsyncClient,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = client

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
    ) -> str:
        _ = stream
        if not self._api_key or not self._model:
            raise LlmUnavailableError("llm key missing")
        url = f"{self._base_url.rstrip('/')}/chat/completions"
        try:
            response = await self._client.post(
                url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            body = response.json()
            return body["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("llm generate failed")
            raise LlmUnavailableError() from exc

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        answer = await self.generate(messages)
        yield answer


def _context_sentences(content: str) -> list[str]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    sentences: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].startswith("[") and index + 1 < len(lines):
            excerpt = lines[index + 1][:240].strip()
            if excerpt and excerpt[-1] not in ".!?":
                excerpt = f"{excerpt}."
            if excerpt:
                sentences.append(excerpt)
            index += 2
            continue
        index += 1
    return sentences


class RoutingLLMClient:
    """Calls only the provider selected for this request. No failover."""

    def __init__(self, clients: dict[str, FixtureLLMClient | OpenAICompatLLMClient]) -> None:
        self._clients = clients

    def _client(self) -> FixtureLLMClient | OpenAICompatLLMClient:
        route = route_var.get()
        model = route.model if route is not None else CHEAP_MODEL
        client = self._clients.get(model)
        if client is None:
            raise LlmUnavailableError()
        return client

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
    ) -> str:
        return await self._client().generate(messages, stream=stream)

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        async for chunk in self._client().stream(messages):
            yield chunk


def build_llm_client(settings: GatewaySettings, http_client: httpx.AsyncClient | None = None):
    if settings.llm_mode == "live":
        if http_client is None:
            raise LlmUnavailableError("llm client missing")
        cheap = OpenAICompatLLMClient(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            client=http_client,
        )
        capable = OpenAICompatLLMClient(
            base_url=settings.provider_b_base_url,
            api_key=settings.provider_b_api_key,
            model=settings.provider_b_model,
            timeout=settings.llm_timeout_seconds,
            client=http_client,
        )
    else:
        cheap = FixtureLLMClient(settings.stub_stream_delay_ms)
        capable = FixtureLLMClient(settings.stub_stream_delay_ms)
    return RoutingLLMClient({CHEAP_MODEL: cheap, CAPABLE_MODEL: capable})
