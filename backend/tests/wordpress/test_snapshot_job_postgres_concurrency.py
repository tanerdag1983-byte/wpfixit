import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domains.projects.models import Organization, Project
from app.domains.wordpress.draft_jobs import hash_project_key
from app.domains.wordpress.models import (
    WordPressOutboundCredential,
    WordPressPage,
)
from app.domains.wordpress.snapshot_jobs import (
    SnapshotJobError,
    claim_next_snapshot_job,
    complete_snapshot_job,
    create_or_get_snapshot_job,
    fail_snapshot_job,
)
from tests.wordpress.test_snapshot_job_service import snapshot_result

POSTGRES_TEST_URL = os.getenv("WP_FIXPILOT_POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="WP_FIXPILOT_POSTGRES_TEST_URL is not configured",
)


def test_snapshot_claim_and_terminal_races_have_one_winner() -> None:
    engine = create_engine(POSTGRES_TEST_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:12]
    organization_id = f"snapshot-org-{suffix}"
    project_id = f"snapshot-project-{suffix}"
    page_id = f"snapshot-page-{suffix}"
    site_url = f"https://{suffix}.example"
    with Session(engine) as session:
        session.add(Organization(id=organization_id, name="Snapshot concurrency"))
        session.commit()
        session.add(
            Project(
                id=project_id,
                organization_id=organization_id,
                name="Snapshot concurrency",
                domain=site_url,
            )
        )
        session.commit()
        page = WordPressPage(
            id=page_id,
            project_id=project_id,
            wordpress_object_id=701,
            post_type="page",
            status="publish",
            title="Source",
            slug="source",
            url=f"{site_url}/source",
            content_hash="source-content-hash",
        )
        session.add_all(
            [
                page,
                WordPressOutboundCredential(
                    id=f"snapshot-credential-{suffix}",
                    project_id=project_id,
                    key_hash=hash_project_key("wpfx_concurrency"),
                    site_url=site_url,
                ),
            ]
        )
        session.commit()
        job_id = create_or_get_snapshot_job(session, page).id
        session.commit()

    claim_barrier = Barrier(2)

    def claim() -> tuple[str, str] | None:
        with Session(engine) as session:
            claim_barrier.wait(timeout=10)
            claimed = claim_next_snapshot_job(session, project_id, site_url)
            session.commit()
            return (
                (claimed.job.id, claimed.claim_token)
                if claimed is not None
                else None
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = [future.result(timeout=10) for future in [
                executor.submit(claim),
                executor.submit(claim),
            ]]
        assert claims.count(None) == 1
        _, claim_token = next(value for value in claims if value is not None)
        terminal_barrier = Barrier(2)

        def complete() -> str:
            with Session(engine) as session:
                terminal_barrier.wait(timeout=10)
                try:
                    complete_snapshot_job(
                        session,
                        job_id,
                        claim_token,
                        snapshot_result(
                            source_url=f"{site_url}/source",
                        ),
                    )
                    session.commit()
                    return "completed"
                except SnapshotJobError:
                    session.rollback()
                    return "rejected"

        def fail() -> str:
            with Session(engine) as session:
                terminal_barrier.wait(timeout=10)
                try:
                    fail_snapshot_job(
                        session,
                        job_id,
                        claim_token,
                        error_code="wordpress_error",
                        error_message="Capture failed",
                    )
                    session.commit()
                    return "failed"
                except SnapshotJobError:
                    session.rollback()
                    return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            terminal = [
                future.result(timeout=10)
                for future in [executor.submit(complete), executor.submit(fail)]
            ]
        assert terminal.count("rejected") == 1
        assert set(terminal) & {"completed", "failed"}
    finally:
        with Session(engine) as session:
            organization = session.get(Organization, organization_id)
            if organization is not None:
                session.delete(organization)
                session.commit()
        engine.dispose()


def test_two_snapshot_creators_receive_the_same_open_job() -> None:
    engine = create_engine(POSTGRES_TEST_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:12]
    organization_id = f"snapshot-create-org-{suffix}"
    project_id = f"snapshot-create-project-{suffix}"
    page_id = f"snapshot-create-page-{suffix}"
    site_url = f"https://{suffix}.example"
    with Session(engine) as session:
        session.add(Organization(id=organization_id, name="Snapshot create race"))
        session.commit()
        session.add(
            Project(
                id=project_id,
                organization_id=organization_id,
                name="Snapshot create race",
                domain=site_url,
            )
        )
        session.commit()
        session.add(
            WordPressPage(
                id=page_id,
                project_id=project_id,
                wordpress_object_id=701,
                post_type="page",
                status="publish",
                title="Source",
                slug="source",
                url=f"{site_url}/source",
                content_hash="source-content-hash",
            )
        )
        session.commit()

    barrier = Barrier(2)

    def create() -> str:
        with Session(engine) as session:
            page = session.get(WordPressPage, page_id)
            assert page is not None
            barrier.wait(timeout=10)
            job = create_or_get_snapshot_job(session, page)
            session.commit()
            return job.id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            job_ids = [
                future.result(timeout=10)
                for future in [executor.submit(create), executor.submit(create)]
            ]
        assert job_ids[0] == job_ids[1]
    finally:
        with Session(engine) as session:
            organization = session.get(Organization, organization_id)
            if organization is not None:
                session.delete(organization)
                session.commit()
        engine.dispose()
