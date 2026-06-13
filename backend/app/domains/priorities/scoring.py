from dataclasses import dataclass, field
from math import log10


@dataclass(frozen=True)
class PageSignals:
    url: str
    seo_score: int = 100
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0
    average_position: float = 0
    sessions: int = 0
    conversions: int = 0
    trend: float = 0
    importance: float = 0.5
    issue_severity: float = 0


@dataclass(frozen=True)
class PriorityResult:
    url: str
    priority_score: int
    confidence: float
    action: str
    components: dict[str, float] = field(default_factory=dict)
    signals: PageSignals | None = None


def _volume(value: int, ceiling: int) -> float:
    if value <= 0:
        return 0
    return min(1, log10(value + 1) / log10(ceiling + 1))


def _action(components: dict[str, float]) -> str:
    strongest = max(components, key=components.get)
    actions = {
        "audit": "Los eerst de technische en on-page SEO-fouten op.",
        "gsc_ctr": "Verbeter title en meta description om de CTR te verhogen.",
        "ranking": "Versterk content en interne links voor zoektermen op pagina 1-2.",
        "conversion": (
            "Verbeter propositie, CTA en conversiepad op deze landingspagina."
        ),
        "trend": "Onderzoek de prestatiedaling en vergelijk recente wijzigingen.",
        "importance": "Behandel deze belangrijke pagina met voorrang.",
        "confidence": (
            "Verzamel ontbrekende databronnen voor een betrouwbaarder advies."
        ),
    }
    return actions[strongest]


def score_page(signals: PageSignals) -> PriorityResult:
    impression_volume = _volume(signals.impressions, 50_000)
    session_volume = _volume(signals.sessions, 10_000)
    ctr_gap = max(0, min(1, (0.05 - signals.ctr) / 0.05))
    conversion_rate = (
        signals.conversions / signals.sessions if signals.sessions else 0
    )
    conversion_gap = max(0, min(1, (0.03 - conversion_rate) / 0.03))
    ranking_window = (
        max(0, 1 - abs(signals.average_position - 8) / 8)
        if signals.average_position
        else 0
    )
    data_points = sum(
        (
            signals.seo_score < 100,
            signals.impressions > 0,
            signals.sessions > 0,
            signals.average_position > 0,
        )
    )
    confidence = round(0.35 + (data_points / 4) * 0.65, 2)
    components = {
        "audit": round(
            min(25, (100 - max(0, min(100, signals.seo_score))) * 0.2
                + signals.issue_severity * 5),
            2,
        ),
        "gsc_ctr": round(20 * impression_volume * ctr_gap, 2),
        "ranking": round(15 * impression_volume * ranking_window, 2),
        "conversion": round(20 * session_volume * conversion_gap, 2),
        "trend": round(10 * max(0, min(1, -signals.trend / 0.4)), 2),
        "importance": round(5 * max(0, min(1, signals.importance)), 2),
        "confidence": round(5 * confidence, 2),
    }
    total = max(0, min(100, round(sum(components.values()))))
    return PriorityResult(
        url=signals.url,
        priority_score=total,
        confidence=confidence,
        action=_action(components),
        components=components,
        signals=signals,
    )


def score_pages(pages: list[PageSignals]) -> list[PriorityResult]:
    return sorted(
        (score_page(page) for page in pages),
        key=lambda result: result.priority_score,
        reverse=True,
    )
