"""search_vector for hybrid retrieval

Revision ID: 0002_rag_search
Revises: 0001_rag_documents
Create Date: 2026-09-23
"""

from alembic import op

revision = "0002_rag_search"
down_revision = "0001_rag_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE chunks ADD COLUMN search_vector tsvector")
    op.execute(
        """
        UPDATE chunks AS c
        SET search_vector = to_tsvector('simple', d.title || ' ' || c.content)
        FROM documents AS d
        WHERE d.id = c.document_id
        """
    )
    op.execute("ALTER TABLE chunks ALTER COLUMN search_vector SET NOT NULL")
    op.execute("CREATE INDEX ix_chunks_search_vector ON chunks USING gin (search_vector)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_search_vector")
    op.execute("ALTER TABLE chunks DROP COLUMN search_vector")
