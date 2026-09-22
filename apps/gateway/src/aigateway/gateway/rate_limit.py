from __future__ import annotations

import time
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from aigateway.config import GatewaySettings
from aigateway.contracts import AuthContext, RateLimitedError, RateLimiterUnavailableError

TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local data = redis.call("HMGET", key, "tokens", "ts")
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
local elapsed = math.max(0, now - ts) / 1000.0
tokens = math.min(capacity, tokens + elapsed * refill)
local allowed = 0
local retry_after = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  local missing = cost - tokens
  retry_after = math.max(1, math.ceil(missing / refill))
end
redis.call("HSET", key, "tokens", tokens, "ts", now)
redis.call("EXPIRE", key, 180)
return {allowed, math.floor(tokens), retry_after, capacity}
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_at: int

    def headers(self) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_at),
        }


class AllowAllRateLimiter:
    async def consume(self, ctx: AuthContext, *, tenant_id: str) -> RateLimitResult:
        _ = ctx, tenant_id
        now = int(time.time())
        return RateLimitResult(True, 60, 59, 0, now + 60)


class DeniedRateLimiter:
    async def consume(self, ctx: AuthContext, *, tenant_id: str) -> RateLimitResult:
        _ = ctx, tenant_id
        now = int(time.time())
        raise RateLimitedError(
            retry_after=1,
            limit=20,
            remaining=0,
            reset_at=now + 1,
        )


class UnavailableRateLimiter:
    async def consume(self, ctx: AuthContext, *, tenant_id: str) -> RateLimitResult:
        _ = ctx, tenant_id
        raise RateLimiterUnavailableError()


class RedisTokenBucket:
    def __init__(self, redis: Redis, settings: GatewaySettings) -> None:
        self._redis = redis
        self._settings = settings

    async def consume(self, ctx: AuthContext, *, tenant_id: str) -> RateLimitResult:
        now_ms = int(time.time() * 1000)
        buckets = [
            (
                f"rl:tenant:{tenant_id}",
                self._settings.rate_limit_tenant_per_minute,
                self._settings.rate_limit_tenant_per_minute * 2,
            )
        ]
        if ctx.auth_method == "api_key" and ctx.key_prefix:
            buckets.append(
                (
                    f"rl:key:{ctx.key_prefix}",
                    self._settings.rate_limit_api_key_per_minute,
                    self._settings.rate_limit_api_key_per_minute * 2,
                )
            )
        else:
            buckets.append(
                (
                    f"rl:user:{ctx.user_id}",
                    self._settings.rate_limit_user_per_minute,
                    self._settings.rate_limit_user_per_minute * 2,
                )
            )
        try:
            results = [await self._take(key, rate, burst, now_ms) for key, rate, burst in buckets]
        except RedisError as exc:
            raise RateLimiterUnavailableError() from exc
        denied = next((item for item in results if not item.allowed), None)
        if denied is not None:
            raise RateLimitedError(
                retry_after=denied.retry_after,
                limit=denied.limit,
                remaining=denied.remaining,
                reset_at=denied.reset_at,
            )
        tightest = min(results, key=lambda item: item.remaining)
        return tightest

    async def _take(self, key: str, rate: int, burst: int, now_ms: int) -> RateLimitResult:
        refill = rate / 60.0
        raw = await self._redis.eval(TOKEN_BUCKET_LUA, 1, key, burst, refill, now_ms, 1)
        allowed, remaining, retry_after, limit = (int(v) for v in raw)
        reset_at = int(time.time()) + max(retry_after, 60)
        return RateLimitResult(
            allowed=bool(allowed),
            limit=limit,
            remaining=remaining,
            retry_after=retry_after,
            reset_at=reset_at,
        )
