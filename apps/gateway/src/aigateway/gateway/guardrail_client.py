from __future__ import annotations

import httpx

from aigateway.config import GatewaySettings
from aigateway.contracts import (
    GuardrailCheckResult,
    GuardrailPolicy,
    GuardrailPolicyUpdate,
    GuardrailsUnavailableError,
    GuardrailText,
)
from aigateway.telemetry import correlation_id_var, get_logger

logger = get_logger(__name__)


class HttpGuardrailClient:
    def __init__(self, settings: GatewaySettings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"X-Internal-Token": self._settings.internal_auth_token}
        cid = correlation_id_var.get()
        if cid:
            headers["X-Correlation-ID"] = cid
        return headers

    def _url(self, path: str) -> str:
        return f"{self._settings.guardrails_base_url.rstrip('/')}{path}"

    async def check_input(
        self,
        *,
        tenant_id: str,
        texts: list[GuardrailText],
    ) -> GuardrailCheckResult:
        try:
            response = await self._client.post(
                self._url("/internal/v1/check"),
                headers=self._headers(),
                json={
                    "tenant_id": tenant_id,
                    "texts": [item.model_dump() for item in texts],
                },
                timeout=self._settings.guardrails_timeout,
            )
        except httpx.HTTPError as exc:
            logger.warning("guardrails check failed")
            raise GuardrailsUnavailableError() from exc
        if response.status_code >= 500 or response.status_code == 401:
            raise GuardrailsUnavailableError()
        response.raise_for_status()
        return GuardrailCheckResult.model_validate(response.json())

    async def get_policy(self, tenant_id: str) -> GuardrailPolicy:
        try:
            response = await self._client.get(
                self._url("/internal/v1/policy"),
                headers=self._headers(),
                params={"tenant_id": tenant_id},
                timeout=self._settings.guardrails_timeout,
            )
        except httpx.HTTPError as exc:
            raise GuardrailsUnavailableError() from exc
        if response.status_code >= 500 or response.status_code == 401:
            raise GuardrailsUnavailableError()
        response.raise_for_status()
        return GuardrailPolicy.model_validate(response.json())

    async def patch_policy(self, tenant_id: str, update: GuardrailPolicyUpdate) -> GuardrailPolicy:
        try:
            response = await self._client.patch(
                self._url("/internal/v1/policy"),
                headers=self._headers(),
                params={"tenant_id": tenant_id},
                json=update.model_dump(exclude_unset=True),
                timeout=self._settings.guardrails_timeout,
            )
        except httpx.HTTPError as exc:
            raise GuardrailsUnavailableError() from exc
        if response.status_code >= 500 or response.status_code == 401:
            raise GuardrailsUnavailableError()
        response.raise_for_status()
        return GuardrailPolicy.model_validate(response.json())
