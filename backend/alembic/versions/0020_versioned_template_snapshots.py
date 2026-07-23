"""persist versioned template snapshots

Revision ID: 0020_template_snapshots
Revises: 0019_outbound_wp_draft_jobs
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_template_snapshots"
down_revision: str | None = "0019_outbound_wp_draft_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SNAPSHOT_IDENTITY_CHECK = (
    "("
    "(wordpress_snapshot_id IS NULL AND snapshot_version IS NULL AND "
    "schema_version IS NULL AND adapter_version IS NULL AND "
    "capture_state IS NULL AND migration_state IS NULL AND verified_at IS NULL) OR "
    "(wordpress_snapshot_id IS NOT NULL AND snapshot_version IS NOT NULL AND "
    "schema_version IS NOT NULL AND schema_version = 'snapshot-text-v1' AND "
    "adapter_version IS NOT NULL AND capture_state IS NOT NULL AND "
    "capture_state = 'ready' AND migration_state IS NOT NULL AND "
    "migration_state = 'native' AND "
    "verified_at IS NOT NULL)"
    ")"
)


def upgrade() -> None:
    with op.batch_alter_table("page_blueprints", recreate="auto") as batch_op:
        batch_op.add_column(
            sa.Column("wordpress_snapshot_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("snapshot_version", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("schema_version", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("adapter_version", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("capture_state", sa.String(length=24), nullable=True)
        )
        batch_op.add_column(
            sa.Column("migration_state", sa.String(length=24), nullable=True)
        )
        batch_op.add_column(
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_page_blueprint_wordpress_snapshot_identity",
            ["project_id", "wordpress_snapshot_id"],
        )
        batch_op.create_check_constraint(
            "ck_page_blueprints_snapshot_identity",
            SNAPSHOT_IDENTITY_CHECK,
        )


def downgrade() -> None:
    with op.batch_alter_table("page_blueprints", recreate="auto") as batch_op:
        batch_op.drop_constraint(
            "ck_page_blueprints_snapshot_identity",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_page_blueprint_wordpress_snapshot_identity",
            type_="unique",
        )
        batch_op.drop_column("verified_at")
        batch_op.drop_column("migration_state")
        batch_op.drop_column("capture_state")
        batch_op.drop_column("adapter_version")
        batch_op.drop_column("schema_version")
        batch_op.drop_column("snapshot_version")
        batch_op.drop_column("wordpress_snapshot_id")
