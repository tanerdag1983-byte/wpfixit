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
    op.execute(
        "ALTER TABLE page_recommendations ADD COLUMN IF NOT EXISTS "
        "wordpress_page_id VARCHAR(64)"
    )
    op.execute(
        "UPDATE page_recommendations AS recommendation "
        "SET wordpress_page_id = version.wordpress_page_id "
        "FROM page_observed_versions AS version "
        "WHERE version.id = recommendation.page_version_id "
        "AND recommendation.wordpress_page_id IS NULL"
    )
    op.execute(
        "ALTER TABLE page_recommendations ALTER COLUMN wordpress_page_id "
        "SET NOT NULL"
    )
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = "
        "'page_recommendations_wordpress_page_id_fkey' AND conrelid = "
        "'page_recommendations'::regclass) THEN "
        "ALTER TABLE page_recommendations ADD CONSTRAINT "
        "page_recommendations_wordpress_page_id_fkey FOREIGN KEY "
        "(wordpress_page_id) REFERENCES wordpress_pages (id) ON DELETE CASCADE; "
        "END IF; END $$"
    )
    op.execute(
        "ALTER TABLE page_recommendations DROP CONSTRAINT IF EXISTS "
        "uq_page_recommendations_page_fingerprint"
    )
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = "
        "'uq_page_recommendations_version_fingerprint' AND conrelid = "
        "'page_recommendations'::regclass) THEN "
        "ALTER TABLE page_recommendations ADD CONSTRAINT "
        "uq_page_recommendations_version_fingerprint UNIQUE "
        "(page_version_id, fingerprint); "
        "END IF; END $$"
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
    op.execute(
        sa.text(
            "DELETE FROM page_recommendations WHERE id IN ("
            "SELECT id FROM ("
            "SELECT recommendation.id, ROW_NUMBER() OVER ("
            "PARTITION BY recommendation.wordpress_page_id, "
            "recommendation.fingerprint ORDER BY "
            "CASE WHEN version.content_hash = page.content_hash THEN 0 ELSE 1 END, "
            "version.observed_at DESC, recommendation.created_at DESC, "
            "recommendation.id DESC"
            ") AS position "
            "FROM page_recommendations AS recommendation "
            "JOIN page_observed_versions AS version "
            "ON version.id = recommendation.page_version_id "
            "JOIN wordpress_pages AS page "
            "ON page.id = recommendation.wordpress_page_id"
            ") AS ranked WHERE position > 1)"
        )
    )
    op.create_unique_constraint(
        "uq_page_recommendations_page_fingerprint",
        "page_recommendations",
        ["wordpress_page_id", "fingerprint"],
    )
