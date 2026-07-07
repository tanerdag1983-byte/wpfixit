import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import encrypt_text
from app.domains.page_packages.models import (
    PagePackageHandoff,
    PagePackageRegenerationCandidate,
)
from app.domains.page_packages.service import issue_page_package_handoff
from app.domains.projects.models import OrganizationMember, Profile
from app.domains.wordpress.models import WordPressConnection
from tests.page_packages.test_proposal_versions import page_proposal_factory
from tests.recommendations.conftest import ProjectFixtures
from tests.recommendations.test_ai_connection_routes import ENCRYPTION_KEY


def _plugin_headers(
    secret: str,
    route: str,
    payload: dict | None = None,
) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    body = json.dumps(payload or {}, separators=(",", ":"), ensure_ascii=False)
    canonical = "\n".join(
        [
            "POST",
            route,
            timestamp,
            nonce,
            hashlib.sha256(body.encode()).hexdigest(),
        ]
    )
    signature = hmac.new(
        secret.encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "x-wp-fixpilot-timestamp": timestamp,
        "x-wp-fixpilot-nonce": nonce,
        "x-wp-fixpilot-signature": signature,
    }


def approved_page_proposal(
    session: Session,
    projects: ProjectFixtures,
):
    connection = session.get(WordPressConnection, "wp-member")
    if connection is None:
        connection = WordPressConnection(
            id="wp-member",
            project_id=projects.member_project.id,
            site_url="https://member.example",
            encrypted_secret="encrypted-secret",
            seo_plugin="yoast",
            health_state="healthy",
        )
        session.add(connection)
        session.commit()

    proposal = page_proposal_factory(
        session,
        projects,
        proposal_id="proposal-approved",
        state="approved",
        version_number=1,
        is_current=True,
    )
    proposal.approved_by = projects.member.id
    proposal.approved_at = datetime.now(UTC)
    session.commit()
    return proposal


def test_accept_candidate_revokes_previous_handoffs(
    client,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    current = approved_page_proposal(session, projects)
    issued_handoff = issue_page_package_handoff(session, current, projects.member.id)
    page_proposal_factory(
        session,
        projects,
        proposal_id="proposal-v0",
        state="failed",
        version_number=0,
        is_current=False,
        proposal_group_id=current.proposal_group_id,
        current_version_id=current.id,
    )
    session.add(
        PagePackageHandoff(
            id="handoff-other",
            project_id=current.project_id,
            proposal_version_id="proposal-v0",
            wordpress_connection_id="wp-member",
            code_hash="other",
            issued_by=projects.member.id,
            state="issued",
            expires_at=datetime.now(UTC),
        )
    )
    session.add(
        PagePackageRegenerationCandidate(
            id="candidate-1",
            proposal_group_id=current.proposal_group_id,
            base_version_id=current.id,
            generation_mode="block",
            target_block_id="faq",
            instruction="Maak de antwoorden concreter.",
            candidate_package={"title": "Nieuwe versie"},
            candidate_rendered_html="<h1>Nieuwe versie</h1>",
            status="ready",
        )
    )
    session.commit()

    response = client.post(
        f"/projects/{current.project_id}/page-proposals/candidates/candidate-1/accept"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_version"]["version_number"] == 2
    assert payload["current_version"]["state"] == "proposed"
    assert payload["revoked_handoff_ids"] == [issued_handoff.record.id]


def test_handoff_codes_are_stored_only_as_hashes(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    proposal = approved_page_proposal(session, projects)

    handoff = issue_page_package_handoff(session, proposal, projects.member.id)

    assert handoff.raw_code is not None
    stored = session.get(PagePackageHandoff, handoff.record.id)
    assert stored is not None
    assert stored.code_hash != handoff.raw_code
    assert stored.state == "issued"


def test_handoff_issuance_requires_owner_or_admin(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    proposal = approved_page_proposal(session, projects)
    same_org_member = Profile(id="user-member-basic", email="basic@example.com")
    session.add(same_org_member)
    session.commit()
    session.add(
        OrganizationMember(
            organization_id=projects.organization.id,
            profile_id=same_org_member.id,
            role="member",
        )
    )
    session.commit()

    try:
        issue_page_package_handoff(session, proposal, same_org_member.id)
    except PermissionError as error:
        assert str(error) == "Only organization owners or admins can issue handoffs"
    else:
        raise AssertionError("expected non-manager handoff issuance to be rejected")

    assert session.query(PagePackageHandoff).count() == 0


def test_handoff_issuance_rejects_missing_approval_metadata(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    proposal = approved_page_proposal(session, projects)
    proposal.approved_at = None
    session.commit()

    try:
        issue_page_package_handoff(session, proposal, projects.member.id)
    except ValueError as error:
        assert (
            str(error)
            == "Only the approved current proposal version can be handed off"
        )
    else:
        raise AssertionError("expected incomplete approval metadata to be rejected")

    assert session.query(PagePackageHandoff).count() == 0


def test_issue_redeem_complete_and_revoke_handoff_routes(
    client,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
    monkeypatch,
) -> None:
    monkeypatch.setattr(get_settings(), "encryption_key", ENCRYPTION_KEY)
    auth_as(projects.member)
    proposal = approved_page_proposal(session, projects)
    connection = session.get(WordPressConnection, "wp-member")
    assert connection is not None
    connection.encrypted_secret = encrypt_text("bridge-secret")
    session.commit()

    issue = client.post(
        f"/projects/{proposal.project_id}/page-proposals/{proposal.id}/handoffs"
    )

    assert issue.status_code == 200
    issued = issue.json()
    assert "#code=" in issued["import_url"]
    assert "code=" not in issued["import_url"].split("#", 1)[0]

    handoff = session.get(PagePackageHandoff, issued["handoff"]["id"])
    assert handoff is not None

    redeem_payload = {
        "code": issued["code"],
        "site_url": "https://member.example",
        "wordpress_user_id": 17,
    }
    redeem = client.post(
        f"/projects/{proposal.project_id}/page-proposals/handoffs/redeem",
        json=redeem_payload,
        headers=_plugin_headers(
            "bridge-secret",
            f"/projects/{proposal.project_id}/page-proposals/handoffs/redeem",
            redeem_payload,
        ),
    )

    assert redeem.status_code == 200
    redeemed = redeem.json()
    assert redeemed["handoff"]["state"] == "redeemed"
    assert redeemed["package"]["proposal_version_id"] == proposal.id

    complete_payload = {
        "wordpress_object_id": 20,
        "edit_url": "https://member.example/wp-admin/post.php?post=20",
    }
    complete_route = (
        f"/projects/{proposal.project_id}/page-proposals/handoffs/{handoff.id}/complete"
    )
    first_complete = client.post(
        complete_route,
        json=complete_payload,
        headers=_plugin_headers("bridge-secret", complete_route, complete_payload),
    )
    second_complete = client.post(
        complete_route,
        json=complete_payload,
        headers=_plugin_headers("bridge-secret", complete_route, complete_payload),
    )

    assert first_complete.status_code == 200
    assert second_complete.status_code == 200
    assert second_complete.json()["proposal_version"]["state"] == "draft_created"

    other = page_proposal_factory(
        session,
        projects,
        proposal_id="proposal-approved-2",
        state="approved",
        version_number=1,
        is_current=True,
        proposal_group_id="proposal-group-2",
        current_version_id="proposal-approved-2",
    )
    other.approved_by = projects.member.id
    other.approved_at = datetime.now(UTC)
    session.commit()

    revoke_issue = issue_page_package_handoff(session, other, projects.member.id)
    revoke_route = (
        f"/projects/{other.project_id}/page-proposals/handoffs/{revoke_issue.record.id}/revoke"
    )
    revoke = client.post(
        revoke_route,
        headers=_plugin_headers("bridge-secret", revoke_route, {}),
    )

    assert revoke.status_code == 200
    assert revoke.json()["handoff"]["state"] == "revoked"
