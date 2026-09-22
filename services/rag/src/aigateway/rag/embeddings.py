from __future__ import annotations

import hashlib
import math
import re

import httpx

from aigateway.config import RagSettings
from aigateway.contracts import RagUnavailableError
from aigateway.rag.models import EMBED_DIM
from aigateway.telemetry import get_logger

logger = get_logger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+")


def fixture_embedding(text: str) -> list[float]:
    tokens = _TOKEN.findall(text.lower())
    grams = list(tokens)
    grams.extend(f"{left}_{right}" for left, right in zip(tokens, tokens[1:], strict=False))
    vec = [0.0] * EMBED_DIM
    for gram in grams:
        digest = hashlib.sha256(gram.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % EMBED_DIM
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


async def embed_text(
    text: str,
    settings: RagSettings,
    *,
    client: httpx.AsyncClient,
) -> list[float]:
    if settings.embedding_mode != "live":
        return fixture_embedding(text)
    if not settings.embedding_api_key or not settings.embedding_model:
        raise RagUnavailableError("embedding key missing")
    try:
        response = await client.post(
            settings.embedding_api_url,
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
            json={
                "model": settings.embedding_model,
                "input": text[:8000],
                "dimensions": EMBED_DIM,
            },
            timeout=settings.rag_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        vector = ((data.get("data") or [{}])[0]).get("embedding")
        if not isinstance(vector, list) or len(vector) != EMBED_DIM:
            raise RagUnavailableError("embedding dimension mismatch")
        return [float(value) for value in vector]
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        logger.warning("embedding request failed")
        raise RagUnavailableError("embedding provider failed") from exc
