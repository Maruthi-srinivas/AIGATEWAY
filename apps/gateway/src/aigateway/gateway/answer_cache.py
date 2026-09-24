from __future__ import annotations

import hashlib
import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from aigateway.telemetry import get_logger

logger = get_logger(__name__)


def normalize_query(query: str) -> str:
    return " ".join(query.lower().split())


def cache_key(tenant_id: str, role: str, policy_hash: str, query: str) -> str:
    digest = hashlib.sha256(normalize_query(query).encode("utf-8")).hexdigest()
    return f"ans:{tenant_id}:{role}:{policy_hash}:{digest}"


class AnswerCache:
    def __init__(self, redis: Redis | None) -> None:
        self._redis = redis

    async def get(self, key: str) -> dict[str, Any] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
        except RedisError:
            logger.warning("answer cache get failed")
            return None
        if not raw:
            return None
        payload = json.loads(raw)
        if isinstance(payload, dict) and "answer" in payload:
            return payload
        return None

    async def set(self, key: str, payload: dict[str, Any]) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, json.dumps(payload), ex=3600)
        except RedisError:
            logger.warning("answer cache set failed")

    async def invalidate_tenant(self, tenant_id: str) -> None:
        if self._redis is None:
            return
        try:
            async for key in self._redis.scan_iter(match=f"ans:{tenant_id}:*", count=100):
                await self._redis.delete(key)
        except RedisError:
            logger.warning("answer cache invalidate failed")
