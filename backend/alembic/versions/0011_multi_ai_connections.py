"""store multiple AI connections and project policy

Revision ID: 0011_multi_ai_connections
Revises: 0010_ai_settings
Create Date: 2026-06-13 16:00:00.000000
"""

from collections.abc import Sequence
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa

from alembic import op

revision: str = "0011_multi_ai_connections"
down_revision: str | None = "0010_ai_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_CONNECTION_NAME = "Bestaande AI-koppeling"


def _legacy_connection_id(organization_id: str) -> str:
    value = uuid5(NAMESPACE_URL, f"wp-fixpilot:legacy-ai:{organization_id}")
    return f"legacy-{value.hex}"


def _normalize_legacy_provider(provider: str) -> str:
    if len(provider) <= 32:
        return provider
    digest = sha256(provider.encode()).hexdigest()[:25]
    return f"legacy_{digest}"


def upgrade() -> None:
    op.create_table(
        "ai_connections",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("default_model", sa.String(length=255), nullable=True),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "name",
            name="uq_ai_connection_org_name",
        ),
    )
    op.create_index(
        op.f("ix_ai_connections_organization_id"),
        "ai_connections",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "project_ai_policies",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("primary_connection_id", sa.String(length=64), nullable=False),
        sa.Column("primary_model", sa.String(length=255), nullable=False),
        sa.Column("fallback_connection_id", sa.String(length=64), nullable=True),
        sa.Column("fallback_model", sa.String(length=255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fallback_connection_id"],
            ["ai_connections.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["primary_connection_id"],
            ["ai_connections.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id"),
    )

    connection = op.get_bind()
    old_settings = sa.table(
        "organization_ai_settings",
        sa.column("organization_id", sa.String(length=64)),
        sa.column("provider", sa.String(length=64)),
        sa.column("base_url", sa.String(length=2048)),
        sa.column("model", sa.String(length=255)),
        sa.column("encrypted_api_key", sa.Text()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    ai_connections = sa.table(
        "ai_connections",
        sa.column("id", sa.String(length=64)),
        sa.column("organization_id", sa.String(length=64)),
        sa.column("name", sa.String(length=160)),
        sa.column("provider", sa.String(length=32)),
        sa.column("base_url", sa.String(length=2048)),
        sa.column("default_model", sa.String(length=255)),
        sa.column("encrypted_api_key", sa.Text()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    settings_rows = connection.execute(sa.select(old_settings)).mappings()
    migrated_rows = [
        {
            "id": _legacy_connection_id(row["organization_id"]),
            "organization_id": row["organization_id"],
            "name": LEGACY_CONNECTION_NAME,
            "provider": _normalize_legacy_provider(row["provider"]),
            "base_url": row["base_url"],
            "default_model": row["model"],
            "encrypted_api_key": row["encrypted_api_key"],
            "enabled": True,
            "created_at": row["updated_at"],
            "updated_at": row["updated_at"],
        }
        for row in settings_rows
    ]
    if migrated_rows:
        connection.execute(sa.insert(ai_connections), migrated_rows)

    op.drop_table("organization_ai_settings")


def downgrade() -> None:
    op.create_table(
        "organization_ai_settings",
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
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

    connection = op.get_bind()
    ai_connections = sa.table(
        "ai_connections",
        sa.column("id", sa.String(length=64)),
        sa.column("organization_id", sa.String(length=64)),
        sa.column("provider", sa.String(length=32)),
        sa.column("base_url", sa.String(length=2048)),
        sa.column("default_model", sa.String(length=255)),
        sa.column("encrypted_api_key", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    old_settings = sa.table(
        "organization_ai_settings",
        sa.column("organization_id", sa.String(length=64)),
        sa.column("provider", sa.String(length=64)),
        sa.column("base_url", sa.String(length=2048)),
        sa.column("model", sa.String(length=255)),
        sa.column("encrypted_api_key", sa.Text()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    connection_rows = connection.execute(
        sa.select(ai_connections).order_by(
            ai_connections.c.organization_id,
            ai_connections.c.created_at,
            ai_connections.c.id,
        )
    ).mappings()
    selected_organizations: set[str] = set()
    restored_rows = []
    for row in connection_rows:
        organization_id = row["organization_id"]
        if organization_id in selected_organizations:
            continue
        selected_organizations.add(organization_id)
        restored_rows.append(
            {
                "organization_id": organization_id,
                "provider": row["provider"],
                "base_url": row["base_url"],
                "model": row["default_model"] or "",
                "encrypted_api_key": row["encrypted_api_key"],
                "updated_at": row["updated_at"],
            }
        )
    if restored_rows:
        connection.execute(sa.insert(old_settings), restored_rows)

    op.drop_table("project_ai_policies")
    op.drop_index(
        op.f("ix_ai_connections_organization_id"),
        table_name="ai_connections",
    )
    op.drop_table("ai_connections")
