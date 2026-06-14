"""add recommendation prompt version

Revision ID: 0012_prompt_version
Revises: 0011_multi_ai_connections
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_prompt_version"
down_revision: str | None = "0011_multi_ai_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "seo_recommendations",
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("seo_recommendations", "prompt_version")
