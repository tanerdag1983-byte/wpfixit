"""add reviewable page package proposals

Revision ID: 0016_page_pkg_proposals
Revises: 0015_page_pkg_settings
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_page_pkg_proposals"
down_revision: str | None = "0015_page_pkg_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "page_package_proposals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column(
            "state", sa.String(length=24), server_default="generating", nullable=False
        ),
        sa.Column("package", sa.JSON(), nullable=False),
        sa.Column("rendered_html", sa.Text(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("proposed_by", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wordpress_object_id", sa.Integer(), nullable=True),
        sa.Column("wordpress_edit_url", sa.String(length=2048), nullable=True),
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
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["keyword_opportunities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index(
        "ix_page_package_proposals_project_id", "page_package_proposals", ["project_id"]
    )
    op.create_index(
        "ix_page_package_proposals_opportunity_id",
        "page_package_proposals",
        ["opportunity_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_page_package_proposals_opportunity_id", table_name="page_package_proposals"
    )
    op.drop_index(
        "ix_page_package_proposals_project_id", table_name="page_package_proposals"
    )
    op.drop_table("page_package_proposals")
