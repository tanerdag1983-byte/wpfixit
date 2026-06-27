import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BuilderType = Literal["gutenberg", "elementor", "bricks", "wpbakery", "acf"]
SeoPluginType = Literal["yoast", "rank_math", "aioseo"]


class PagePackageSettingsWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    builder: BuilderType
    template_wordpress_page_id: str = Field(min_length=1, max_length=64)
    seo_plugin: SeoPluginType
    slot_mapping: dict[str, str] = Field(default_factory=dict)


UNSAFE_HTML = re.compile(
    r"<(?:script|iframe|object|embed|form)\b|\son\w+\s*=|javascript\s*:|data\s*:\s*text/html",
    re.IGNORECASE,
)


def safe_html(value: str) -> str:
    value = value.strip()
    if UNSAFE_HTML.search(value):
        raise ValueError("Unsafe HTML is not allowed")
    return value


class InternalLink(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    anchor: str = Field(min_length=2, max_length=160)
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if UNSAFE_HTML.search(value) or not (
            value.startswith("/") or value.startswith("https://")
        ):
            raise ValueError("Internal link must be relative or HTTPS")
        return value


class PageSection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    heading: str = Field(min_length=3, max_length=180)
    body_html: str = Field(min_length=10, max_length=12_000)

    _safe_body = field_validator("body_html")(safe_html)


class FaqItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=5, max_length=240)
    answer_html: str = Field(min_length=10, max_length=4_000)

    _safe_answer = field_validator("answer_html")(safe_html)


class PageCta(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=180)
    body_html: str = Field(min_length=10, max_length=4_000)
    button_label: str = Field(min_length=2, max_length=80)
    button_url: str = Field(min_length=1, max_length=2048)

    _safe_body = field_validator("body_html")(safe_html)

    @field_validator("button_url")
    @classmethod
    def validate_button_url(cls, value: str) -> str:
        if UNSAFE_HTML.search(value) or not (
            value.startswith("/") or value.startswith("https://")
        ):
            raise ValueError("CTA URL must be relative or HTTPS")
        return value


class GeneratedPagePackage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=10, max_length=180)
    slug: str = Field(
        min_length=3, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    seo_title: str = Field(min_length=20, max_length=70)
    meta_description: str = Field(min_length=70, max_length=170)
    focus_keyword: str = Field(min_length=3, max_length=160)
    hero_title: str = Field(min_length=5, max_length=180)
    introduction_html: str = Field(min_length=10, max_length=6_000)
    sections: list[PageSection] = Field(min_length=2, max_length=12)
    faq: list[FaqItem] = Field(min_length=2, max_length=12)
    cta: PageCta
    internal_links: list[InternalLink] = Field(min_length=1, max_length=12)

    _safe_introduction = field_validator("introduction_html")(safe_html)


class PagePackageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str
    search_volume: int | None = None
    intent: str | None = None
    company_context: str
    project_domain: str
    internal_link_candidates: list[InternalLink]
    template_slots: dict[str, str]


class PagePackageGenerationResult(BaseModel):
    package: GeneratedPagePackage
    provider: str = ""
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class PagePackageProposalWrite(BaseModel):
    package: GeneratedPagePackage
