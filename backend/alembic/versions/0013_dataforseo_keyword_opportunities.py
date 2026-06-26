"""add dataforseo keyword opportunities

Revision ID: 0013_dataforseo
Revises: 0012_prompt_version
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_dataforseo"
down_revision: str | None = "0012_prompt_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dataforseo_connections",
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("login", sa.String(length=255), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(length=24), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.create_table(
        "keyword_opportunities",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("keyword", sa.String(length=512), nullable=False),
        sa.Column("location_code", sa.Integer(), nullable=False),
        sa.Column("language_code", sa.String(length=8), nullable=False),
        sa.Column("search_volume", sa.Integer(), nullable=True),
        sa.Column("cpc", sa.Numeric(12, 4), nullable=True),
        sa.Column("competition", sa.Numeric(8, 4), nullable=True),
        sa.Column("competition_level", sa.String(length=32), nullable=True),
        sa.Column("keyword_difficulty", sa.Integer(), nullable=True),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("target_url", sa.String(length=2048), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=64),
            server_default="dataforseo",
            nullable=False,
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "keyword",
            "location_code",
            "language_code",
            name="uq_keyword_opportunity_identity",
        ),
    )
    op.create_index(
        op.f("ix_keyword_opportunities_project_id"),
        "keyword_opportunities",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_keyword_opportunities_project_id"),
        table_name="keyword_opportunities",
    )
    op.drop_table("keyword_opportunities")
    op.drop_table("dataforseo_connections")
