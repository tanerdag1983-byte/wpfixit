"""add project page package settings

Revision ID: 0015_page_pkg_settings
Revises: 0014_keyword_targets
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_page_pkg_settings"
down_revision: str | None = "0014_keyword_targets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_page_package_settings",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("builder", sa.String(length=32), nullable=False),
        sa.Column(
            "template_wordpress_page_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("seo_plugin", sa.String(length=32), nullable=False),
        sa.Column("slot_mapping", sa.JSON(), nullable=False),
        sa.Column("template_content_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "validation_state",
            sa.String(length=24),
            server_default="unvalidated",
            nullable=False,
        ),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["template_wordpress_page_id"],
            ["wordpress_pages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id"),
    )


def downgrade() -> None:
    op.drop_table("project_page_package_settings")
