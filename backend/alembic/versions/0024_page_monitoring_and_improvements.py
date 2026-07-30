"""persist page monitoring and improvement history

Revision ID: 0024_page_monitoring
Revises: 0023_keyword_sync_lifecycle
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_page_monitoring"
down_revision: str | None = "0023_keyword_sync_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    wordpress_page_constraints = sa.inspect(op.get_bind()).get_unique_constraints(
        "wordpress_pages"
    )
    if not any(
        constraint["column_names"] == ["project_id", "id"]
        for constraint in wordpress_page_constraints
    ):
        op.create_unique_constraint(
            "uq_wordpress_pages_project_id_id",
            "wordpress_pages",
            ["project_id", "id"],
        )

    with op.batch_alter_table("page_package_proposals") as batch:
        batch.add_column(
            sa.Column("source_wordpress_page_id", sa.String(length=64), nullable=True)
        )
        batch.create_foreign_key(
            "fk_page_package_proposals_source_wordpress_page_project",
            "wordpress_pages",
            ["project_id", "source_wordpress_page_id"],
            ["project_id", "id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "page_observed_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("wordpress_page_id", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("snapshot_payload", sa.JSON(), nullable=False),
        sa.Column("proposal_version_id", sa.String(length=64), nullable=True),
        sa.Column("draft_job_id", sa.String(length=64), nullable=True),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "wordpress_page_id"],
            ["wordpress_pages.project_id", "wordpress_pages.id"],
            name="fk_page_observed_versions_project_page",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "proposal_version_id"],
            ["page_package_proposals.project_id", "page_package_proposals.id"],
            name="fk_page_observed_versions_project_proposal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["draft_job_id"],
            ["wordpress_draft_jobs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "wordpress_page_id",
            "content_hash",
            name="uq_page_observed_versions_page_hash",
        ),
    )
    op.create_table(
        "page_score_snapshots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("page_version_id", sa.String(length=64), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("factors", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["page_version_id"], ["page_observed_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_page_score_snapshots_page_version_id",
        "page_score_snapshots",
        ["page_version_id"],
        unique=False,
    )
    op.create_table(
        "page_recommendations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("page_version_id", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["page_version_id"], ["page_observed_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "page_version_id",
            "fingerprint",
            name="uq_page_recommendations_version_fingerprint",
        ),
    )
    op.create_index(
        "ix_page_recommendations_page_version_id",
        "page_recommendations",
        ["page_version_id"],
        unique=False,
    )
    op.create_table(
        "page_timeline_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("wordpress_page_id", sa.String(length=64), nullable=False),
        sa.Column("page_version_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "wordpress_page_id"],
            ["wordpress_pages.project_id", "wordpress_pages.id"],
            name="fk_page_timeline_events_project_page",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["page_version_id"],
            ["page_observed_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_page_timeline_events_page_created",
        "page_timeline_events",
        ["wordpress_page_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "wordpress_snapshot_capture_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("wordpress_page_id", sa.String(length=64), nullable=False),
        sa.Column(
            "state",
            sa.String(length=24),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("claim_token", sa.String(length=128), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_claim_token_hash", sa.String(length=64), nullable=True),
        sa.Column("snapshot_result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
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
            name="ck_wordpress_snapshot_capture_jobs_state",
        ),
        sa.CheckConstraint(
            "(state = 'claimed' AND claim_token IS NOT NULL AND "
            "claim_expires_at IS NOT NULL AND claimed_at IS NOT NULL) OR "
            "(state != 'claimed' AND claim_token IS NULL AND "
            "claim_expires_at IS NULL AND claimed_at IS NULL)",
            name="ck_wordpress_snapshot_capture_jobs_claim_fields",
        ),
        sa.CheckConstraint(
            "(state IN ('completed', 'failed') AND "
            "terminal_claim_token_hash IS NOT NULL) OR "
            "(state NOT IN ('completed', 'failed') AND "
            "terminal_claim_token_hash IS NULL)",
            name="ck_wordpress_snapshot_capture_jobs_terminal_claim_hash",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "wordpress_page_id"],
            ["wordpress_pages.project_id", "wordpress_pages.id"],
            name="fk_wordpress_snapshot_capture_jobs_project_page",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wordpress_snapshot_capture_jobs_project_state",
        "wordpress_snapshot_capture_jobs",
        ["project_id", "state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wordpress_snapshot_capture_jobs_project_state",
        table_name="wordpress_snapshot_capture_jobs",
    )
    op.drop_table("wordpress_snapshot_capture_jobs")
    op.drop_index(
        "ix_page_timeline_events_page_created",
        table_name="page_timeline_events",
    )
    op.drop_table("page_timeline_events")
    op.drop_index(
        "ix_page_recommendations_page_version_id",
        table_name="page_recommendations",
    )
    op.drop_table("page_recommendations")
    op.drop_index(
        "ix_page_score_snapshots_page_version_id",
        table_name="page_score_snapshots",
    )
    op.drop_table("page_score_snapshots")
    op.drop_table("page_observed_versions")
    with op.batch_alter_table("page_package_proposals") as batch:
        batch.drop_constraint(
            "fk_page_package_proposals_source_wordpress_page_project",
            type_="foreignkey",
        )
        batch.drop_column("source_wordpress_page_id")
