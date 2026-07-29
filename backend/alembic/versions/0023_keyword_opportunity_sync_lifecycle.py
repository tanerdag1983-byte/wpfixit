"""persist keyword opportunity sync lifecycle

Revision ID: 0023_keyword_sync_lifecycle
Revises: 0022_snapshot_draft_jobs
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_keyword_sync_lifecycle"
down_revision: str | None = "0022_snapshot_draft_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "keyword_opportunity_sync_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("seed_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("offset", sa.Integer(), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            sa.String(length=16),
            server_default="running",
            nullable=False,
        ),
        sa.Column("provider_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("accepted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "state IN ('running', 'completed', 'failed')",
            name="ck_keyword_opportunity_sync_runs_state",
        ),
        sa.CheckConstraint(
            '"offset" >= 0',
            name="ck_keyword_opportunity_sync_runs_offset",
        ),
        sa.CheckConstraint(
            '"limit" >= 0',
            name="ck_keyword_opportunity_sync_runs_limit",
        ),
        sa.CheckConstraint(
            "provider_count >= 0 AND accepted_count >= 0 AND created_count >= 0 "
            "AND updated_count >= 0 AND rejected_count >= 0",
            name="ck_keyword_opportunity_sync_runs_counts",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "keyword_opportunity_sync_states",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("seed_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("next_offset", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "exhausted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("last_successful_run_id", sa.String(length=64), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "next_offset >= 0",
            name="ck_keyword_opportunity_sync_states_next_offset",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_successful_run_id"],
            ["keyword_opportunity_sync_runs.id"],
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("project_id"),
    )
    with op.batch_alter_table("keyword_opportunities") as batch:
        batch.add_column(
            sa.Column("first_seen_run_id", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column("last_seen_run_id", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "last_seen_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_foreign_key(
            "fk_keyword_opportunities_first_seen_run_id",
            "keyword_opportunity_sync_runs",
            ["first_seen_run_id"],
            ["id"],
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        )
        batch.create_foreign_key(
            "fk_keyword_opportunities_last_seen_run_id",
            "keyword_opportunity_sync_runs",
            ["last_seen_run_id"],
            ["id"],
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        )
    op.execute(
        "UPDATE keyword_opportunities SET last_seen_at = discovered_at "
        "WHERE last_seen_at IS NULL OR last_seen_at <> discovered_at"
    )
    with op.batch_alter_table("keyword_opportunities") as batch:
        batch.alter_column(
            "last_seen_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("keyword_opportunities") as batch:
        batch.drop_constraint(
            "fk_keyword_opportunities_last_seen_run_id",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_keyword_opportunities_first_seen_run_id",
            type_="foreignkey",
        )
        batch.drop_column("dismissed_at")
        batch.drop_column("last_seen_at")
        batch.drop_column("last_seen_run_id")
        batch.drop_column("first_seen_run_id")
    op.drop_table("keyword_opportunity_sync_states")
    op.drop_table("keyword_opportunity_sync_runs")
