"""organization routing policy

Revision ID: 0003_org_policy
Revises: 0002_jev_policy
Create Date: 2026-09-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_org_policy"
down_revision = "0002_jev_policy"
branch_labels = None
depends_on = None

_MODELS = sa.text('\'["fixture-cheap", "fixture-capable"]\'::jsonb')
_TOOLS = sa.text('\'["lookup_leave", "export_directory"]\'::jsonb')


def upgrade() -> None:
    op.add_column(
        "guardrail_policies",
        sa.Column("strictness", sa.String(16), nullable=False, server_default="standard"),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column("route_preference", sa.String(16), nullable=False, server_default="cheap"),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column("model_allowlist", postgresql.JSONB(), nullable=False, server_default=_MODELS),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column("tool_allowlist", postgresql.JSONB(), nullable=False, server_default=_TOOLS),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
    )


def downgrade() -> None:
    op.drop_column("guardrail_policies", "retention_days")
    op.drop_column("guardrail_policies", "tool_allowlist")
    op.drop_column("guardrail_policies", "model_allowlist")
    op.drop_column("guardrail_policies", "route_preference")
    op.drop_column("guardrail_policies", "strictness")
