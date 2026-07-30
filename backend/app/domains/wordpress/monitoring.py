import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.domains.recommendations.models import CompanyProfile
from app.domains.wordpress.draft_jobs import hash_draft_job_payload
from app.domains.wordpress.models import (
    PageObservedVersion,
    PageRecommendation,
    PageScoreSnapshot,
    PageTimelineEvent,
    WordPressPage,
)


@dataclass(frozen=True)
class PageCheckResult:
    version: PageObservedVersion
    version_created: bool
    score: PageScoreSnapshot
    recommendations_created: int


def record_page_version(
    session: Session,
    page: WordPressPage,
    facts: dict,
    *,
    source: str,
    proposal_version_id: str | None = None,
    draft_job_id: str | None = None,
) -> tuple[PageObservedVersion, bool]:
    content_hash = facts.get("content_hash")
    if not isinstance(content_hash, str) or not content_hash or len(content_hash) > 128:
        raise ValueError("page monitoring content hash invalid")
    if not source or len(source) > 32:
        raise ValueError("page monitoring source invalid")

    version = session.scalar(
        select(PageObservedVersion).where(
            PageObservedVersion.wordpress_page_id == page.id,
            PageObservedVersion.content_hash == content_hash,
        )
    )
    if version is not None:
        return version, False

    page.content_hash = content_hash
    version = PageObservedVersion(
        id=f"pver_{uuid4().hex}",
        project_id=page.project_id,
        wordpress_page_id=page.id,
        content_hash=content_hash,
        source=source,
        snapshot_payload=facts,
        proposal_version_id=proposal_version_id,
        draft_job_id=draft_job_id,
    )
    session.add(version)
    session.flush()
    return version, True


def score_page_version(version: PageObservedVersion) -> PageScoreSnapshot:
    session = object_session(version)
    if session is None:
        raise ValueError("page version must be attached to a session")
    score, _ = _score_for_version(session, version)
    return score


def check_page(
    session: Session,
    page: WordPressPage,
    facts: dict,
    *,
    trigger: str,
) -> PageCheckResult:
    profile = session.get(CompanyProfile, page.project_id)
    snapshot_facts = dict(facts)
    if profile is not None:
        snapshot_facts["company_profile"] = {
            "company_name": profile.company_name,
            "services": profile.services,
        }
    version, version_created = record_page_version(
        session,
        page,
        snapshot_facts,
        source=trigger,
    )
    score, score_created = _score_for_version(session, version)
    recommendations_created = _record_recommendations(session, version, score.factors)
    if version_created:
        session.add(
            PageTimelineEvent(
                id=f"ptimeline_{uuid4().hex}",
                project_id=page.project_id,
                wordpress_page_id=page.id,
                page_version_id=version.id,
                event_type="version_observed",
                payload={"content_hash": version.content_hash, "trigger": trigger},
                created_at=datetime.now(UTC),
            )
        )
    if score_created:
        session.add(
            PageTimelineEvent(
                id=f"ptimeline_{uuid4().hex}",
                project_id=page.project_id,
                wordpress_page_id=page.id,
                page_version_id=version.id,
                event_type="score_created",
                payload={"overall_score": score.overall_score, "trigger": trigger},
                created_at=datetime.now(UTC),
            )
        )
    session.flush()
    return PageCheckResult(
        version=version,
        version_created=version_created,
        score=score,
        recommendations_created=recommendations_created,
    )


def _score_for_version(
    session: Session, version: PageObservedVersion
) -> tuple[PageScoreSnapshot, bool]:
    existing = session.scalar(
        select(PageScoreSnapshot).where(PageScoreSnapshot.page_version_id == version.id)
    )
    if existing is not None:
        return existing, False

    page = session.get(WordPressPage, version.wordpress_page_id)
    if page is None:
        raise ValueError("page version source page not found")
    factors = _score_factors(page, version.snapshot_payload)
    maximum = sum(factor["max_points"] for factor in factors)
    overall_score = round(100 * sum(factor["points"] for factor in factors) / maximum)
    score = PageScoreSnapshot(
        id=f"pscore_{uuid4().hex}",
        page_version_id=version.id,
        overall_score=overall_score,
        factors=factors,
    )
    session.add(score)
    session.flush()
    return score, True


def _score_factors(page: WordPressPage, facts: dict) -> list[dict]:
    values = facts.get("values") if isinstance(facts.get("values"), dict) else {}
    content = _text(values.get("content"))
    plain_content = _plain_text(content)
    title = _text(values.get("seo_title")) or page.title
    meta_description = _text(values.get("meta_description"))
    keyword = _text(values.get("focus_keyword")).casefold()
    canonical = _text(values.get("canonical"))
    has_headings = bool(re.search(r"<h[12][\s>]", content, re.IGNORECASE))
    link_count = len(re.findall(r"<a\s[^>]*href=[\"']", content, re.IGNORECASE))
    images = re.findall(r"<img\s[^>]*>", content, re.IGNORECASE)
    alt_count = sum(
        bool(re.search(r"\balt=[\"'][^\"']+", image, re.IGNORECASE))
        for image in images
    )
    words = re.findall(r"[\w'-]+", plain_content)
    sentences = [part for part in re.split(r"[.!?]+", plain_content) if part.strip()]
    readable = bool(words) and (not sentences or len(words) / len(sentences) <= 25)
    keyword_covered = bool(keyword) and keyword in " ".join(
        (title, meta_description, plain_content)
    ).casefold()
    profile = facts.get("company_profile")
    profile_terms = []
    if isinstance(profile, dict):
        profile_terms = [
            _text(term).casefold()
            for term in [profile.get("company_name"), *(profile.get("services") or [])]
            if _text(term)
        ]
    profile_matches = any(term in plain_content.casefold() for term in profile_terms)

    return [
        _factor("title", title, bool(title), "Add a descriptive page title."),
        _factor(
            "meta_description",
            meta_description,
            50 <= len(meta_description) <= 160,
            "Add a meta description between 50 and 160 characters.",
        ),
        _factor("headings", has_headings, has_headings, "Add a page heading."),
        _factor(
            "indexability",
            values.get("noindex") is not True,
            values.get("noindex") is not True,
            "Allow search engines to index this page.",
        ),
        _factor("canonical", canonical, bool(canonical), "Set the canonical URL."),
        _factor(
            "keyword_coverage",
            keyword,
            keyword_covered,
            "Use the focus keyword in the page copy.",
        ),
        _factor(
            "readability",
            {"word_count": len(words), "sentence_count": len(sentences)},
            readable,
            "Shorten long sentences for easier reading.",
        ),
        _factor("links", link_count, link_count > 0, "Add a relevant internal link."),
        _factor(
            "images",
            {
                "featured": bool(values.get("featured_image_id")),
                "in_page": len(images),
                "with_alt": alt_count,
            },
            (bool(values.get("featured_image_id")) or bool(images))
            and alt_count == len(images),
            "Add a featured or in-page image with descriptive alt text.",
        ),
        _factor(
            "company_profile",
            profile_terms,
            profile_matches,
            "Mention a relevant company service on this page.",
            max_points=10 if profile_terms else 0,
        ),
    ]


def _factor(
    key: str,
    value: object,
    passes: bool,
    suggested_action: str,
    *,
    max_points: int = 10,
) -> dict:
    return {
        "key": key,
        "value": value,
        "points": max_points if passes else 0,
        "max_points": max_points,
        "explanation": (
            f"{key.replace('_', ' ').capitalize()} is present."
            if passes
            else f"{key.replace('_', ' ').capitalize()} needs attention."
        ),
        "suggested_action": "" if passes else suggested_action,
        "evidence": {"value": value},
    }


def _record_recommendations(
    session: Session, version: PageObservedVersion, factors: list[dict]
) -> int:
    created = 0
    for factor in factors:
        if factor["points"] == factor["max_points"] or not factor["suggested_action"]:
            continue
        fingerprint = hash_draft_job_payload(
            {
                "key": factor["key"],
                "evidence": factor["evidence"],
                "suggested_action": factor["suggested_action"],
            }
        )
        existing = session.scalar(
            select(PageRecommendation).where(
                PageRecommendation.page_version_id == version.id,
                PageRecommendation.fingerprint == fingerprint,
            )
        )
        if existing is None:
            session.add(
                PageRecommendation(
                    id=f"prec_{uuid4().hex}",
                    page_version_id=version.id,
                    fingerprint=fingerprint,
                    state="open",
                    evidence=factor["evidence"],
                    suggested_action=factor["suggested_action"],
                )
            )
            created += 1
    return created


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _plain_text(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)
