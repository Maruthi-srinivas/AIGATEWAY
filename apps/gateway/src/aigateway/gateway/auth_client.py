from __future__ import annotations

from collections.abc import Mapping

import httpx
from fastapi import Request, Response

from aigateway.config import GatewaySettings
from aigateway.contracts import AuthContext, AuthenticationError
from aigateway.telemetry import correlation_id_var, get_logger

logger = get_logger(__name__)

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "host",
}


class HttpAuthClient:
    def __init__(self, settings: GatewaySettings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def authenticate(
        self,
        *,
        authorization: str | None = None,
        api_key: str | None = None,
    ) -> AuthContext:
        try:
            response = await self._client.post(
                f"{self._settings.auth_base_url.rstrip('/')}/internal/v1/introspect",
                headers={"X-Internal-Token": self._settings.internal_auth_token},
                json={"authorization": authorization, "api_key": api_key},
                timeout=self._settings.auth_timeout,
            )
        except httpx.HTTPError as exc:
            logger.warning("auth introspect failed", exc_info=True)
            raise AuthenticationError("auth unavailable") from exc
        if response.status_code == 401:
            body = response.json() if response.content else {}
            raise AuthenticationError(detail=body.get("detail", "unauthenticated"))
        response.raise_for_status()
        return AuthContext.model_validate(response.json())

    async def write_audit(self, payload: dict) -> None:
        headers = {"X-Internal-Token": self._settings.internal_auth_token}
        cid = correlation_id_var.get()
        if cid:
            headers["X-Correlation-ID"] = cid
        try:
            await self._client.post(
                f"{self._settings.auth_base_url.rstrip('/')}/internal/v1/audit",
                headers=headers,
                json=payload,
                timeout=self._settings.auth_timeout,
            )
        except httpx.HTTPError:
            logger.warning("failed to write audit event", exc_info=True)

    async def proxy(self, request: Request) -> Response:
        url = f"{self._settings.auth_base_url.rstrip('/')}{request.url.path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
        headers = _filter_headers(request.headers)
        cid = correlation_id_var.get()
        if cid:
            headers["X-Correlation-ID"] = cid
        body = await request.body()
        upstream = await self._client.request(
            request.method,
            url,
            headers=headers,
            content=body or None,
            timeout=self._settings.auth_timeout,
        )
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=_filter_headers(upstream.headers),
            media_type=upstream.headers.get("content-type"),
        )


def _filter_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}
