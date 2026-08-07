import hashlib
import html
import json
import re
from html.parser import HTMLParser

from sqlalchemy.orm import Session

from app.domains.page_blueprints.schemas import SnapshotTextField
from app.domains.page_packages.models import PagePackageProposal
from app.domains.page_packages.schemas import (
    GeneratedBlueprintPackage,
    GeneratedPagePackage,
    GeneratedSnapshotTextPackage,
    PagePackageContext,
    PagePackageGenerationResult,
    PageProposalRegenerationRequest,
    SnapshotTextValidation,
    SnapshotTextValue,
    plain_text,
    safe_html,
)
from app.domains.recommendations.provider import ProviderGenerationError


def build_context(
    session: Session,
    proposal: PagePackageProposal,
) -> PagePackageContext:
    stored = session.get(PagePackageProposal, proposal.id)
    if stored is None or stored.source_wordpress_page_id is None:
        raise ValueError("existing-page proposal context is unavailable")
    raw_context = stored.config_snapshot.get("generation_context")
    if not isinstance(raw_context, dict):
        raise ValueError("existing-page proposal context is unavailable")
    context = PagePackageContext.model_validate(raw_context)
    schema = (
        context.blueprint_schema.model_dump(mode="python")
        if context.blueprint_schema is not None
        else None
    )
    if schema != stored.config_snapshot.get("content_schema"):
        raise ValueError("existing-page proposal context is invalid")
    return context


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


class _RichTextUrlCollector(HTMLParser):
    URL_ATTRIBUTES = {"action", "formaction", "href", "poster", "src"}

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        for name, value in attrs:
            if name.lower() in self.URL_ATTRIBUTES and value:
                self.urls.append(value.strip())


def _rich_text_urls(value: str) -> list[str]:
    parser = _RichTextUrlCollector()
    parser.feed(value)
    return parser.urls


_SNAPSHOT_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_IGNORED_FIELD_IDS = 100
_MAX_ENTITY_DECODE_PASSES = 8
_RICH_TEXT_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "u",
    "ul",
}


def _decode_html_entities(value: str) -> str:
    for _ in range(_MAX_ENTITY_DECODE_PASSES):
        decoded = html.unescape(value)
        if decoded == value:
            return value
        value = decoded
    if html.unescape(value) != value:
        raise ValueError("nested HTML entities exceed the normalization limit")
    return value


class _RichTextSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag not in _RICH_TEXT_TAGS:
            return
        rendered_attrs = ""
        if tag == "a":
            href = next(
                (
                    value.strip()
                    for name, value in attrs
                    if name.lower() == "href" and value
                ),
                None,
            )
            if href is not None:
                rendered_attrs = f' href="{html.escape(href, quote=True)}"'
        self.parts.append(f"<{tag}{rendered_attrs}>")

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() in _RICH_TEXT_TAGS and tag.lower() != "br":
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _RICH_TEXT_TAGS and tag != "br":
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(html.escape(data, quote=False))

    def sanitized(self) -> str:
        return "".join(self.parts).strip()


def _strip_markup(value: str) -> str:
    without_tags = re.sub(r"<[^>]*>", " ", value)
    return " ".join(without_tags.split())


def _sanitize_rich_text(value: str) -> str:
    sanitizer = _RichTextSanitizer()
    sanitizer.feed(value)
    sanitizer.close()
    return sanitizer.sanitized()


def _snapshot_field_value(
    field: SnapshotTextField,
    value: str,
    approved_urls: set[str],
) -> tuple[str | None, str | None]:
    try:
        decoded = _decode_html_entities(value)
        safe_html(decoded)
    except ValueError:
        return None, "unsafe_html"

    if field.value_type == "rich_text":
        if any(url not in approved_urls for url in _rich_text_urls(decoded)):
            return None, "unapproved_url"
        normalized = _sanitize_rich_text(decoded)
        empty_value = not _strip_markup(normalized)
    else:
        normalized = _strip_markup(decoded)
        try:
            plain_text(normalized)
        except ValueError:
            return None, "unsafe_html"
        empty_value = not normalized

    if field.id == "document:slug" and normalized:
        if _SNAPSHOT_SLUG.fullmatch(normalized) is None:
            return None, "invalid_slug"
    if field.value_type == "url" and normalized not in approved_urls:
        return None, "unapproved_url"
    if len(normalized) > field.max_length:
        return None, "max_length"
    if field.required and empty_value:
        return None, "required"
    return normalized, None


def normalize_snapshot_text_package(
    raw: object,
    context: PagePackageContext,
) -> SnapshotTextValidation:
    schema = context.blueprint_schema
    if schema is None or schema.schema_version != "snapshot-text-v1":
        raise ValueError("snapshot-text-v1 schema is required")
    if isinstance(raw, GeneratedSnapshotTextPackage):
        payload = raw.model_dump(mode="python")
    elif isinstance(raw, dict):
        payload = raw
    else:
        raise ValueError("invalid snapshot text package")
    if set(payload) != {"text_replacements"} or not isinstance(
        payload["text_replacements"], dict
    ):
        raise ValueError("invalid snapshot text package")

    fields = schema.fields_by_id()
    candidates = payload["text_replacements"]
    approved_urls = {
        link.url for link in context.internal_link_candidates
    } | set(context.approved_cta_urls)
    replacements: dict[str, str] = {}
    field_errors: dict[str, str] = {}
    provided_field_ids: set[str] = set()
    ignored_field_ids: list[str] = []

    for field_id, candidate in candidates.items():
        if field_id not in fields:
            if (
                isinstance(field_id, str)
                and len(ignored_field_ids) < _MAX_IGNORED_FIELD_IDS
            ):
                ignored_field_ids.append(field_id)
            continue
        provided_field_ids.add(field_id)
        if isinstance(candidate, SnapshotTextValue):
            value = candidate.value
        elif (
            isinstance(candidate, dict)
            and set(candidate) == {"value"}
            and isinstance(candidate["value"], str)
        ):
            value = candidate["value"]
        else:
            field_errors[field_id] = "invalid_value"
            continue
        normalized, error = _snapshot_field_value(
            fields[field_id],
            value,
            approved_urls,
        )
        if (
            error is None
            and normalized is not None
            and not _strip_markup(normalized)
            and fields[field_id].current_value
        ):
            normalized, error = _snapshot_field_value(
                fields[field_id],
                fields[field_id].current_value,
                approved_urls,
            )
        if error is not None:
            field_errors[field_id] = error
        else:
            assert normalized is not None
            replacements[field_id] = normalized

    focus_field = fields.get("seo:focus_keyword")
    if focus_field is not None:
        provided_field_ids.add(focus_field.id)
        normalized, error = _snapshot_field_value(
            focus_field,
            context.keyword,
            approved_urls,
        )
        if error is not None:
            field_errors[focus_field.id] = error
            replacements.pop(focus_field.id, None)
        else:
            assert normalized is not None
            replacements[focus_field.id] = normalized
            field_errors.pop(focus_field.id, None)

    for field in fields.values():
        if not field.required or field.id in provided_field_ids:
            continue
        normalized, error = _snapshot_field_value(
            field,
            field.current_value,
            approved_urls,
        )
        if error is not None:
            field_errors[field.id] = error
            continue
        assert normalized is not None
        provided_field_ids.add(field.id)
        replacements[field.id] = normalized

    missing_required = sorted(
        field.id
        for field in fields.values()
        if field.required and field.id not in provided_field_ids
    )
    blocking = sorted(
        field_id
        for field_id in field_errors
        if fields[field_id].required
    )
    return SnapshotTextValidation(
        replacements=replacements,
        field_errors=dict(sorted(field_errors.items())),
        blocking_field_ids=blocking,
        ignored_field_ids=sorted(ignored_field_ids),
        missing_required_field_ids=missing_required,
    )


def page_package_contract(context: PagePackageContext):
    if (
        context.blueprint_schema is not None
        and context.blueprint_schema.schema_version == "snapshot-text-v1"
    ):
        return GeneratedSnapshotTextPackage
    if context.blueprint_schema is not None:
        return GeneratedBlueprintPackage
    return GeneratedPagePackage


def page_package_system_prompt(context: PagePackageContext) -> str:
    if (
        context.blueprint_schema is not None
        and context.blueprint_schema.schema_version == "snapshot-text-v1"
    ):
        schema_prompt = json.dumps(
            page_package_contract(context).model_json_schema(),
            ensure_ascii=False,
            sort_keys=True,
        )
        return (
            "Genereer uitsluitend Nederlandse kandidaatwaarden voor bekende "
            "field-ID's. Antwoord exact als een JSON-object met deze vorm: "
            '{"text_replacements":{"known-field-id":{"value":"candidate text"}}}. '
            "De enige top-level key is text_replacements. Gebruik uitsluitend "
            "field-ID's uit de invoer en geef per ID exact een value-string. Laat "
            "onbekende field-ID's weg. Gebruik voor URL-waarden uitsluitend de "
            "aangeleverde goedgekeurde URL's. Verzin geen garanties, prijzen, "
            "locaties of certificeringen. Geef geen toelichting buiten het "
            "JSON-object. HTML mag geen scripts, formulieren, inline event handlers "
            "of javascript-URL's bevatten. Het resultaat is een concept voor "
            "menselijke beoordeling en mag nooit automatisch worden gepubliceerd."
            f"\n\nContractschema:\n{schema_prompt}\n\n"
            f"Projectcontext:\n"
            f"{context.company_context[:10_000] or 'Niet ingesteld.'}"
        )
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


def page_package_user_prompt(context: PagePackageContext) -> str:
    schema = context.blueprint_schema
    if schema is None or schema.schema_version != "snapshot-text-v1":
        return json.dumps(context.model_dump(), ensure_ascii=False)
    approved_urls = sorted(
        {link.url for link in context.internal_link_candidates}
        | set(context.approved_cta_urls)
    )
    return json.dumps(
        {
            "keyword": context.keyword,
            "search_volume": context.search_volume,
            "intent": context.intent,
            "project_domain": context.project_domain,
            "approved_urls": approved_urls,
            "field_definitions": [
                {
                    "id": field.id,
                    "label": field.label,
                    "value_type": field.value_type,
                    "current_value": field.current_value,
                    "required": field.required,
                    "max_length": field.max_length,
                }
                for field in schema.fields_by_id().values()
            ],
        },
        ensure_ascii=False,
    )


def generation_result(
    package: (
        GeneratedPagePackage
        | GeneratedBlueprintPackage
        | GeneratedSnapshotTextPackage
    ),
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
    contract = (
        context.blueprint_schema.schema_version
        if context.blueprint_schema is not None
        else "page-package-v1"
    )
    if contract == "blueprint-v1":
        contract = "blueprint-replacements-v1"
    return hashlib.sha256(
        json.dumps(
            {
                "contract": contract,
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
