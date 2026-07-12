import html
import json
import re
from copy import deepcopy

import requests
from pydantic import ValidationError

from app.domains.page_packages.generation import (
    generation_result,
    page_package_contract,
    page_package_system_prompt,
)
from app.domains.page_packages.schemas import (
    GeneratedBlueprintPackage,
    PagePackageContext,
)
from app.domains.recommendations.provider import (
    ProviderGenerationError,
    provider_error_message,
    system_prompt,
    validated_result,
)
from app.domains.recommendations.schemas import (
    GeneratedRecommendation,
    PageFacts,
    RecommendationResult,
)


def _extract_page_package_payload(payload, contract):
    if not isinstance(payload, dict):
        return payload

    contract_keys = set(contract.model_fields)
    required_keys = {
        name for name, field in contract.model_fields.items() if field.is_required()
    }

    direct_subset = {
        key: value for key, value in payload.items() if key in contract_keys
    }
    if required_keys.issubset(direct_subset):
        return direct_subset

    preferred_wrappers = (
        "landing_page",
        "page_package",
        "blueprint_package",
        "generated_package",
        "generated_page_package",
        "generated_blueprint_package",
        "package",
        "blueprint",
        "result",
        "output",
    )
    for key in preferred_wrappers:
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested_subset = _extract_page_package_payload(nested, contract)
            if isinstance(nested_subset, dict):
                nested_keys = set(nested_subset)
                if required_keys.issubset(nested_keys):
                    return nested_subset

    for value in payload.values():
        if isinstance(value, dict):
            nested_subset = _extract_page_package_payload(value, contract)
            if isinstance(nested_subset, dict):
                nested_keys = set(nested_subset)
                if required_keys.issubset(nested_keys):
                    return nested_subset

    return payload


def _parse_page_package_content(content: str, context: PagePackageContext):
    contract = page_package_contract(context)
    if context.blueprint_schema is not None:
        return normalize_blueprint_package(json.loads(content), context)
    try:
        return contract.model_validate_json(content)
    except ValidationError:
        payload = json.loads(content)
        normalized = _extract_page_package_payload(payload, contract)
        return contract.model_validate(normalized)


def _legacy_blueprint_payload(payload: dict, context: PagePackageContext) -> dict:
    """Convert older landing-page JSON into the current replacement contract."""
    landing = payload.get("landing_page")
    if not isinstance(landing, dict):
        legacy_keys = ("hero_title", "introduction_html", "sections", "faq", "cta")
        if any(key in payload for key in legacy_keys):
            landing = payload
        else:
            normalized = _extract_page_package_payload(
                payload,
                GeneratedBlueprintPackage,
            )
            return _repair_blueprint_replacement_ids(normalized, context)
    if isinstance(landing.get("replacements"), list):
        return _repair_blueprint_replacement_ids(landing, context)

    schema = context.blueprint_schema
    assert schema is not None
    sections = landing.get("sections")
    sections = sections if isinstance(sections, list) else []
    faq_items = landing.get("faq")
    faq_items = faq_items if isinstance(faq_items, list) else []
    cta = landing.get("cta") if isinstance(landing.get("cta"), dict) else {}
    section_cursor = 0
    replacements: list[dict[str, str]] = []

    for block in schema.blocks:
        role = block.semantic_role
        block_values: list[str] = []
        if role == "hero":
            block_values = [
                str(landing.get("hero_title") or landing.get("title") or "")
            ]
        elif role == "introduction":
            block_values = [str(landing.get("introduction_html") or "")]
        elif role == "faq":
            block_values = [
                "".join(
                    f"<details><summary>{item.get('question', '')}</summary>"
                    f"{item.get('answer_html', '')}</details>"
                    for item in faq_items
                    if isinstance(item, dict)
                )
            ]
        elif role == "cta":
            block_values = [
                str(cta.get("title") or landing.get("title") or ""),
                str(cta.get("body_html") or ""),
                str(cta.get("button_label") or "Meer informatie"),
                str(cta.get("button_url") or ""),
            ]
        else:
            while section_cursor < len(sections):
                item = sections[section_cursor]
                section_cursor += 1
                if isinstance(item, dict):
                    block_values.extend(
                        [
                            str(item.get("heading") or ""),
                            str(item.get("body_html") or ""),
                        ]
                    )
                    break

        value_cursor = 0
        for field in block.fields:
            value = ""
            label = field.label.casefold()
            if field.value_type == "url":
                value = str(cta.get("button_url") or "")
            elif (
                "titel" in label
                or "title" in label
                or field.value_type
                in {
                    "heading",
                    "button_text",
                }
            ):
                value = str(landing.get("hero_title") or landing.get("title") or "")
            elif value_cursor < len(block_values):
                value = block_values[value_cursor]
                value_cursor += 1
            if not value:
                value = field.current_value
            if field.required and not value:
                value = (
                    "Meer informatie"
                    if field.value_type != "rich_text"
                    else "<p>Meer informatie.</p>"
                )
            replacements.append({"field_id": field.id, "value": value})

    return {
        "title": str(
            landing.get("title") or landing.get("hero_title") or context.keyword
        ),
        "slug": _slugify(str(landing.get("slug") or context.keyword)),
        "seo_title": str(
            landing.get("seo_title") or landing.get("title") or context.keyword
        ),
        "meta_description": str(
            landing.get("meta_description")
            or landing.get("introduction_html")
            or context.keyword
        )
        .replace("<p>", "")
        .replace("</p>", "")[:170],
        "focus_keyword": str(landing.get("focus_keyword") or context.keyword),
        "replacements": replacements,
        "internal_links": landing.get("internal_links") or [],
    }


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return value or "nieuwe-pagina"


def _repair_blueprint_replacement_ids(
    payload: dict, context: PagePackageContext
) -> dict:
    if not isinstance(payload, dict) or not isinstance(
        payload.get("replacements"), list
    ):
        return payload
    schema = context.blueprint_schema
    assert schema is not None
    known = {field.id for block in schema.blocks for field in block.fields}
    available = [field.id for block in schema.blocks for field in block.fields]
    repaired = deepcopy(payload)
    used = {
        item.get("field_id")
        for item in repaired["replacements"]
        if isinstance(item, dict) and item.get("field_id") in known
    }
    next_ids = [field_id for field_id in available if field_id not in used]
    for item in repaired["replacements"]:
        if not isinstance(item, dict) or item.get("field_id") in known:
            continue
        if next_ids:
            item["field_id"] = next_ids.pop(0)
    present = {
        item.get("field_id")
        for item in repaired["replacements"]
        if isinstance(item, dict)
    }
    for block in schema.blocks:
        for field in block.fields:
            if field.required and field.id not in present:
                repaired["replacements"].append(
                    {"field_id": field.id, "value": field.current_value}
                )
    return repaired


def _strip_html_to_plain_text(value: str) -> str:
    stripped = re.sub(r"<[^>]*>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(stripped)).strip()


def _normalize_blueprint_plain_text_values(
    payload: dict,
    context: PagePackageContext,
) -> dict:
    if not isinstance(payload, dict):
        return payload

    normalized = deepcopy(payload)
    for key in ("title", "seo_title", "meta_description", "focus_keyword"):
        value = normalized.get(key)
        if isinstance(value, str):
            normalized[key] = _strip_html_to_plain_text(value)

    schema = context.blueprint_schema
    assert schema is not None
    value_types = {
        field.id: field.value_type for block in schema.blocks for field in block.fields
    }
    for replacement in normalized.get("replacements", []):
        if not isinstance(replacement, dict):
            continue
        if value_types.get(replacement.get("field_id")) not in {
            "plain_text",
            "heading",
            "button_text",
        }:
            continue
        value = replacement.get("value")
        if isinstance(value, str):
            replacement["value"] = _strip_html_to_plain_text(value)

    for link in normalized.get("internal_links", []):
        if not isinstance(link, dict):
            continue
        anchor = link.get("anchor")
        if isinstance(anchor, str):
            link["anchor"] = _strip_html_to_plain_text(anchor)

    return normalized


def normalize_blueprint_package(
    payload: dict,
    context: PagePackageContext,
) -> GeneratedBlueprintPackage:
    """Normalize stored legacy output before it is sent to the WordPress bridge."""
    normalized = _legacy_blueprint_payload(payload, context)
    normalized = _normalize_blueprint_plain_text_values(normalized, context)
    return GeneratedBlueprintPackage.model_validate(normalized)


class OpenAICompatibleRecommendationGenerator:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        company_context: str = "",
        provider: str = "openai_compatible",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.company_context = company_context
        self.provider = provider

    def generate_page_package(self, context: PagePackageContext):
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": page_package_system_prompt(context),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                context.model_dump(), ensure_ascii=False
                            ),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=120,
                allow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            package = _parse_page_package_content(
                payload["choices"][0]["message"]["content"],
                context,
            )
            usage = payload.get("usage", {})
            return generation_result(
                package,
                provider=self.provider,
                model=self.model,
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                context=context,
            )
        except ProviderGenerationError:
            raise
        except Exception as error:
            raise ProviderGenerationError(
                provider_error_message(
                    "OpenAI-compatible page generation failed",
                    error,
                )
            ) from error

    def generate(self, facts: PageFacts) -> RecommendationResult:
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt(self.company_context),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                facts.model_dump(), ensure_ascii=False
                            ),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=60,
                allow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            generated = GeneratedRecommendation.model_validate_json(
                payload["choices"][0]["message"]["content"]
            )
            usage = payload.get("usage", {})
            return validated_result(
                generated,
                facts,
                provider=self.provider,
                model=self.model,
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
            )
        except ProviderGenerationError:
            raise
        except Exception as error:
            raise ProviderGenerationError(
                provider_error_message(
                    "OpenAI-compatible generation failed",
                    error,
                )
            ) from error
