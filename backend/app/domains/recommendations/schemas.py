from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    excerpt: str

    @field_validator("excerpt")
    @classmethod
    def bound_excerpt(cls, value: str) -> str:
        return value[:500]


class PageFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str
    priority_score: int = Field(ge=0, le=100)
    components: dict[str, float]
    evidence: list[EvidenceItem] = Field(min_length=1)


class GeneratedRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: str
    priority: str
    recommendation: str
    rationale: str
    evidence: list[str] = Field(min_length=1)


class RecommendationResult(GeneratedRecommendation):
    approval_state: str = "proposed"
    provider: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
