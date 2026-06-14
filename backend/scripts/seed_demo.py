from datetime import date, timedelta

from sqlalchemy import delete

from app.core.database import SessionLocal
from app.domains.audits.models import PageAudit
from app.domains.ga4.models import Ga4PagePerformance
from app.domains.gsc.models import GscPagePerformance
from app.domains.projects.models import (
    Organization,
    OrganizationMember,
    Profile,
    Project,
)
from app.domains.recommendations.models import CompanyProfile
from app.domains.wordpress.models import (
    WordPressChangeEvent,
    WordPressChangeProposal,
    WordPressPage,
)

USER_ID = "demo-user"
ORGANIZATION_ID = "org-member"
PROJECT_ID = "shm"
PAGE_ID = "demo-wp-revisie"


def seed() -> None:
    with SessionLocal() as session:
        session.execute(
            delete(WordPressChangeEvent).where(
                WordPressChangeEvent.project_id == PROJECT_ID
            )
        )
        session.execute(
            delete(WordPressChangeProposal).where(
                WordPressChangeProposal.project_id == PROJECT_ID
            )
        )
        session.merge(Profile(id=USER_ID, email="demo@wpfixpilot.local"))
        session.merge(
            Organization(
                id=ORGANIZATION_ID,
                name="WP FixPilot Demo",
            )
        )
        session.flush()
        session.merge(
            OrganizationMember(
                organization_id=ORGANIZATION_ID,
                profile_id=USER_ID,
                role="owner",
            )
        )
        session.merge(
            Project(
                id=PROJECT_ID,
                organization_id=ORGANIZATION_ID,
                name="SHM Transmissie",
                domain="https://shmtransmissie.nl",
            )
        )
        session.flush()
        session.merge(
            WordPressPage(
                id=PAGE_ID,
                project_id=PROJECT_ID,
                wordpress_object_id=42,
                post_type="page",
                status="publish",
                title="Revisie",
                slug="revisie",
                url="https://shmtransmissie.nl/revisie",
                content_hash="demo-base-hash",
            )
        )
        session.merge(
            CompanyProfile(
                project_id=PROJECT_ID,
                company_name="SHM Transmissie",
                description="Specialist in diagnose en transmissierevisie.",
                audience="Autobezitters met transmissieproblemen",
                services=["Diagnose", "Transmissierevisie", "Onderhoud"],
                tone_of_voice="Deskundig en duidelijk",
                custom_prompt="Gebruik alleen aantoonbare claims.",
            )
        )
        session.flush()
        session.merge(
            PageAudit(
                id="demo-audit-revisie",
                project_id=PROJECT_ID,
                wordpress_page_id=PAGE_ID,
                score=48,
                page_type_label="service",
                facts={"importance": 0.9},
            )
        )
        today = date.today()
        for suffix, offset, clicks, sessions, conversions in (
            ("old", 30, 180, 1800, 18),
            ("new", 5, 80, 1100, 3),
        ):
            performance_date = today - timedelta(days=offset)
            session.merge(
                GscPagePerformance(
                    id=f"demo-gsc-{suffix}",
                    project_id=PROJECT_ID,
                    property_uri="sc-domain:shmtransmissie.nl",
                    date=performance_date,
                    page_url="https://shmtransmissie.nl/revisie",
                    clicks=clicks,
                    impressions=10_000,
                    ctr=clicks / 10_000,
                    average_position=4.8,
                )
            )
            session.merge(
                Ga4PagePerformance(
                    id=f"demo-ga4-{suffix}",
                    project_id=PROJECT_ID,
                    property_id="demo-property",
                    date=performance_date,
                    page_path="/revisie",
                    sessions=sessions,
                    active_users=sessions - 100,
                    engagement_rate=0.58,
                    key_events=conversions,
                    revenue=None,
                )
            )
        session.merge(
            WordPressChangeProposal(
                id="demo-proposal",
                project_id=PROJECT_ID,
                wordpress_page_id=PAGE_ID,
                recommendation_id=None,
                change_type="seo_title",
                before_value="Oude SEO-title",
                after_value="Transmissie revisie door SHM Transmissie",
                base_content_hash="demo-base-hash",
                approval_state="proposed",
                proposed_by=USER_ID,
            )
        )
        session.commit()


if __name__ == "__main__":
    seed()
    print("Demo data seeded for project 'shm'.")
