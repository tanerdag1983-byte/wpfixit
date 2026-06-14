from app.domains.recommendations.provider import ProviderGenerationError
from app.domains.recommendations.schemas import PageFacts, RecommendationResult


class PolicyRecommendationGenerator:
    def __init__(self, primary, fallback=None) -> None:
        self.primary = primary
        self.fallback = fallback

    def generate(self, facts: PageFacts) -> RecommendationResult:
        try:
            return self.primary.generate(facts)
        except ProviderGenerationError:
            if self.fallback is None:
                raise
            return self.fallback.generate(facts)
