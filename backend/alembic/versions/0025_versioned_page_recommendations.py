"""scope page recommendations to observed versions

Revision ID: 0025_versioned_recs
Revises: 0024_page_monitoring
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_versioned_recs"
down_revision: str | None = "0024_page_monitoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_page_recommendations_page_fingerprint",
        "page_recommendations",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_page_recommendations_version_fingerprint",
        "page_recommendations",
        ["page_version_id", "fingerprint"],
    )
    op.execute(
        sa.text(
            "UPDATE page_recommendations AS recommendation "
            "SET state = 'superseded' "
            "WHERE state = 'open' AND EXISTS ("
            "SELECT 1 FROM page_observed_versions AS newer "
            "JOIN page_observed_versions AS current "
            "ON current.id = recommendation.page_version_id "
            "WHERE newer.wordpress_page_id = recommendation.wordpress_page_id "
            "AND (newer.observed_at, newer.id) > (current.observed_at, current.id)"
            ")"
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_page_recommendations_version_fingerprint",
        "page_recommendations",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_page_recommendations_page_fingerprint",
        "page_recommendations",
        ["wordpress_page_id", "fingerprint"],
    )
