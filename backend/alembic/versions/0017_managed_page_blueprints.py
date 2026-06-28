"""persist immutable managed page blueprints

Revision ID: 0017_managed_page_blueprints
Revises: 0016_page_pkg_proposals
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

BLUEPRINT_LIFECYCLE_STATES = (
    "capture_required",
    "capturing",
    "ready",
    "stale",
    "invalid",
)

BLUEPRINT_LIFECYCLE_STATE_CHECK = (
    "state IN ('capture_required', 'capturing', 'ready', 'stale', 'invalid')"
)

revision: str = "0017_managed_page_blueprints"
down_revision: str | None = "0016_page_pkg_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_wordpress_pages_project_id_id",
        "wordpress_pages",
        ["project_id", "id"],
    )
    op.create_table(
        "page_blueprints",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("page_type", sa.String(length=32), nullable=False),
        sa.Column("source_wordpress_page_id", sa.String(length=64), nullable=False),
        sa.Column("wordpress_blueprint_id", sa.Integer(), nullable=False),
        sa.Column("builder", sa.String(length=32), nullable=False),
        sa.Column("seo_plugin", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("structure_hash", sa.String(length=128), nullable=False),
        sa.Column("content_schema", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column(
            "is_default_for_page_type",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("supersedes_id", sa.String(length=64), nullable=True),
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
            BLUEPRINT_LIFECYCLE_STATE_CHECK,
            name="ck_page_blueprints_state",
        ),
        sa.CheckConstraint(
            "is_default_for_page_type = false OR state = 'ready'",
            name="ck_page_blueprints_default_ready",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "source_wordpress_page_id"],
            ["wordpress_pages.project_id", "wordpress_pages.id"],
            name="fk_page_blueprints_source_wordpress_page_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "supersedes_id"],
            ["page_blueprints.project_id", "page_blueprints.id"],
            name="fk_page_blueprints_supersedes_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "id",
            "version",
            "structure_hash",
            name="uq_page_blueprints_project_identity",
        ),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_page_blueprints_project_id_id",
        ),
        sa.UniqueConstraint(
            "project_id",
            "wordpress_blueprint_id",
            name="uq_page_blueprint_wordpress_identity",
        ),
        sa.UniqueConstraint("supersedes_id", name="uq_page_blueprints_supersedes_id"),
    )
    op.create_index(
        "ix_page_blueprints_project_id",
        "page_blueprints",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "uq_page_blueprint_default_per_type",
        "page_blueprints",
        ["project_id", "page_type"],
        unique=True,
        postgresql_where=sa.text("is_default_for_page_type = true"),
        sqlite_where=sa.text("is_default_for_page_type = 1"),
    )

    with op.batch_alter_table("page_package_proposals", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("blueprint_id", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("blueprint_version", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("blueprint_structure_hash", sa.String(length=128), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_page_package_proposals_blueprint_identity_all_or_none",
            "("
            "(blueprint_id IS NULL AND blueprint_version IS NULL AND "
            "blueprint_structure_hash IS NULL) OR "
            "(blueprint_id IS NOT NULL AND blueprint_version IS NOT NULL AND "
            "blueprint_structure_hash IS NOT NULL)"
            ")",
        )
        batch_op.create_foreign_key(
            "fk_page_package_proposals_blueprint_identity",
            "page_blueprints",
            [
                "project_id",
                "blueprint_id",
                "blueprint_version",
                "blueprint_structure_hash",
            ],
            ["project_id", "id", "version", "structure_hash"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("page_package_proposals", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "fk_page_package_proposals_blueprint_identity", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "ck_page_package_proposals_blueprint_identity_all_or_none", type_="check"
        )
        batch_op.drop_column("blueprint_structure_hash")
        batch_op.drop_column("blueprint_version")
        batch_op.drop_column("blueprint_id")

    op.drop_index("uq_page_blueprint_default_per_type", table_name="page_blueprints")
    op.drop_index("ix_page_blueprints_project_id", table_name="page_blueprints")
    op.drop_table("page_blueprints")
    op.drop_constraint(
        "uq_wordpress_pages_project_id_id",
        "wordpress_pages",
        type_="unique",
    )
