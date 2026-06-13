from typing import Protocol

from app.domains.recommendations.schemas import PageFacts, RecommendationResult


class RecommendationGenerator(Protocol):
    def generate(self, facts: PageFacts) -> RecommendationResult: ...
