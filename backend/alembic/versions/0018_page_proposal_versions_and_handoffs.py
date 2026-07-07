"""persist page proposal versions and handoffs

Revision ID: 0018_page_proposal_versions
Revises: 0017_managed_page_blueprints
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_page_proposal_versions"
down_revision: str | None = "0017_managed_page_blueprints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "page_package_proposals",
        sa.Column("proposal_group_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "page_package_proposals",
        sa.Column(
            "version_number",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "page_package_proposals",
        sa.Column("parent_version_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "page_package_proposals",
        sa.Column("current_version_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "page_package_proposals",
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "page_package_proposals",
        sa.Column(
            "generation_mode",
            sa.String(length=24),
            nullable=False,
            server_default="full",
        ),
    )
    op.add_column(
        "page_package_proposals",
        sa.Column("target_block_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "page_package_proposals",
        sa.Column("user_instruction", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_page_package_proposals_parent_version",
        "page_package_proposals",
        "page_package_proposals",
        ["parent_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute(
        "update page_package_proposals "
        "set proposal_group_id = id, current_version_id = id "
        "where proposal_group_id is null"
    )
    op.alter_column("page_package_proposals", "proposal_group_id", nullable=False)
    op.alter_column("page_package_proposals", "current_version_id", nullable=False)
    op.create_index(
        "ix_page_package_proposals_proposal_group_id",
        "page_package_proposals",
        ["proposal_group_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_page_package_proposals_current_pointer_matches_flag",
        "page_package_proposals",
        "((is_current = true AND id = current_version_id) OR "
        "(is_current = false AND id != current_version_id))",
    )
    op.create_index(
        "ix_page_package_proposals_current_version_per_group",
        "page_package_proposals",
        ["proposal_group_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
        sqlite_where=sa.text("is_current = 1"),
    )

    op.create_table(
        "page_package_regeneration_candidates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("proposal_group_id", sa.String(length=64), nullable=False),
        sa.Column("base_version_id", sa.String(length=64), nullable=False),
        sa.Column("generation_mode", sa.String(length=24), nullable=False),
        sa.Column("target_block_id", sa.String(length=128), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("candidate_package", sa.JSON(), nullable=False),
        sa.Column("candidate_rendered_html", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column(
            "input_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="generating",
        ),
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
            ["base_version_id"],
            ["page_package_proposals.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_page_package_regeneration_candidates_proposal_group_id",
        "page_package_regeneration_candidates",
        ["proposal_group_id"],
    )

    op.create_table(
        "page_package_handoffs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("proposal_version_id", sa.String(length=64), nullable=False),
        sa.Column("wordpress_connection_id", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("issued_by", sa.String(length=64), nullable=False),
        sa.Column(
            "state",
            sa.String(length=24),
            nullable=False,
            server_default="issued",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["proposal_version_id"],
            ["page_package_proposals.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wordpress_connection_id"],
            ["wordpress_connections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )


def downgrade() -> None:
    op.drop_table("page_package_handoffs")
    op.drop_index(
        "ix_page_package_regeneration_candidates_proposal_group_id",
        table_name="page_package_regeneration_candidates",
    )
    op.drop_table("page_package_regeneration_candidates")

    op.drop_index(
        "ix_page_package_proposals_current_version_per_group",
        table_name="page_package_proposals",
    )
    op.drop_constraint(
        "ck_page_package_proposals_current_pointer_matches_flag",
        "page_package_proposals",
        type_="check",
    )
    op.drop_index(
        "ix_page_package_proposals_proposal_group_id",
        table_name="page_package_proposals",
    )
    op.drop_constraint(
        "fk_page_package_proposals_parent_version",
        "page_package_proposals",
        type_="foreignkey",
    )
    op.drop_column("page_package_proposals", "user_instruction")
    op.drop_column("page_package_proposals", "target_block_id")
    op.drop_column("page_package_proposals", "generation_mode")
    op.drop_column("page_package_proposals", "is_current")
    op.drop_column("page_package_proposals", "current_version_id")
    op.drop_column("page_package_proposals", "parent_version_id")
    op.drop_column("page_package_proposals", "version_number")
    op.drop_column("page_package_proposals", "proposal_group_id")
