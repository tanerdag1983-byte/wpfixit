"""persist resumable proposal stages

Revision ID: 0021_proposal_stages
Revises: 0020_template_snapshots
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_proposal_stages"
down_revision: str | None = "0020_template_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "page_proposal_stages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("proposal_version_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=24), nullable=False),
        sa.Column(
            "state",
            sa.String(length=24),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column(
            "retry_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("attempt_token", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_retried_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "name IN ('template', 'text', 'validation')",
            name="ck_page_proposal_stages_name",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'running', 'ready', 'attention', 'failed')",
            name="ck_page_proposal_stages_state",
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name="ck_page_proposal_stages_retry_count",
        ),
        sa.CheckConstraint(
            "length(attempt_token) BETWEEN 1 AND 64",
            name="ck_page_proposal_stages_attempt_token",
        ),
        sa.CheckConstraint(
            "length(CAST(result AS TEXT)) <= 100000",
            name="ck_page_proposal_stages_result_size",
        ),
        sa.CheckConstraint(
            "length(CAST(errors AS TEXT)) <= 20000",
            name="ck_page_proposal_stages_errors_size",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_version_id"],
            ["page_package_proposals.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposal_version_id",
            "name",
            name="uq_page_proposal_stages_proposal_name",
        ),
    )
    op.create_index(
        "ix_page_proposal_stages_proposal_version_id",
        "page_proposal_stages",
        ["proposal_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_page_proposal_stages_proposal_version_id",
        table_name="page_proposal_stages",
    )
    op.drop_table("page_proposal_stages")
