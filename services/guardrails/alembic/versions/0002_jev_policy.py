"""jev policy thresholds

Revision ID: 0002_jev_policy
Revises: 0001_guardrail_policies
Create Date: 2026-09-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_jev_policy"
down_revision = "0001_guardrail_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guardrail_policies",
        sa.Column("jev_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column(
            "jev_injection_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.7",
        ),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column(
            "jev_jailbreak_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.7",
        ),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column(
            "jev_toxicity_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.7",
        ),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column(
            "jev_pii_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.7",
        ),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column(
            "jev_risk_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.7",
        ),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column(
            "jev_output_toxicity_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.7",
        ),
    )
    op.add_column(
        "guardrail_policies",
        sa.Column(
            "jev_output_pii_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.7",
        ),
    )


def downgrade() -> None:
    op.drop_column("guardrail_policies", "jev_output_pii_threshold")
    op.drop_column("guardrail_policies", "jev_output_toxicity_threshold")
    op.drop_column("guardrail_policies", "jev_risk_threshold")
    op.drop_column("guardrail_policies", "jev_pii_threshold")
    op.drop_column("guardrail_policies", "jev_toxicity_threshold")
    op.drop_column("guardrail_policies", "jev_jailbreak_threshold")
    op.drop_column("guardrail_policies", "jev_injection_threshold")
    op.drop_column("guardrail_policies", "jev_enabled")
