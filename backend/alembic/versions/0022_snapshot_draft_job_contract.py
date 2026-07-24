"""allow immutable snapshot draft jobs

Revision ID: 0022_snapshot_draft_jobs
Revises: 0021_proposal_stages
Create Date: 2026-07-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_snapshot_draft_jobs"
down_revision: str | None = "0021_proposal_stages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("wordpress_draft_jobs") as batch:
        batch.drop_constraint(
            "ck_wordpress_draft_jobs_contract_version",
            type_="check",
        )
        batch.create_check_constraint(
            "ck_wordpress_draft_jobs_contract_version",
            "contract_version IN "
            "('wordpress-draft-job-v1', 'wordpress-snapshot-draft-job-v1')",
        )


def downgrade() -> None:
    with op.batch_alter_table("wordpress_draft_jobs") as batch:
        batch.drop_constraint(
            "ck_wordpress_draft_jobs_contract_version",
            type_="check",
        )
        batch.create_check_constraint(
            "ck_wordpress_draft_jobs_contract_version",
            "contract_version = 'wordpress-draft-job-v1'",
        )
