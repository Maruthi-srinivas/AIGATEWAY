from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from aigateway.config import GatewaySettings
from aigateway.telemetry import get_logger

logger = get_logger(__name__)

CheckFn = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class ReadinessStatus:
    postgres: bool
    redis: bool
    auth: bool
    guardrails: bool
    rag: bool

    @property
    def ok(self) -> bool:
        return self.postgres and self.redis and self.auth and self.guardrails and self.rag


async def default_check_postgres(dsn: str, timeout: float) -> bool:
    def _connect() -> None:
        import psycopg

        connect_timeout = max(1, int(timeout))
        with psycopg.connect(dsn, connect_timeout=connect_timeout) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")

    try:
        await asyncio.to_thread(_connect)
        return True
    except Exception:
        logger.warning("postgres readiness check failed", exc_info=True)
        return False


async def default_check_redis(url: str, timeout: float) -> bool:
    try:
        import redis.asyncio as redis

        client = redis.from_url(url, socket_connect_timeout=timeout)
        try:
            await asyncio.wait_for(client.ping(), timeout=timeout)
            return True
        finally:
            await client.aclose()
    except Exception:
        logger.warning("redis readiness check failed", exc_info=True)
        return False


async def default_check_http(base_url: str, timeout: float, name: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{base_url.rstrip('/')}/health")
            return response.status_code == 200
    except Exception:
        logger.warning("%s readiness check failed", name, exc_info=True)
        return False


class ReadinessChecker:
    def __init__(
        self,
        settings: GatewaySettings,
        *,
        check_postgres: CheckFn | None = None,
        check_redis: CheckFn | None = None,
        check_auth: CheckFn | None = None,
        check_guardrails: CheckFn | None = None,
        check_rag: CheckFn | None = None,
    ) -> None:
        self._settings = settings
        self._check_postgres = check_postgres
        self._check_redis = check_redis
        self._check_auth = check_auth
        self._check_guardrails = check_guardrails
        self._check_rag = check_rag

    async def check(self) -> ReadinessStatus:
        postgres_ok, redis_ok, auth_ok, guardrails_ok, rag_ok = await asyncio.gather(
            self._postgres(),
            self._redis(),
            self._auth(),
            self._guardrails(),
            self._rag(),
        )
        return ReadinessStatus(
            postgres=postgres_ok,
            redis=redis_ok,
            auth=auth_ok,
            guardrails=guardrails_ok,
            rag=rag_ok,
        )

    async def _postgres(self) -> bool:
        if self._check_postgres is not None:
            return await self._check_postgres()
        return await default_check_postgres(
            self._settings.postgres_dsn,
            self._settings.postgres_connect_timeout,
        )

    async def _redis(self) -> bool:
        if self._check_redis is not None:
            return await self._check_redis()
        return await default_check_redis(
            self._settings.redis_url,
            self._settings.redis_connect_timeout,
        )

    async def _auth(self) -> bool:
        if self._check_auth is not None:
            return await self._check_auth()
        return await default_check_http(
            self._settings.auth_base_url,
            self._settings.auth_timeout,
            "auth",
        )

    async def _guardrails(self) -> bool:
        if self._check_guardrails is not None:
            return await self._check_guardrails()
        return await default_check_http(
            self._settings.guardrails_base_url,
            self._settings.guardrails_timeout,
            "guardrails",
        )

    async def _rag(self) -> bool:
        if self._check_rag is not None:
            return await self._check_rag()
        return await default_check_http(
            self._settings.rag_base_url,
            self._settings.rag_timeout,
            "rag",
        )
