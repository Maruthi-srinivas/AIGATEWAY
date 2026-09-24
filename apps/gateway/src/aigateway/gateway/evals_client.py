from __future__ import annotations

import httpx

from aigateway.config import GatewaySettings
from aigateway.contracts import EvalsUnavailableError, EvaluationCase
from aigateway.telemetry import correlation_id_var, get_logger

logger = get_logger(__name__)


class HttpEvalsClient:
    def __init__(self, settings: GatewaySettings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"X-Internal-Token": self._settings.internal_auth_token}
        cid = correlation_id_var.get()
        if cid:
            headers["X-Correlation-ID"] = cid
        return headers

    async def golden(self) -> list[dict]:
        try:
            response = await self._client.get(
                f"{self._settings.evals_base_url.rstrip('/')}/internal/v1/golden",
                headers=self._headers(),
                timeout=self._settings.evals_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise EvalsUnavailableError() from exc
        if response.status_code >= 500 or response.status_code == 401:
            raise EvalsUnavailableError()
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise EvalsUnavailableError()
        return payload

    async def store(self, body: dict) -> EvaluationCase:
        try:
            response = await self._client.post(
                f"{self._settings.evals_base_url.rstrip('/')}/internal/v1/evaluations",
                headers=self._headers(),
                json=body,
                timeout=self._settings.evals_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise EvalsUnavailableError() from exc
        if response.status_code >= 500 or response.status_code == 401:
            raise EvalsUnavailableError()
        response.raise_for_status()
        return EvaluationCase.model_validate(response.json())


class NullEvalsClient:
    async def golden(self) -> list[dict]:
        raise EvalsUnavailableError()

    async def store(self, body: dict) -> EvaluationCase:
        _ = body
        return EvaluationCase(case_id="skipped", faithfulness=None)
