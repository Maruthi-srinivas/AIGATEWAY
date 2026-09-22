from __future__ import annotations

import httpx

from aigateway.config import GatewaySettings
from aigateway.contracts import (
    DocumentDetail,
    DocumentIngest,
    DocumentList,
    DocumentNotFoundError,
    DocumentOut,
    RagUnavailableError,
    RetrievedChunk,
)
from aigateway.telemetry import correlation_id_var, get_logger

logger = get_logger(__name__)


class HttpRagClient:
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
        return f"{self._settings.rag_base_url.rstrip('/')}{path}"

    async def retrieve(
        self,
        *,
        tenant_id: str,
        query: str,
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        try:
            response = await self._client.post(
                self._url("/internal/v1/retrieve"),
                headers=self._headers(),
                json={"tenant_id": tenant_id, "query": query, "top_k": top_k},
                timeout=self._settings.rag_timeout,
            )
        except httpx.HTTPError as exc:
            logger.warning("rag retrieve failed")
            raise RagUnavailableError() from exc
        if response.status_code >= 500 or response.status_code == 401:
            raise RagUnavailableError()
        response.raise_for_status()
        payload = response.json()
        return [RetrievedChunk.model_validate(item) for item in payload.get("chunks", [])]

    async def ingest(self, tenant_id: str, body: DocumentIngest, created_by: str) -> DocumentOut:
        return await self._json(
            "POST",
            "/internal/v1/documents",
            params={"tenant_id": tenant_id, "created_by": created_by},
            json=body.model_dump(),
            model=DocumentOut,
        )

    async def list_documents(self, tenant_id: str, *, limit: int, offset: int) -> DocumentList:
        return await self._json(
            "GET",
            "/internal/v1/documents",
            params={"tenant_id": tenant_id, "limit": limit, "offset": offset},
            model=DocumentList,
        )

    async def get_document(self, tenant_id: str, document_id: str) -> DocumentDetail:
        return await self._json(
            "GET",
            f"/internal/v1/documents/{document_id}",
            params={"tenant_id": tenant_id},
            model=DocumentDetail,
        )

    async def delete_document(self, tenant_id: str, document_id: str) -> None:
        await self._json(
            "DELETE",
            f"/internal/v1/documents/{document_id}",
            params={"tenant_id": tenant_id},
            model=None,
        )

    async def _json(self, method: str, path: str, *, params, json=None, model):
        try:
            response = await self._client.request(
                method,
                self._url(path),
                headers=self._headers(),
                params=params,
                json=json,
                timeout=self._settings.rag_timeout,
            )
        except httpx.HTTPError as exc:
            raise RagUnavailableError() from exc
        if response.status_code == 404:
            raise DocumentNotFoundError()
        if response.status_code >= 500 or response.status_code == 401:
            raise RagUnavailableError()
        if response.status_code == 400:
            body = response.json() if response.content else {}
            from aigateway.contracts import PayloadTooLargeError, ValidationFailedError

            code = body.get("code")
            if code == "payload_too_large":
                raise PayloadTooLargeError(body.get("detail", "payload too large"))
            raise ValidationFailedError(body.get("detail", "invalid request"))
        response.raise_for_status()
        if model is None:
            return None
        return model.model_validate(response.json())
