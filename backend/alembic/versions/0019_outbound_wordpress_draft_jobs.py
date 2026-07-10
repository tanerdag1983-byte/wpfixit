"""persist outbound WordPress draft jobs

Revision ID: 0019_outbound_wp_draft_jobs
Revises: 0018_page_proposal_versions
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_outbound_wp_draft_jobs"
down_revision: str | None = "0018_page_proposal_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wordpress_outbound_credentials",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("site_url", sa.String(length=2048), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_table(
        "wordpress_draft_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("proposal_version_id", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.String(length=64), nullable=False),
        sa.Column(
            "state",
            sa.String(length=24),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("claim_token", sa.String(length=128), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wordpress_object_id", sa.Integer(), nullable=True),
        sa.Column("wordpress_edit_url", sa.String(length=2048), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "state IN ('queued', 'claimed', 'completed', 'failed', 'cancelled')",
            name="ck_wordpress_draft_jobs_state",
        ),
        sa.CheckConstraint(
            "(claim_token IS NULL AND claim_expires_at IS NULL) OR "
            "(claim_token IS NOT NULL AND claim_expires_at IS NOT NULL)",
            name="ck_wordpress_draft_jobs_claim_fields",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["proposal_version_id"], ["page_package_proposals.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_version_id"),
    )
    op.create_index(
        "ix_wordpress_draft_jobs_project_state",
        "wordpress_draft_jobs",
        ["project_id", "state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wordpress_draft_jobs_project_state",
        table_name="wordpress_draft_jobs",
    )
    op.drop_table("wordpress_draft_jobs")
    op.drop_table("wordpress_outbound_credentials")
