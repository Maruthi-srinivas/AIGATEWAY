from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from aigateway.telemetry import get_logger, observe_session_cache

logger = get_logger(__name__)


class SessionCache:
    def __init__(self, redis: Redis | None, *, ttl_seconds: int, limit: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._limit = limit

    def key(self, tenant_id: str, conversation_id: str) -> str:
        return f"conv:{tenant_id}:{conversation_id}"

    async def get(self, tenant_id: str, conversation_id: str) -> list[dict[str, str]] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(self.key(tenant_id, conversation_id))
        except RedisError:
            logger.warning("session cache get failed", exc_info=True)
            observe_session_cache("error")
            return None
        if not raw:
            observe_session_cache("miss")
            return None
        payload: Any = json.loads(raw)
        if isinstance(payload, list):
            observe_session_cache("hit")
            return payload[-self._limit :]
        observe_session_cache("miss")
        return None

    async def set(
        self,
        tenant_id: str,
        conversation_id: str,
        messages: list[dict[str, str]],
    ) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(
                self.key(tenant_id, conversation_id),
                json.dumps(messages[-self._limit :]),
                ex=self._ttl,
            )
        except RedisError:
            logger.warning("session cache set failed", exc_info=True)
