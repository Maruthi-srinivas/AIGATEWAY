from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aigateway.config import RagSettings
from aigateway.rag.chunking import chunk_text
from aigateway.rag.embeddings import embed_text
from aigateway.rag.models import Document
from aigateway.rag.repository import create_document
from aigateway.telemetry import get_logger

logger = get_logger(__name__)

HR_TITLE = "Acme HR leave policy"
HR_BODY = (
    "Acme HR paid time off is twenty days per year. "
    "Parental leave is sixteen weeks for eligible employees."
)
ENG_TITLE = "Acme Engineering on-call"
ENG_BODY = (
    "Acme Engineering on-call rotation lasts one week. "
    "The pager escalation goes to the incident commander."
)


async def seed_if_needed(session: AsyncSession, settings: RagSettings, *, http_client) -> None:
    if not settings.seed_enabled:
        return
    existing = await session.scalar(select(func.count()).select_from(Document))
    if existing:
        return
    tenants = {
        row["slug"]: row["id"]
        for row in (await session.execute(text("SELECT id, slug FROM tenants"))).mappings()
    }
    hr_id = tenants.get("acme-hr")
    eng_id = tenants.get("acme-eng")
    if hr_id is None or eng_id is None:
        logger.warning("rag seed skipped missing tenants")
        return
    await _ingest(session, settings, http_client, tenant_id=hr_id, title=HR_TITLE, body=HR_BODY)
    await _ingest(session, settings, http_client, tenant_id=eng_id, title=ENG_TITLE, body=ENG_BODY)
    logger.info("rag seed ensured")


async def _ingest(
    session: AsyncSession,
    settings: RagSettings,
    http_client,
    *,
    tenant_id: uuid.UUID,
    title: str,
    body: str,
) -> None:
    parts = chunk_text(body)
    embedded = [(part, await embed_text(part, settings, client=http_client)) for part in parts]
    await create_document(
        session,
        tenant_id=tenant_id,
        created_by=None,
        title=title,
        body=body,
        classification=None,
        acl=[],
        chunks=embedded,
    )
