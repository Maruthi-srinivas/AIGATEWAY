"""evaluation scores

Revision ID: 0001_evaluations
Revises:
Create Date: 2026-09-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_evaluations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("case_id", sa.String(64), nullable=True),
        sa.Column("faithfulness", sa.Float(), nullable=True),
        sa.Column("context_recall", sa.Float(), nullable=True),
        sa.Column("context_precision", sa.Float(), nullable=True),
        sa.Column("answer_correctness", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("feedback", sa.String(8), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_evaluations_tenant_id", "evaluations", ["tenant_id"])
    op.create_index("ix_evaluations_run_id", "evaluations", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluations_run_id", table_name="evaluations")
    op.drop_index("ix_evaluations_tenant_id", table_name="evaluations")
    op.drop_table("evaluations")
