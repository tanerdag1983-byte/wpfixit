import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.projects.models import Project
from app.domains.recommendations.models import CompanyProfile
from app.domains.wordpress.models import WordPressPage

BUSINESS_STOP_TOKENS = frozenset(
    {
        "aan",
        "auto",
        "automatische",
        "bedrijf",
        "bij",
        "contact",
        "de",
        "een",
        "en",
        "het",
        "in",
        "kosten",
        "met",
        "naar",
        "of",
        "om",
        "ons",
        "onze",
        "over",
        "pagina",
        "reparatie",
        "repareren",
        "reviseren",
        "revisie",
        "service",
        "site",
        "specialist",
        "voor",
        "vervangen",
        "wat",
        "website",
    }
)

PAGE_STOP_TOKENS = frozenset(
    {
        "aan",
        "auto",
        "bedrijf",
        "bij",
        "contact",
        "de",
        "een",
        "en",
        "het",
        "in",
        "kosten",
        "met",
        "naar",
        "of",
        "om",
        "ons",
        "onze",
        "over",
        "pagina",
        "service",
        "voor",
        "wat",
    }
)

MATCH_STOP_TOKENS = PAGE_STOP_TOKENS | frozenset(
    {
        "automaat",
        "automatische",
        "diagnose",
        "goedkoop",
        "onderhoud",
        "oplossing",
        "oplossingen",
        "probleem",
        "problemen",
        "reparatie",
        "repareren",
        "reviseren",
        "revisie",
        "specialist",
        "transmissie",
        "vervangen",
        "versnellingsbak",
    }
)


@dataclass(frozen=True)
class PageTopic:
    url: str
    phrases: tuple[str, ...]
    tokens: frozenset[str]


@dataclass(frozen=True)
class KeywordContext:
    seeds: tuple[str, ...]
    business_phrases: tuple[str, ...]
    business_tokens: frozenset[str]
    pages: tuple[PageTopic, ...]


@dataclass(frozen=True)
class PageMatch:
    classification: str
    url: str | None
    score: int
    evidence: tuple[str, ...]


def build_keyword_context(
    session: Session,
    project: Project,
    *,
    limit: int = 20,
) -> KeywordContext:
    profile = session.get(CompanyProfile, project.id)
    pages = session.scalars(
        select(WordPressPage)
        .where(WordPressPage.project_id == project.id)
        .order_by(WordPressPage.url)
    ).all()
    page_topics = tuple(_page_topic(page) for page in pages)
    all_page_phrases = [phrase for page in page_topics for phrase in page.phrases]

    service_phrases = _normalized_values(profile.services if profile else [])
    company_phrase = _normalize_phrase(
        profile.company_name if profile else project.name
    )
    fallback_phrases = _normalized_values(
        [profile.description, profile.audience] if profile else [project.name]
    )
    if service_phrases:
        anchor_sources = list(service_phrases)
    elif profile:
        anchor_sources = fallback_phrases + all_page_phrases
    else:
        anchor_sources = all_page_phrases + fallback_phrases
    if company_phrase:
        anchor_sources.append(company_phrase)
    business_tokens = frozenset(
        token
        for phrase in anchor_sources
        for token in _tokens(phrase)
        if token not in BUSINESS_STOP_TOKENS and len(token) >= 3
    )

    relevant_page_phrases = [
        phrase
        for page in page_topics
        if page.tokens & business_tokens
        for phrase in page.phrases
    ]
    seeds = _unique(service_phrases + relevant_page_phrases + fallback_phrases)

    return KeywordContext(
        seeds=tuple(seeds[:limit]),
        business_phrases=tuple(_unique(anchor_sources)),
        business_tokens=business_tokens,
        pages=page_topics,
    )


def is_relevant(keyword: str, context: KeywordContext) -> bool:
    candidate_tokens = frozenset(_tokens(keyword)) - BUSINESS_STOP_TOKENS
    page_tokens = frozenset(
        token
        for page in context.pages
        for token in page.tokens
        if token not in BUSINESS_STOP_TOKENS
    )
    return bool(candidate_tokens & (context.business_tokens | page_tokens))


def target_url(keyword: str, context: KeywordContext) -> str | None:
    return classify_target(keyword, context).url


def classify_target(keyword: str, context: KeywordContext) -> PageMatch:
    if not is_relevant(keyword, context):
        return PageMatch("new_page", None, 0, ("not_business_relevant",))

    normalized = _normalize_phrase(keyword)
    candidate_tokens = frozenset(_tokens(normalized))
    candidate_entities = candidate_tokens - context.business_tokens - MATCH_STOP_TOKENS
    candidate_bigrams = _bigrams(normalized)
    ranked: list[tuple[int, int, str, tuple[str, ...]]] = []

    for page in context.pages:
        exact_phrase = any(
            phrase
            and len(_tokens(phrase)) >= 2
            and (phrase in normalized or normalized in phrase)
            for phrase in page.phrases
        )
        shared_bigrams = candidate_bigrams & {
            bigram for phrase in page.phrases for bigram in _bigrams(phrase)
        }
        page_entities = page.tokens - context.business_tokens - MATCH_STOP_TOKENS
        entity_overlap = candidate_entities & page_entities

        if exact_phrase:
            ranked.append((100, 2, page.url, ("exact_phrase",)))
            continue
        if shared_bigrams:
            ranked.append(
                (
                    85 + min(10, len(shared_bigrams) * 2),
                    2,
                    page.url,
                    tuple(f"shared_phrase:{value}" for value in sorted(shared_bigrams)),
                )
            )
            continue
        if candidate_entities and candidate_entities.issubset(page_entities):
            ranked.append(
                (
                    75 + min(15, len(entity_overlap) * 5),
                    2,
                    page.url,
                    tuple(f"entity:{value}" for value in sorted(entity_overlap)),
                )
            )
            continue
        if entity_overlap:
            ranked.append(
                (
                    50 + min(10, len(entity_overlap) * 3),
                    1,
                    page.url,
                    tuple(
                        f"partial_entity:{value}" for value in sorted(entity_overlap)
                    ),
                )
            )

    if not ranked:
        return PageMatch("new_page", None, 0, ("no_distinctive_page_match",))

    score, strength, url, evidence = max(
        ranked,
        key=lambda item: (item[0], item[1], item[2]),
    )
    if strength == 2:
        return PageMatch("existing_page", url, score, evidence)
    return PageMatch("review", None, score, evidence)


def _page_topic(page: WordPressPage) -> PageTopic:
    phrases = _unique(_normalized_values([page.title, page.slug.replace("-", " ")]))
    return PageTopic(
        url=page.url,
        phrases=tuple(phrases),
        tokens=frozenset(
            token
            for phrase in phrases
            for token in _tokens(phrase)
            if token not in PAGE_STOP_TOKENS and len(token) >= 3
        ),
    )


def _normalized_values(values: Iterable[object]) -> list[str]:
    return _unique(
        phrase
        for value in values
        if (phrase := _normalize_phrase(value)) and len(_tokens(phrase)) >= 2
    )


def _normalize_phrase(value: object) -> str:
    return " ".join(_tokens(str(value or "")))


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def _bigrams(value: str) -> frozenset[str]:
    words = _tokens(value)
    return frozenset(
        f"{left} {right}" for left, right in zip(words, words[1:], strict=False)
    )


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
