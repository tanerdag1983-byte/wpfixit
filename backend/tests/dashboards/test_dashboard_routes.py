from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.audits.models import PageAudit, SeoRecommendation
from app.domains.wordpress.models import WordPressPage
from tests.projects.conftest import ProjectFixtures


def test_dashboard_combines_search_and_all_filters(
    client: TestClient,
    session: Session,
    auth_as,
    projects: ProjectFixtures,
) -> None:
    auth_as(projects.member)
    page = WordPressPage(
        id=str(uuid4()),
        project_id=projects.member_project.id,
        wordpress_object_id=10,
        post_type="page",
        status="publish",
        title="Transmissie revisie",
        slug="revisie",
        url="https://member.example/revisie",
    )
    ignored_page = WordPressPage(
        id=str(uuid4()),
        project_id=projects.member_project.id,
        wordpress_object_id=11,
        post_type="post",
        status="draft",
        title="Nieuws",
        slug="nieuws",
        url="https://member.example/nieuws",
    )
    session.add_all([page, ignored_page])
    session.flush()
    session.add_all(
        [
            PageAudit(
                id=str(uuid4()),
                project_id=projects.member_project.id,
                wordpress_page_id=page.id,
                score=55,
                page_type_label="service",
                facts={},
            ),
            PageAudit(
                id=str(uuid4()),
                project_id=projects.member_project.id,
                wordpress_page_id=ignored_page.id,
                score=40,
                page_type_label="blog",
                facts={},
            ),
            SeoRecommendation(
                id=str(uuid4()),
                project_id=projects.member_project.id,
                wordpress_page_id=page.id,
                action_type="seo_title",
                priority="high",
                recommendation="Verbeter de title.",
                evidence={},
            ),
        ]
    )
    session.commit()

    response = client.get(
        f"/projects/{projects.member_project.id}/dashboard-overview",
        params={
            "q": "revisie",
            "priority": "high",
            "page_type": "service",
            "status": "publish",
            "max_score": 70,
        },
    )

    assert response.status_code == 200
    assert [item["url"] for item in response.json()["pages"]] == [
        "https://member.example/revisie"
    ]
    assert all(item["priority"] == "high" for item in response.json()["pages"])
