from datetime import UTC, datetime, timedelta

import pytest

from app.domains.dataforseo.models import KeywordOpportunity
from app.domains.jobs.models import Job
from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_packages.models import PagePackageHandoff, PagePackageProposal
from app.domains.wordpress.draft_jobs import (
    cancel_ineligible_draft_jobs,
    claim_next_draft_job,
    complete_draft_job,
    create_or_get_draft_job,
    fail_draft_job,
    hash_project_key,
)
from app.domains.wordpress.models import (
    WordPressConnection,
    WordPressDraftJob,
    WordPressOutboundCredential,
    WordPressPage,
)


def _schema() -> dict:
    return {
        "schema_version": "blueprint-v1",
        "blocks": [
            {
                "id": "hero",
                "layout": "hero_algemeen",
                "label": "Hero",
                "semantic_role": "hero",
                "fields": [
                    {
                        "id": "acf-title",
                        "path": "page_blocks/0/title",
                        "label": "Titel",
                        "value_type": "heading",
                        "current_value": "Transmissie revisie",
                        "required": True,
                        "max_length": 180,
                    },
                    {
                        "id": "acf-cta-url",
                        "path": "page_blocks/0/button_url",
                        "label": "CTA URL",
                        "value_type": "url",
                        "current_value": "/contact/",
                        "required": True,
                        "max_length": 2048,
                    },
                ],
            }
        ],
    }


def _package() -> dict:
    return {
        "title": "DSG revisie specialist Schiedam",
        "slug": "dsg-revisie-schiedam",
        "seo_title": "DSG revisie Schiedam door een specialist",
        "meta_description": (
            "Laat uw DSG onderzoeken en gericht reviseren door SHM Transmissie "
            "in Schiedam met een duidelijk advies vooraf."
        ),
        "focus_keyword": "dsg revisie schiedam",
        "replacements": [
            {"field_id": "acf-title", "value": "DSG revisie Schiedam"},
            {"field_id": "acf-cta-url", "value": "/contact/"},
        ],
        "internal_links": [],
    }


@pytest.fixture
def approved_blueprint_proposal(session, projects) -> PagePackageProposal:
    project = projects.member_project
    source = WordPressPage(
        id="draft-job-source",
        project_id=project.id,
        wordpress_object_id=902,
        post_type="page",
        status="publish",
        title="Diensttemplate",
        slug="diensttemplate",
        url="https://member.example/diensttemplate/",
    )
    blueprint = PageBlueprint(
        id="draft-job-blueprint",
        project_id=project.id,
        name="Dienstpagina",
        page_type="service",
        source_wordpress_page_id=source.id,
        wordpress_blueprint_id=902,
        builder="acf",
        seo_plugin="yoast",
        version=2,
        structure_hash="structure-v2",
        content_schema=_schema(),
        state="ready",
        is_default_for_page_type=True,
    )
    opportunity = KeywordOpportunity(
        id="draft-job-service-opportunity",
        project_id=project.id,
        keyword="dsg versnellingsbak reviseren",
        location_code=2528,
        language_code="nl",
        target_classification="new_page",
        target_score=0,
        target_evidence=[],
        source="dataforseo",
        raw_payload={},
    )
    generation_job = Job(
        id="draft-job-service-generation",
        project_id=project.id,
        job_type="page_package_generation",
    )
    proposal = PagePackageProposal(
        id="approved-blueprint-proposal",
        project_id=project.id,
        opportunity_id=opportunity.id,
        job_id=generation_job.id,
        proposal_group_id="approved-blueprint-proposal",
        current_version_id="approved-blueprint-proposal",
        is_current=True,
        state="approved",
        blueprint_id=blueprint.id,
        blueprint_version=blueprint.version,
        blueprint_structure_hash=blueprint.structure_hash,
        package=_package(),
        rendered_html="",
        config_snapshot={"content_schema": _schema()},
        proposed_by=projects.member.id,
        approved_by=projects.member.id,
        approved_at=datetime.now(UTC),
    )
    credential = WordPressOutboundCredential(
        id="draft-job-credential",
        project_id=project.id,
        key_hash=hash_project_key("wpfx_test"),
        site_url="https://member.example",
    )
    session.add_all(
        [source, blueprint, opportunity, generation_job, proposal, credential]
    )
    session.commit()
    return proposal


def test_create_or_get_job_is_idempotent(session, approved_blueprint_proposal) -> None:
    first = create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()
    second = create_or_get_draft_job(session, approved_blueprint_proposal)

    assert first.id == second.id
    assert first.payload_hash == second.payload_hash
    assert first.payload["wordpress_blueprint_id"] == 902
    assert first.payload["expected_version"] == 2
    assert first.payload["replacements"]["acf-title"] == "DSG revisie Schiedam"
    assert first.payload["approved_urls"] == ["/contact/"]


def test_create_job_revokes_an_expired_redeemed_manual_handoff(
    session, approved_blueprint_proposal
) -> None:
    connection = WordPressConnection(
        id="draft-job-connection",
        project_id=approved_blueprint_proposal.project_id,
        site_url="https://member.example",
        encrypted_secret="encrypted",
    )
    handoff = PagePackageHandoff(
        id="expired-redeemed-handoff",
        project_id=approved_blueprint_proposal.project_id,
        proposal_version_id=approved_blueprint_proposal.id,
        wordpress_connection_id=connection.id,
        code_hash="expired-redeemed-handoff-hash",
        issued_by="member-user",
        state="redeemed",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        redeemed_at=datetime.now(UTC) - timedelta(minutes=2),
    )
    session.add_all([connection, handoff])
    session.commit()

    job = create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()

    assert job.state == "queued"
    assert handoff.state == "revoked"
    assert handoff.revoked_at is not None


def test_create_job_keeps_an_active_redeemed_manual_handoff(
    session, approved_blueprint_proposal
) -> None:
    connection = WordPressConnection(
        id="active-draft-job-connection",
        project_id=approved_blueprint_proposal.project_id,
        site_url="https://member.example",
        encrypted_secret="encrypted",
    )
    handoff = PagePackageHandoff(
        id="active-redeemed-handoff",
        project_id=approved_blueprint_proposal.project_id,
        proposal_version_id=approved_blueprint_proposal.id,
        wordpress_connection_id=connection.id,
        code_hash="active-redeemed-handoff-hash",
        issued_by="member-user",
        state="redeemed",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        redeemed_at=datetime.now(UTC),
    )
    session.add_all([connection, handoff])
    session.commit()

    with pytest.raises(ValueError, match="manual handoff is already in progress"):
        create_or_get_draft_job(session, approved_blueprint_proposal)

    assert handoff.state == "redeemed"
    assert handoff.revoked_at is None


def test_create_job_rejects_non_current_or_unapproved_proposal(
    session, approved_blueprint_proposal
) -> None:
    approved_blueprint_proposal.is_current = False
    approved_blueprint_proposal.current_version_id = "replacement-version"

    with pytest.raises(ValueError, match="current approved"):
        create_or_get_draft_job(session, approved_blueprint_proposal)


def test_claim_complete_and_replay_return_one_result(
    session, approved_blueprint_proposal
) -> None:
    job = create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()

    claimed = claim_next_draft_job(
        session, job.project_id, "https://member.example:443"
    )
    assert claimed is not None
    assert claimed.job.id == job.id
    assert claimed.job.state == "claimed"

    completed = complete_draft_job(
        session,
        claimed.job.id,
        claimed.claim_token,
        wordpress_object_id=987,
        wordpress_edit_url=(
            "https://member.example/wp-admin/post.php?post=987&action=edit"
        ),
    )
    replay = complete_draft_job(
        session,
        claimed.job.id,
        claimed.claim_token,
        wordpress_object_id=987,
        wordpress_edit_url=completed.wordpress_edit_url,
    )

    assert replay.id == completed.id
    assert replay.state == "completed"
    assert replay.wordpress_object_id == 987
    assert replay.claim_token is None


def test_expired_claim_is_reclaimed_with_a_new_token(
    session, approved_blueprint_proposal
) -> None:
    job = create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()
    first = claim_next_draft_job(session, job.project_id, "https://member.example")
    assert first is not None
    first_token = first.claim_token
    first.job.claim_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()

    second = claim_next_draft_job(session, job.project_id, "https://member.example")

    assert second is not None
    assert second.job.id == job.id
    assert second.claim_token != first_token
    assert second.job.attempt_count == 2


def test_cancel_ineligible_jobs_cancels_queued_job(
    session, approved_blueprint_proposal
) -> None:
    job = create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()

    cancelled = cancel_ineligible_draft_jobs(
        session,
        approved_blueprint_proposal.project_id,
        approved_blueprint_proposal.proposal_group_id,
        eligible_proposal_version_id="replacement-version",
    )

    assert cancelled == 1
    assert job.state == "cancelled"
    assert job.cancelled_at is not None
    assert session.query(WordPressDraftJob).count() == 1


def test_cancel_ineligible_jobs_keeps_completed_job_immutable(
    session, approved_blueprint_proposal
) -> None:
    job = create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()
    claimed = claim_next_draft_job(session, job.project_id, "https://member.example")
    assert claimed is not None
    complete_draft_job(
        session,
        job.id,
        claimed.claim_token,
        wordpress_object_id=987,
        wordpress_edit_url=None,
    )

    cancelled = cancel_ineligible_draft_jobs(
        session,
        approved_blueprint_proposal.project_id,
        approved_blueprint_proposal.proposal_group_id,
        eligible_proposal_version_id="replacement-version",
    )

    assert cancelled == 0
    assert job.state == "completed"


def test_cancel_ineligible_jobs_leaves_claimed_job_completable(
    session, approved_blueprint_proposal
) -> None:
    job = create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()
    claimed = claim_next_draft_job(session, job.project_id, "https://member.example")
    assert claimed is not None

    cancelled = cancel_ineligible_draft_jobs(
        session,
        approved_blueprint_proposal.project_id,
        approved_blueprint_proposal.proposal_group_id,
        eligible_proposal_version_id="replacement-version",
    )
    completed = complete_draft_job(
        session,
        job.id,
        claimed.claim_token,
        wordpress_object_id=987,
        wordpress_edit_url=None,
    )

    assert cancelled == 0
    assert completed.state == "completed"
    assert approved_blueprint_proposal.state == "draft_created"


def test_claim_rejects_another_wordpress_site(
    session, approved_blueprint_proposal
) -> None:
    create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()

    with pytest.raises(ValueError, match="credential_invalid"):
        claim_next_draft_job(
            session,
            approved_blueprint_proposal.project_id,
            "https://other.example",
        )


def test_expired_claim_cannot_complete(session, approved_blueprint_proposal) -> None:
    job = create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()
    claimed = claim_next_draft_job(session, job.project_id, "https://member.example")
    assert claimed is not None

    with pytest.raises(ValueError, match="claim_invalid"):
        complete_draft_job(
            session,
            job.id,
            claimed.claim_token,
            wordpress_object_id=987,
            wordpress_edit_url=None,
            now=claimed.job.claim_expires_at + timedelta(seconds=1),
        )


def test_fail_and_replay_preserve_one_terminal_result(
    session, approved_blueprint_proposal
) -> None:
    job = create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()
    claimed = claim_next_draft_job(session, job.project_id, "https://member.example")
    assert claimed is not None

    failed = fail_draft_job(
        session,
        job.id,
        claimed.claim_token,
        error_code="blueprint_drift",
        error_message="Blueprint changed",
    )
    replay = fail_draft_job(
        session,
        job.id,
        claimed.claim_token,
        error_code="blueprint_drift",
        error_message="Blueprint changed",
    )

    assert replay.id == failed.id
    assert replay.state == "failed"
    assert replay.claim_token is None

    with pytest.raises(ValueError, match="claim_invalid"):
        fail_draft_job(
            session,
            job.id,
            "different-claim-token-with-valid-length",
            error_code="blueprint_drift",
            error_message="Blueprint changed",
        )


def test_failure_rejects_oversized_error_fields(
    session, approved_blueprint_proposal
) -> None:
    job = create_or_get_draft_job(session, approved_blueprint_proposal)
    session.commit()
    claimed = claim_next_draft_job(session, job.project_id, "https://member.example")
    assert claimed is not None

    with pytest.raises(ValueError, match="error_code_invalid"):
        fail_draft_job(
            session,
            job.id,
            claimed.claim_token,
            error_code="x" * 65,
            error_message="Failure",
        )
    with pytest.raises(ValueError, match="error_message_invalid"):
        fail_draft_job(
            session,
            job.id,
            claimed.claim_token,
            error_code="unknown_field",
            error_message="x" * 501,
        )


def test_job_payload_rejects_url_not_in_blueprint_or_project(
    session, approved_blueprint_proposal
) -> None:
    package = dict(approved_blueprint_proposal.package)
    package["replacements"] = [
        {"field_id": "acf-title", "value": "DSG revisie Schiedam"},
        {"field_id": "acf-cta-url", "value": "https://outside.example/"},
    ]
    approved_blueprint_proposal.package = package

    with pytest.raises(ValueError, match="URL is not approved"):
        create_or_get_draft_job(session, approved_blueprint_proposal)
