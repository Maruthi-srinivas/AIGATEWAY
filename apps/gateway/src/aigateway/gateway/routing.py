from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from aigateway.contracts import AuthorizationError

CHEAP_MODEL = "fixture-cheap"
CAPABLE_MODEL = "fixture-capable"

MODEL_PROVIDER = {
    CHEAP_MODEL: "fixture-a",
    CAPABLE_MODEL: "fixture-b",
}
MODEL_PREFERENCE = {
    CHEAP_MODEL: "cheap",
    CAPABLE_MODEL: "capable",
}
MODEL_COST = {
    CHEAP_MODEL: 0.0001,
    CAPABLE_MODEL: 0.001,
}

route_var: ContextVar[Route | None] = ContextVar("llm_route", default=None)


@dataclass(frozen=True)
class Route:
    provider: str
    model: str
    preference: str
    estimated_cost: float


def select_route(allowlist: list[str], preference: str) -> Route:
    """Pick the first allowlisted model for the tenant preference. No failover."""
    if preference not in {"cheap", "capable"} or not allowlist:
        raise AuthorizationError("model not allowed")
    for model in allowlist:
        if MODEL_PREFERENCE.get(model) == preference:
            return Route(
                provider=MODEL_PROVIDER[model],
                model=model,
                preference=preference,
                estimated_cost=MODEL_COST[model],
            )
    raise AuthorizationError("model not allowed")
