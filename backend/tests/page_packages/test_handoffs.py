from sqlalchemy.orm import Session

from app.domains.page_packages.models import PagePackageHandoff
from app.domains.page_packages.service import issue_page_package_handoff
from app.domains.wordpress.models import WordPressConnection
from tests.page_packages.test_proposal_versions import page_proposal_factory
from tests.recommendations.conftest import ProjectFixtures


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
    session.commit()
    return proposal


def test_handoff_codes_are_stored_only_as_hashes(
    session: Session,
    projects: ProjectFixtures,
) -> None:
    proposal = approved_page_proposal(session, projects)

    handoff = issue_page_package_handoff(session, proposal, "user-1")

    assert handoff.raw_code is not None
    stored = session.get(PagePackageHandoff, handoff.record.id)
    assert stored is not None
    assert stored.code_hash != handoff.raw_code
    assert stored.state == "issued"
