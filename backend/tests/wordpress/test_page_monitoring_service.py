from contextlib import nullcontext
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.domains.wordpress.models import (
    PageRecommendation,
    PageTimelineEvent,
    WordPressPage,
)
from app.domains.wordpress.monitoring import (
    check_page,
    record_page_version,
    score_page_version,
)


def page_facts(content_hash: str, *, canonical: str = "") -> dict:
    return {
        "content_hash": content_hash,
        "values": {
            "seo_title": "Transmissie revisie",
            "meta_description": (
                "Deskundige transmissie revisie met een heldere diagnose."
            ),
            "focus_keyword": "transmissie revisie",
            "canonical": canonical,
            "noindex": False,
            "content": (
                "<h1>Transmissie revisie</h1><h2>Onze aanpak</h2>"
                "<p>Wij onderzoeken uw auto zorgvuldig en leggen elke stap helder uit. "
                "Onze specialisten herstellen transmissies met aandacht voor "
                "kwaliteit.</p>"
                "<a href=\"/contact\">Neem contact op</a>"
                "<img src=\"transmissie.jpg\" alt=\"Transmissie revisie specialist\">"
            ),
            "featured_image_id": 12,
            "featured_image_alt": "Transmissie revisie specialist",
        },
    }


def make_page(session, projects) -> WordPressPage:
    page = WordPressPage(
        id="monitoring-service-page",
        project_id=projects.member_project.id,
        wordpress_object_id=702,
        post_type="page",
        status="publish",
        title="Transmissie revisie",
        slug="transmissie-revisie",
        url="https://member.example/transmissie-revisie",
        content_hash="hash-a",
    )
    session.add(page)
    session.commit()
    return page


def test_unchanged_hash_reuses_version_without_duplicate_recommendations(
    session, projects
) -> None:
    page = make_page(session, projects)
    facts = page_facts("hash-a")

    first = check_page(session, page, facts, trigger="sync")
    second = check_page(session, page, facts, trigger="manual")

    assert first.version.id == second.version.id
    assert first.recommendations_created == 1
    assert second.recommendations_created == 0
    assert (
        session.scalar(
            select(func.count(PageRecommendation.id)).where(
                PageRecommendation.page_version_id == first.version.id
            )
        )
        == 1
    )
    timeline_types = list(
        session.scalars(
            select(PageTimelineEvent.event_type).where(
                PageTimelineEvent.wordpress_page_id == page.id
            )
        )
    )
    assert timeline_types.count("recommendation_created") == 1
    assert timeline_types.count("page_checked") == 2


def test_changed_hash_creates_version_score_and_timeline(session, projects) -> None:
    page = make_page(session, projects)

    first = check_page(session, page, page_facts("hash-a"), trigger="sync")
    second = check_page(session, page, page_facts("hash-b"), trigger="sync")
    timeline_types = list(
        session.scalars(
            select(PageTimelineEvent.event_type)
            .where(PageTimelineEvent.wordpress_page_id == page.id)
            .order_by(PageTimelineEvent.created_at, PageTimelineEvent.id)
        )
    )

    assert first.version.id != second.version.id
    assert second.version_created is True
    assert second.score.factors[0]["explanation"]
    assert second.score.factors[0].keys() == {
        "key",
        "value",
        "points",
        "max_points",
        "explanation",
        "suggested_action",
        "evidence",
    }
    assert timeline_types[-1] == "page_checked"


def test_changed_hash_records_recommendations_per_version(session, projects) -> None:
    page = make_page(session, projects)

    first = check_page(session, page, page_facts("hash-a"), trigger="sync")
    second = check_page(session, page, page_facts("hash-b"), trigger="sync")

    assert first.recommendations_created == 1
    assert second.recommendations_created == 1
    assert session.scalar(select(func.count(PageRecommendation.id))) == 2
    states = list(
        session.scalars(
            select(PageRecommendation.state).order_by(PageRecommendation.created_at)
        )
    )
    assert states == ["superseded", "open"]


def test_clean_version_supersedes_historical_recommendations(
    session, projects
) -> None:
    page = make_page(session, projects)

    first = check_page(session, page, page_facts("hash-a"), trigger="sync")
    second = check_page(
        session,
        page,
        page_facts("hash-b", canonical="https://member.example/transmissie-revisie"),
        trigger="sync",
    )

    recommendation = session.scalar(select(PageRecommendation))
    assert first.recommendations_created == 1
    assert second.recommendations_created == 0
    assert recommendation is not None
    assert recommendation.state == "superseded"


def test_builder_payload_contributes_to_page_score(session, projects) -> None:
    page = make_page(session, projects)
    facts = page_facts("builder-hash")
    facts["values"]["content"] = ""
    facts["values"]["builders"] = {
        "elementor": {
            "meta": {
                "_elementor_data": (
                    '[{"settings":{"editor":"<h1>Transmissie revisie</h1>'
                    '<p>Onze specialisten verzorgen transmissie revisie.</p>"}}]'
                )
            }
        },
        "bricks": {
            "meta": {
                "_bricks_page_content_2": [
                    {"settings": {"text": '<a href="/contact">Contact</a>'}}
                ]
            }
        },
        "acf": {
            "meta": {
                "hero_image": '<img src="revisie.jpg" alt="Transmissie revisie">'
            }
        },
    }
    facts["values"]["featured_image_id"] = 0

    result = check_page(session, page, facts, trigger="sync")
    factors = {factor["key"]: factor for factor in result.score.factors}

    assert factors["headings"]["points"] == 10
    assert factors["keyword_coverage"]["points"] == 10
    assert factors["links"]["points"] == 10
    assert factors["images"]["points"] == 10


def test_qualifying_inline_image_succeeds_when_featured_presence_is_unknown(
    session, projects
) -> None:
    page = make_page(session, projects)
    facts = page_facts("hash-a")
    del facts["values"]["featured_image_id"]

    result = check_page(session, page, facts, trigger="sync")
    image_factor = next(
        factor for factor in result.score.factors if factor["key"] == "images"
    )

    assert image_factor["max_points"] == 10
    assert image_factor["points"] == 10
    assert image_factor["suggested_action"] == ""


def test_featured_unknown_with_text_only_inline_is_neutral(
    session, projects
) -> None:
    page = make_page(session, projects)
    facts = page_facts("hash-a")
    del facts["values"]["featured_image_id"]
    facts["values"]["content"] = "<p>Text-only content.</p>"

    result = check_page(session, page, facts, trigger="sync")
    image_factor = next(
        factor for factor in result.score.factors if factor["key"] == "images"
    )

    assert image_factor["max_points"] == 0
    assert image_factor["points"] == 0
    assert image_factor["suggested_action"] == ""


def test_featured_image_with_unknown_alt_is_neutral(session, projects) -> None:
    page = make_page(session, projects)
    facts = page_facts("hash-a")
    del facts["values"]["featured_image_alt"]
    facts["values"]["content"] = "<p>Text-only content.</p>"

    result = check_page(session, page, facts, trigger="sync")
    image_factor = next(
        factor for factor in result.score.factors if factor["key"] == "images"
    )

    assert image_factor["max_points"] == 0
    assert image_factor["points"] == 0
    assert image_factor["suggested_action"] == ""


def test_known_absent_featured_image_with_unknown_inline_is_neutral(
    session, projects
) -> None:
    page = make_page(session, projects)
    facts = page_facts("hash-a")
    facts["values"]["featured_image_id"] = 0
    del facts["values"]["content"]

    result = check_page(session, page, facts, trigger="sync")
    image_factor = next(
        factor for factor in result.score.factors if factor["key"] == "images"
    )

    assert image_factor["max_points"] == 0
    assert image_factor["points"] == 0
    assert image_factor["suggested_action"] == ""


def test_both_known_absent_image_paths_are_actionable(session, projects) -> None:
    page = make_page(session, projects)
    facts = page_facts("hash-a")
    facts["values"]["featured_image_id"] = 0
    facts["values"]["content"] = "<p>Text-only content.</p>"

    result = check_page(session, page, facts, trigger="sync")
    image_factor = next(
        factor for factor in result.score.factors if factor["key"] == "images"
    )

    assert image_factor["max_points"] == 10
    assert image_factor["points"] == 0
    assert image_factor["suggested_action"]


def test_qualifying_inline_image_succeeds_when_featured_is_absent(
    session, projects
) -> None:
    page = make_page(session, projects)
    facts = page_facts("hash-a")
    facts["values"]["featured_image_id"] = 0

    result = check_page(session, page, facts, trigger="sync")
    image_factor = next(
        factor for factor in result.score.factors if factor["key"] == "images"
    )

    assert image_factor["max_points"] == 10
    assert image_factor["points"] == 10
    assert image_factor["suggested_action"] == ""


def test_known_empty_featured_image_alt_with_nonqualifying_inline_is_actionable(
    session, projects
) -> None:
    page = make_page(session, projects)
    facts = page_facts("hash-a")
    facts["values"]["featured_image_alt"] = ""
    facts["values"]["content"] = "<p>Text-only content.</p>"

    result = check_page(session, page, facts, trigger="sync")
    image_factor = next(
        factor for factor in result.score.factors if factor["key"] == "images"
    )

    assert image_factor["max_points"] == 10
    assert image_factor["points"] == 0
    assert image_factor["suggested_action"]


def test_known_featured_image_alt_receives_full_points(session, projects) -> None:
    page = make_page(session, projects)
    facts = page_facts("hash-a")
    del facts["values"]["content"]

    result = check_page(session, page, facts, trigger="sync")
    image_factor = next(
        factor for factor in result.score.factors if factor["key"] == "images"
    )

    assert image_factor["max_points"] == 10
    assert image_factor["points"] == 10
    assert image_factor["suggested_action"] == ""


def test_historical_title_never_reads_mutable_page_title(session, projects) -> None:
    page = make_page(session, projects)
    facts = page_facts("hash-a")
    del facts["values"]["seo_title"]

    version, created = record_page_version(session, page, facts, source="sync")
    page.title = "A mutable replacement title"
    score = score_page_version(version)
    title_factor = next(factor for factor in score.factors if factor["key"] == "title")

    assert created is True
    assert title_factor["max_points"] == 0
    assert title_factor["suggested_action"] == ""


def test_conflict_recovery_binds_lineage_to_existing_version(
    session, projects, monkeypatch
) -> None:
    page = make_page(session, projects)
    facts = page_facts("race-hash")
    published_at = datetime(2026, 8, 7, 10, tzinfo=UTC)
    existing = record_page_version(
        session,
        page,
        page_facts("existing-hash"),
        source="sync",
    )[0]
    versions = iter([None, existing])

    monkeypatch.setattr(
        "app.domains.wordpress.monitoring._page_version",
        lambda *_args: next(versions),
    )
    monkeypatch.setattr(session, "begin_nested", nullcontext)
    monkeypatch.setattr(
        session,
        "flush",
        lambda: (_ for _ in ()).throw(
            IntegrityError("duplicate version", {}, RuntimeError("unique"))
        ),
    )

    version, created = record_page_version(
        session,
        page,
        facts,
        source="draft",
        proposal_version_id="proposal-race",
        draft_job_id="draft-race",
        published_at=published_at,
    )

    assert created is False
    assert version is existing
    assert version.proposal_version_id == "proposal-race"
    assert version.draft_job_id == "draft-race"
    assert version.published_at == published_at
