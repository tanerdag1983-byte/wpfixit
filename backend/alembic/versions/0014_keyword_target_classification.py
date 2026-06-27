"""classify keyword opportunity targets

Revision ID: 0014_keyword_targets
Revises: 0013_dataforseo
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_keyword_targets"
down_revision: str | None = "0013_dataforseo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "keyword_opportunities",
        sa.Column(
            "target_classification",
            sa.String(length=24),
            server_default="new_page",
            nullable=False,
        ),
    )
    op.add_column(
        "keyword_opportunities",
        sa.Column(
            "target_score",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "keyword_opportunities",
        sa.Column(
            "target_evidence",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE keyword_opportunities "
            "SET target_classification = CASE "
            "WHEN target_url IS NULL THEN 'new_page' ELSE 'review' END"
        )
    )


def downgrade() -> None:
    op.drop_column("keyword_opportunities", "target_evidence")
    op.drop_column("keyword_opportunities", "target_score")
    op.drop_column("keyword_opportunities", "target_classification")
