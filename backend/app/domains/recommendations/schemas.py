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
    wordpress_object_id: int | None = None
    post_type: str | None = None
    status: str | None = None
    seo_plugin: str | None = None
    current_values: dict[str, object] = Field(default_factory=dict)
    priority_score: int = Field(ge=0, le=100)
    components: dict[str, float]
    evidence: list[EvidenceItem] = Field(min_length=1)

    @field_validator("current_values")
    @classmethod
    def bound_current_values(cls, values: dict[str, object]) -> dict[str, object]:
        bounded: dict[str, object] = {}
        for key, value in values.items():
            bounded[key] = value[:4_000] if isinstance(value, str) else value
        return bounded


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
