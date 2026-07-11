import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_packages.models import PagePackageProposal
from app.domains.projects.models import Organization, Project
from app.domains.wordpress.draft_jobs import (
    claim_next_draft_job,
    complete_draft_job,
    create_or_get_draft_job,
    fail_draft_job,
    hash_project_key,
)
from app.domains.wordpress.models import (
    WordPressOutboundCredential,
    WordPressPage,
)
from tests.wordpress.test_draft_job_service import _package, _schema

POSTGRES_TEST_URL = os.getenv("WP_FIXPILOT_POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="WP_FIXPILOT_POSTGRES_TEST_URL is required",
)


def test_two_pollers_cannot_claim_the_same_job() -> None:
    engine = create_engine(POSTGRES_TEST_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:12]
    organization_id = f"draft-org-{suffix}"
    project_id = f"draft-project-{suffix}"
    proposal_id = f"draft-proposal-{suffix}"
    site_url = f"https://{suffix}.example"

    with Session(engine) as session:
        session.add(Organization(id=organization_id, name="Draft concurrency"))
        session.commit()
        session.add(
            Project(
                id=project_id,
                organization_id=organization_id,
                name="Draft concurrency",
                domain=site_url,
            )
        )
        session.commit()
        source = WordPressPage(
            id=f"source-{suffix}",
            project_id=project_id,
            wordpress_object_id=810001,
            post_type="page",
            status="publish",
            title="Source",
            slug="source",
            url=f"{site_url}/source/",
        )
        opportunity = KeywordOpportunity(
            id=f"opportunity-{suffix}",
            project_id=project_id,
            keyword="draft concurrency",
            location_code=2528,
            language_code="nl",
            target_classification="new_page",
            target_score=0,
            target_evidence=[],
            source="test",
            raw_payload={},
        )
        generation_job = Job(
            id=f"generation-{suffix}",
            project_id=project_id,
            job_type="page_package_generation",
        )
        session.add_all([source, opportunity, generation_job])
        session.commit()
        blueprint = PageBlueprint(
            id=f"blueprint-{suffix}",
            project_id=project_id,
            name="Service",
            page_type="service",
            source_wordpress_page_id=source.id,
            wordpress_blueprint_id=810002,
            builder="acf",
            seo_plugin="yoast",
            version=1,
            structure_hash=f"hash-{suffix}",
            content_schema=_schema(),
            state="ready",
            is_default_for_page_type=True,
        )
        session.add(blueprint)
        session.commit()
        proposal = PagePackageProposal(
            id=proposal_id,
            project_id=project_id,
            opportunity_id=opportunity.id,
            job_id=generation_job.id,
            state="approved",
            proposal_group_id=proposal_id,
            current_version_id=proposal_id,
            is_current=True,
            blueprint_id=blueprint.id,
            blueprint_version=1,
            blueprint_structure_hash=f"hash-{suffix}",
            package=_package(),
            rendered_html="",
            config_snapshot={"content_schema": _schema()},
            proposed_by="concurrency-test",
            approved_by="concurrency-test",
        )
        session.add_all(
            [
                proposal,
                WordPressOutboundCredential(
                    id=f"credential-{suffix}",
                    project_id=project_id,
                    key_hash=hash_project_key("wpfx_concurrency"),
                    site_url=site_url,
                ),
            ]
        )
        session.commit()
        create_or_get_draft_job(session, proposal)
        session.commit()

    barrier = Barrier(2)

    def claim() -> tuple[str, str] | None:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            result = claim_next_draft_job(session, project_id, site_url)
            session.commit()
            return (
                (result.job.id, result.claim_token) if result is not None else None
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [future.result(timeout=10) for future in [
                executor.submit(claim),
                executor.submit(claim),
            ]]
        assert results.count(None) == 1
        claimed = next(value for value in results if value)
        assert claimed is not None
        job_id, claim_token = claimed

        terminal_barrier = Barrier(2)

        def complete() -> str:
            with Session(engine) as session:
                terminal_barrier.wait(timeout=10)
                try:
                    complete_draft_job(
                        session,
                        job_id,
                        claim_token,
                        wordpress_object_id=987,
                        wordpress_edit_url=None,
                    )
                    session.commit()
                    return "completed"
                except ValueError:
                    session.rollback()
                    return "rejected"

        def fail() -> str:
            with Session(engine) as session:
                terminal_barrier.wait(timeout=10)
                try:
                    fail_draft_job(
                        session,
                        job_id,
                        claim_token,
                        error_code="blueprint_drift",
                        error_message="Blueprint changed",
                    )
                    session.commit()
                    return "failed"
                except ValueError:
                    session.rollback()
                    return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            terminal_results = [
                future.result(timeout=10)
                for future in [executor.submit(complete), executor.submit(fail)]
            ]
        assert terminal_results.count("rejected") == 1
        assert set(terminal_results) & {"completed", "failed"}
    finally:
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if project is not None:
                session.delete(project)
                session.commit()
            organization = session.get(Organization, organization_id)
            if organization is not None:
                session.delete(organization)
                session.commit()
        engine.dispose()


def test_two_creators_receive_the_same_job() -> None:
    engine = create_engine(POSTGRES_TEST_URL, pool_size=4, max_overflow=0)
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:12]
    organization_id = f"create-org-{suffix}"
    project_id = f"create-project-{suffix}"
    proposal_id = f"create-proposal-{suffix}"
    site_url = f"https://{suffix}.example"

    with Session(engine) as session:
        session.add(Organization(id=organization_id, name="Create concurrency"))
        session.commit()
        session.add(
            Project(
                id=project_id,
                organization_id=organization_id,
                name="Create concurrency",
                domain=site_url,
            )
        )
        session.commit()
        source = WordPressPage(
            id=f"create-source-{suffix}",
            project_id=project_id,
            wordpress_object_id=820001,
            post_type="page",
            status="publish",
            title="Source",
            slug="source",
            url=f"{site_url}/source/",
        )
        opportunity = KeywordOpportunity(
            id=f"create-opportunity-{suffix}",
            project_id=project_id,
            keyword="create concurrency",
            location_code=2528,
            language_code="nl",
            target_classification="new_page",
            target_score=0,
            target_evidence=[],
            source="test",
            raw_payload={},
        )
        generation_job = Job(
            id=f"create-generation-{suffix}",
            project_id=project_id,
            job_type="page_package_generation",
        )
        session.add_all([source, opportunity, generation_job])
        session.commit()
        blueprint = PageBlueprint(
            id=f"create-blueprint-{suffix}",
            project_id=project_id,
            name="Service",
            page_type="service",
            source_wordpress_page_id=source.id,
            wordpress_blueprint_id=820002,
            builder="acf",
            seo_plugin="yoast",
            version=1,
            structure_hash=f"create-hash-{suffix}",
            content_schema=_schema(),
            state="ready",
            is_default_for_page_type=True,
        )
        session.add(blueprint)
        session.commit()
        session.add(
            PagePackageProposal(
                id=proposal_id,
                project_id=project_id,
                opportunity_id=opportunity.id,
                job_id=generation_job.id,
                state="approved",
                proposal_group_id=proposal_id,
                current_version_id=proposal_id,
                is_current=True,
                blueprint_id=blueprint.id,
                blueprint_version=1,
                blueprint_structure_hash=blueprint.structure_hash,
                package=_package(),
                rendered_html="",
                config_snapshot={"content_schema": _schema()},
                proposed_by="concurrency-test",
                approved_by="concurrency-test",
            )
        )
        session.commit()

    barrier = Barrier(2)

    def create() -> str:
        with Session(engine) as session:
            proposal = session.get(PagePackageProposal, proposal_id)
            assert proposal is not None
            barrier.wait(timeout=10)
            job = create_or_get_draft_job(session, proposal)
            session.commit()
            return job.id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create), executor.submit(create)]
            results = [future.result(timeout=10) for future in futures]
        assert results[0] == results[1]
    finally:
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if project is not None:
                session.delete(project)
                session.commit()
            organization = session.get(Organization, organization_id)
            if organization is not None:
                session.delete(organization)
                session.commit()
        engine.dispose()
