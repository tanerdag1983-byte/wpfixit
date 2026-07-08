import hashlib
import html
import json
from html.parser import HTMLParser

from app.domains.page_packages.schemas import (
    GeneratedBlueprintPackage,
    GeneratedPagePackage,
    PagePackageContext,
    PagePackageGenerationResult,
    PageProposalRegenerationRequest,
    plain_text,
    safe_html,
)
from app.domains.recommendations.provider import ProviderGenerationError


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.urls.append(value.strip())


def _html_urls(value: str) -> list[str]:
    parser = _LinkCollector()
    parser.feed(value)
    return parser.urls


def page_package_contract(context: PagePackageContext):
    if context.blueprint_schema is not None:
        return GeneratedBlueprintPackage
    return GeneratedPagePackage


def page_package_system_prompt(context: PagePackageContext) -> str:
    blueprint_rules = ""
    if context.blueprint_schema is not None:
        blueprint_rules = (
            " Bewaar iedere block- en field-ID uit het blueprint-schema. Geef exact "
            "een replacement voor ieder verplicht tekst- of URL-veld en respecteer "
            "value_type en max_length. Geef nooit media-, layout-, stijl- of "
            "builderdata terug. Gebruik voor URL-velden en interne links uitsluitend "
            "de aangeleverde goedgekeurde URL's."
        )
    schema_prompt = json.dumps(
        page_package_contract(context).model_json_schema(),
        ensure_ascii=False,
        sort_keys=True,
    )
    return (
        "Maak een complete Nederlandse SEO-landingspagina als strikt JSON volgens "
        "het opgegeven schema. Gebruik het focuszoekwoord natuurlijk, houd merk- en "
        "voertuigentiteiten exact gescheiden en verzin geen garanties, prijzen, "
        "locaties of certificeringen. Gebruik alleen de aangeleverde interne links. "
        "Herhaal nooit de inputcontext en geef geen toelichting buiten het JSON-"
        "object. Laat onbekende velden volledig weg en geef uitsluitend velden terug "
        "die in het contractschema staan. "
        "Alle HTML moet "
        "semantisch zijn en mag geen scripts, formulieren, inline event handlers of "
        "javascript-URL's bevatten. Het resultaat is een concept voor menselijke "
        "beoordeling en mag nooit automatisch worden gepubliceerd."
        f"{blueprint_rules}\n\n"
        f"Contractschema:\n{schema_prompt}\n\n"
        f"Projectcontext:\n{context.company_context[:10_000] or 'Niet ingesteld.'}"
    )


def generation_result(
    package: GeneratedPagePackage | GeneratedBlueprintPackage,
    *,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    context: PagePackageContext | None = None,
) -> PagePackageGenerationResult:
    if isinstance(package, GeneratedBlueprintPackage):
        if context is None:
            raise ValueError("blueprint context is required")
        package = validate_blueprint_replacements(package, context)
    return PagePackageGenerationResult(
        package=package,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def validate_blueprint_replacements(
    package: GeneratedBlueprintPackage,
    context: PagePackageContext,
) -> GeneratedBlueprintPackage:
    schema = context.blueprint_schema
    if schema is None:
        raise ValueError("blueprint schema is required")

    schema_fields = [field for block in schema.blocks for field in block.fields]
    fields = {field.id: field for field in schema_fields}
    if len(fields) != len(schema_fields):
        raise ValueError("duplicate blueprint field ID")
    replacement_ids = [replacement.field_id for replacement in package.replacements]
    if len(replacement_ids) != len(set(replacement_ids)):
        raise ValueError("duplicate blueprint field replacement")

    unknown = set(replacement_ids) - set(fields)
    if unknown:
        raise ValueError(f"unknown blueprint field: {sorted(unknown)[0]}")

    required = {field.id for field in fields.values() if field.required}
    missing = required - set(replacement_ids)
    if missing:
        raise ValueError(f"required blueprint field is missing: {sorted(missing)[0]}")

    approved_urls = {
        link.url for link in context.internal_link_candidates
    } | set(context.approved_cta_urls)
    approved_links = {
        (link.anchor, link.url) for link in context.internal_link_candidates
    }

    for replacement in package.replacements:
        field = fields[replacement.field_id]
        if field.required and not replacement.value:
            raise ValueError(f"required blueprint field is empty: {field.id}")
        if len(replacement.value) > field.max_length:
            raise ValueError(f"blueprint field exceeds max length: {field.id}")
        if field.value_type in {"plain_text", "heading", "button_text"}:
            plain_text(replacement.value)
        elif field.value_type == "rich_text":
            safe_html(replacement.value)
            if any(url not in approved_urls for url in _html_urls(replacement.value)):
                raise ValueError(f"URL is not approved for blueprint field: {field.id}")
        elif replacement.value not in approved_urls:
            raise ValueError(f"URL is not approved for blueprint field: {field.id}")

    has_unapproved_link = any(
        (link.anchor, link.url) not in approved_links
        for link in package.internal_links
    )
    if has_unapproved_link:
        raise ValueError("internal link is not approved")

    return package


def render_page_package(package: GeneratedPagePackage) -> str:
    sections = "".join(
        f"<section><h2>{html.escape(item.heading)}</h2>{item.body_html}</section>"
        for item in package.sections
    )
    faq = "".join(
        f"<details><summary>{html.escape(item.question)}</summary>"
        f"{item.answer_html}</details>"
        for item in package.faq
    )
    return (
        f"<h1>{html.escape(package.hero_title)}</h1>"
        f"{package.introduction_html}{sections}"
        f"<section><h2>Veelgestelde vragen</h2>{faq}</section>"
        f"<section><h2>{html.escape(package.cta.title)}</h2>"
        f'{package.cta.body_html}<p><a href="{html.escape(package.cta.button_url)}">'
        f"{html.escape(package.cta.button_label)}</a></p></section>"
    )


def prompt_version(context: PagePackageContext, model: str) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "contract": (
                    "blueprint-replacements-v1"
                    if context.blueprint_schema is not None
                    else "page-package-v1"
                ),
                "context": context.model_dump(),
                "model": model,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()


def regeneration_candidate_payload(
    proposal_package: dict,
    payload: PageProposalRegenerationRequest,
) -> dict:
    candidate = json.loads(
        json.dumps(proposal_package, ensure_ascii=False, sort_keys=True)
    )
    candidate["_regeneration"] = {
        "mode": payload.mode,
        "target_block_id": payload.target_block_id,
        "instruction": payload.instruction,
    }
    return candidate


class PolicyPagePackageGenerator:
    def __init__(self, primary, fallback=None) -> None:
        self.primary = primary
        self.fallback = fallback

    @property
    def provider(self) -> str:
        return getattr(self.primary, "provider", self.primary.__class__.__name__)

    @property
    def model(self) -> str:
        return self.primary.model

    def generate_page_package(self, context: PagePackageContext):
        try:
            return self.primary.generate_page_package(context)
        except ProviderGenerationError:
            if self.fallback is None:
                raise
            return self.fallback.generate_page_package(context)
