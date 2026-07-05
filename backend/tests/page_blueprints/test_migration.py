from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.page_blueprints.models import PageBlueprint
from app.domains.page_blueprints.service import legacy_blueprint_candidates
from app.domains.page_packages.models import ProjectPagePackageSettings


def test_legacy_page_package_becomes_capture_required_candidate(
    session: Session, projects
) -> None:
    legacy_settings = ProjectPagePackageSettings(
        project_id=projects.member_project.id,
        builder="acf",
        template_wordpress_page_id="source-page",
        seo_plugin="yoast",
        slot_mapping={"hero_title": "acf-block:hero/title"},
        template_content_hash="legacy-hash",
        validation_state="valid",
    )
    session.add(legacy_settings)
    session.commit()

    candidates = legacy_blueprint_candidates(session, legacy_settings.project_id)

    assert len(candidates) == 1
    assert (
        candidates[0].source_wordpress_page_id
        == legacy_settings.template_wordpress_page_id
    )
    assert candidates[0].state == "capture_required"
    assert legacy_settings.validation_state == "valid"
    assert session.scalar(select(func.count()).select_from(PageBlueprint)) == 0


def test_invalid_legacy_settings_do_not_create_candidate(
    session: Session, projects
) -> None:
    session.add(
        ProjectPagePackageSettings(
            project_id=projects.member_project.id,
            builder="acf",
            template_wordpress_page_id="source-page",
            seo_plugin="yoast",
            slot_mapping={},
            validation_state="invalid",
        )
    )
    session.commit()

    assert legacy_blueprint_candidates(session, projects.member_project.id) == []
