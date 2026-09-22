"""guardrail_policies

Revision ID: 0001_guardrail_policies
Revises:
Create Date: 2026-09-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_guardrail_policies"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guardrail_policies",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_injection", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("jailbreak", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("moderation", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("token_limit", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("pii", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("pii_action", sa.String(16), nullable=False, server_default="redact"),
        sa.Column("max_input_chars", sa.Integer(), nullable=False, server_default="4000"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("guardrail_policies")
