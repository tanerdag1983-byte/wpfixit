import html

import pytest
from pydantic import ValidationError

from app.domains.page_blueprints.schemas import BlueprintSchema, SnapshotTextSchema
from app.domains.page_packages.generation import (
    normalize_snapshot_text_package,
    page_package_contract,
    validate_blueprint_replacements,
)
from app.domains.page_packages.schemas import (
    FieldReplacement,
    GeneratedBlueprintPackage,
    GeneratedPagePackage,
    GeneratedSnapshotTextPackage,
    InternalLink,
    PagePackageContext,
)


def valid_package() -> dict:
    return {
        "title": "DSG versnellingsbak reviseren",
        "slug": "dsg-versnellingsbak-reviseren",
        "seo_title": "DSG versnellingsbak reviseren | Specialist",
        "meta_description": (
            "Laat uw DSG versnellingsbak deskundig onderzoeken en reviseren door "
            "een ervaren transmissiespecialist."
        ),
        "focus_keyword": "dsg versnellingsbak reviseren",
        "hero_title": "DSG versnellingsbak reviseren",
        "introduction_html": "<p>Heldere diagnose en vakkundige revisie.</p>",
        "sections": [
            {
                "heading": "Wanneer is revisie nodig?",
                "body_html": (
                    "<p>Veelvoorkomende klachten zijn schokken en slippen.</p>"
                ),
            },
            {
                "heading": "Onze werkwijze",
                "body_html": "<p>We starten met een gerichte diagnose.</p>",
            },
        ],
        "faq": [
            {
                "question": "Hoe lang duurt een DSG revisie?",
                "answer_html": "<p>Dat hangt af van de diagnose en onderdelen.</p>",
            },
            {
                "question": "Krijg ik vooraf een prijsopgave?",
                "answer_html": "<p>Ja, na de diagnose bespreken we de opties.</p>",
            },
        ],
        "cta": {
            "title": "Laat uw DSG controleren",
            "body_html": "<p>Plan een diagnose bij onze specialist.</p>",
            "button_label": "Afspraak maken",
            "button_url": "/contact/",
        },
        "internal_links": [
            {
                "anchor": "automatische versnellingsbak",
                "url": "https://example.com/automatische-versnellingsbak/",
            }
        ],
    }


def valid_blueprint_schema() -> dict:
    return {
        "schema_version": "blueprint-v1",
        "blocks": [
            {
                "id": "hero",
                "layout": "hero_algemeen",
                "label": "Hero",
                "semantic_role": "hero",
                "fields": [
                    {
                        "id": "acf-title",
                        "path": "page_blocks/0/title",
                        "label": "Titel",
                        "value_type": "heading",
                        "current_value": "Transmissie revisie",
                        "required": True,
                        "max_length": 180,
                    },
                    {
                        "id": "acf-cta-url",
                        "path": "page_blocks/0/button_url",
                        "label": "CTA URL",
                        "value_type": "url",
                        "current_value": "/contact/",
                        "required": True,
                        "max_length": 2048,
                    },
                    {
                        "id": "acf-copy",
                        "path": "page_blocks/0/copy",
                        "label": "Tekst",
                        "value_type": "rich_text",
                        "current_value": "<p>Diagnose</p>",
                        "required": False,
                        "max_length": 5000,
                    },
                ],
            }
        ],
    }


def blueprint_context() -> PagePackageContext:
    return PagePackageContext(
        keyword="dsg revisie schiedam",
        search_volume=320,
        intent="commercial",
        company_context="SHM Transmissie in Schiedam",
        project_domain="https://member.example",
        internal_link_candidates=[
            InternalLink(anchor="Transmissie diagnose", url="/transmissie-diagnose/")
        ],
        approved_cta_urls=["/offerte-aanvragen/"],
        blueprint_schema=BlueprintSchema.model_validate(valid_blueprint_schema()),
        template_slots={},
    )


def valid_snapshot_schema() -> dict:
    def field(
        field_id: str,
        value_type: str,
        *,
        current_value: str,
        required: bool = True,
        max_length: int = 200,
    ) -> dict:
        return {
            "id": field_id,
            "path": field_id,
            "label": field_id,
            "value_type": value_type,
            "current_value": current_value,
            "required": required,
            "max_length": max_length,
        }

    return {
        "schema_version": "snapshot-text-v1",
        "document_fields": [
            field(
                "document:title",
                "heading",
                current_value="Bestaande titel",
                max_length=180,
            ),
            field(
                "document:slug",
                "plain_text",
                current_value="bestaande-titel",
                max_length=160,
            ),
            field(
                "seo:title",
                "seo_title",
                current_value="Bestaande SEO-titel",
                max_length=70,
            ),
            field(
                "seo:meta_description",
                "meta_description",
                current_value="Bestaande metabeschrijving",
                max_length=170,
            ),
            field(
                "seo:focus_keyword",
                "focus_keyword",
                current_value="",
                max_length=160,
            ),
        ],
        "blocks": [
            {
                "id": "acf:hero",
                "layout": "hero",
                "label": "Hero",
                "semantic_role": "hero",
                "fields": [
                    field(
                        "acf:hero:title",
                        "heading",
                        current_value="Bestaande hero",
                        max_length=180,
                    ),
                    field(
                        "acf:hero:label",
                        "button_text",
                        current_value="Meer informatie",
                        required=False,
                        max_length=80,
                    ),
                    field(
                        "acf:hero:copy",
                        "rich_text",
                        current_value="<p>Bestaande tekst.</p>",
                        required=False,
                        max_length=5_000,
                    ),
                    field(
                        "acf:hero:url",
                        "url",
                        current_value="/contact/",
                        required=False,
                        max_length=2_048,
                    ),
                ],
            }
        ],
    }


def snapshot_context() -> PagePackageContext:
    return PagePackageContext(
        keyword="dsg revisie schiedam",
        search_volume=320,
        intent="commercial",
        company_context="SHM Transmissie in Schiedam",
        project_domain="https://member.example",
        internal_link_candidates=[
            InternalLink(anchor="Transmissie diagnose", url="/transmissie-diagnose/")
        ],
        approved_cta_urls=["/offerte-aanvragen/"],
        blueprint_schema=SnapshotTextSchema.model_validate(valid_snapshot_schema()),
        template_slots={},
    )


def valid_snapshot_text_package() -> dict:
    return {
        "text_replacements": {
            "document:title": {"value": "<strong>Nieuwe titel</strong>"},
            "document:slug": {"value": "<em>nieuwe-titel</em>"},
            "seo:title": {"value": "<b>Nieuwe SEO-titel</b>"},
            "seo:meta_description": {
                "value": "<p>Nieuwe metabeschrijving voor deze pagina.</p>"
            },
            "seo:focus_keyword": {"value": "ander zoekwoord"},
            "acf:hero:title": {"value": "<h1>Nieuwe hero</h1>"},
        }
    }


def blueprint_package(
    *, field_id: str = "acf-title", url: str = "/offerte-aanvragen/"
) -> GeneratedBlueprintPackage:
    return GeneratedBlueprintPackage(
        title="DSG revisie specialist Schiedam",
        slug="dsg-revisie-schiedam",
        seo_title="DSG revisie Schiedam door een specialist",
        meta_description=(
            "Laat uw DSG onderzoeken en gericht reviseren door SHM Transmissie "
            "in Schiedam."
        ),
        focus_keyword="dsg revisie schiedam",
        replacements=[
            FieldReplacement(field_id=field_id, value="DSG revisie Schiedam"),
            FieldReplacement(field_id="acf-cta-url", value=url),
        ],
        internal_links=[
            InternalLink(anchor="Transmissie diagnose", url="/transmissie-diagnose/")
        ],
    )


def test_complete_page_package_contract() -> None:
    package = GeneratedPagePackage.model_validate(valid_package())

    assert package.slug == "dsg-versnellingsbak-reviseren"
    assert len(package.sections) == 2
    assert len(package.faq) == 2


def test_snapshot_contract_contains_only_field_id_values() -> None:
    contract = page_package_contract(snapshot_context())

    assert contract is GeneratedSnapshotTextPackage
    assert set(contract.model_json_schema()["properties"]) == {"text_replacements"}

    with pytest.raises(ValidationError):
        contract.model_validate(
            {
                **valid_snapshot_text_package(),
                "title": "Legacy top-level title",
            }
        )


def test_invalid_optional_field_does_not_fail_valid_required_fields() -> None:
    payload = valid_snapshot_text_package()
    payload["text_replacements"].update(
        {
            "acf:hero:label": {"value": "<script>bad</script>"},
            "unknown:id": {"value": "ignore"},
        }
    )

    result = normalize_snapshot_text_package(payload, snapshot_context())

    assert result.replacements["document:title"] == "Nieuwe titel"
    assert result.replacements["document:slug"] == "nieuwe-titel"
    assert result.replacements["seo:focus_keyword"] == "dsg revisie schiedam"
    assert "acf:hero:label" not in result.replacements
    assert result.field_errors == {"acf:hero:label": "unsafe_html"}
    assert result.blocking_field_ids == []
    assert result.ignored_field_ids == ["unknown:id"]
    assert result.missing_required_field_ids == []
    assert result.ready is True


def test_required_missing_and_invalid_fields_block_only_validation() -> None:
    payload = valid_snapshot_text_package()
    del payload["text_replacements"]["document:title"]
    payload["text_replacements"]["document:slug"] = {
        "value": "<strong>Onveilige Slug</strong>"
    }

    result = normalize_snapshot_text_package(payload, snapshot_context())

    assert result.field_errors == {"document:slug": "invalid_slug"}
    assert result.blocking_field_ids == ["document:slug"]
    assert result.missing_required_field_ids == ["document:title"]
    assert result.replacements["seo:focus_keyword"] == "dsg revisie schiedam"
    assert result.ready is False


def test_snapshot_plain_text_decodes_entities_before_safety_and_markup_rules() -> None:
    payload = valid_snapshot_text_package()
    payload["text_replacements"].update(
        {
            "document:title": {
                "value": "&lt;strong&gt;Nieuwe titel&lt;/strong&gt;"
            },
            "acf:hero:label": {
                "value": "&lt;img src=x onerror&#61;alert(1)&gt;Meer"
            },
        }
    )

    result = normalize_snapshot_text_package(payload, snapshot_context())

    assert result.replacements["document:title"] == "Nieuwe titel"
    assert result.field_errors == {"acf:hero:label": "unsafe_html"}
    assert result.ready is True


def test_snapshot_plain_text_decodes_nested_entities_to_a_stable_value() -> None:
    payload = valid_snapshot_text_package()
    payload["text_replacements"].update(
        {
            "document:title": {
                "value": (
                    "&amp;amp;lt;strong&amp;amp;gt;Nieuwe titel"
                    "&amp;amp;lt;/strong&amp;amp;gt;"
                )
            },
            "acf:hero:label": {
                "value": (
                    "&amp;amp;lt;img src=x onerror&amp;amp;#61;alert(1)"
                    "&amp;amp;gt;Meer"
                )
            },
        }
    )

    result = normalize_snapshot_text_package(payload, snapshot_context())

    assert result.replacements["document:title"] == "Nieuwe titel"
    assert result.field_errors == {"acf:hero:label": "unsafe_html"}
    assert html.unescape(result.replacements["document:title"]) == "Nieuwe titel"
    assert result.ready is True


def test_snapshot_rich_text_is_sanitized_and_urls_must_be_approved() -> None:
    payload = valid_snapshot_text_package()
    payload["text_replacements"].update(
        {
            "acf:hero:copy": {
                "value": (
                    '<p class="lead">Lees <span>onze</span> '
                    '<a href="/transmissie-diagnose/" onclick="bad()">'
                    "diagnose</a>.</p>"
                )
            },
            "acf:hero:url": {"value": "<b>/offerte-aanvragen/</b>"},
        }
    )

    result = normalize_snapshot_text_package(payload, snapshot_context())

    assert result.field_errors == {"acf:hero:copy": "unsafe_html"}
    assert result.replacements["acf:hero:url"] == "/offerte-aanvragen/"

    payload["text_replacements"]["acf:hero:copy"] = {
        "value": (
            '<p class="lead">Lees <span>onze</span> '
            '<a href="/transmissie-diagnose/">diagnose</a>.</p>'
        )
    }
    payload["text_replacements"]["acf:hero:url"] = {
        "value": "https://outside.example/"
    }

    result = normalize_snapshot_text_package(payload, snapshot_context())

    assert result.replacements["acf:hero:copy"] == (
        '<p>Lees onze <a href="/transmissie-diagnose/">diagnose</a>.</p>'
    )
    assert result.field_errors == {"acf:hero:url": "unapproved_url"}


def test_snapshot_validates_urls_removed_by_rich_text_sanitization() -> None:
    payload = valid_snapshot_text_package()
    payload["text_replacements"]["acf:hero:copy"] = {
        "value": '<p>Tekst<img src="https://outside.example/image.jpg"></p>'
    }

    result = normalize_snapshot_text_package(payload, snapshot_context())

    assert result.field_errors == {"acf:hero:copy": "unapproved_url"}
    assert "acf:hero:copy" not in result.replacements
    assert result.ready is True


def test_snapshot_ignores_only_a_bounded_number_of_unknown_field_ids() -> None:
    payload = valid_snapshot_text_package()
    payload["text_replacements"].update(
        {f"unknown:{index:03d}": {"value": "ignore"} for index in range(150)}
    )

    result = normalize_snapshot_text_package(payload, snapshot_context())

    assert len(result.ignored_field_ids) == 100
    assert result.ignored_field_ids[0] == "unknown:000"
    assert result.ignored_field_ids[-1] == "unknown:099"
    assert result.ready is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("slug",), "DSG Revisie"),
        (("meta_description",), "te kort"),
        (("introduction_html",), '<script>alert("x")</script>'),
        (("sections", 0, "body_html"), '<p onclick="x()">Onveilig</p>'),
        (("cta", "button_url"), "javascript:alert(1)"),
    ],
)
def test_page_package_rejects_invalid_or_unsafe_values(path, value) -> None:
    payload = valid_package()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        GeneratedPagePackage.model_validate(payload)


def test_accepts_only_known_text_fields_and_approved_urls() -> None:
    validated = validate_blueprint_replacements(
        blueprint_package(), blueprint_context()
    )

    assert validated.replacements[0].field_id == "acf-title"


def test_rejects_unknown_blueprint_field() -> None:
    with pytest.raises(ValueError, match="unknown blueprint field"):
        validate_blueprint_replacements(
            blueprint_package(field_id="image-1"), blueprint_context()
        )


def test_rejects_unapproved_blueprint_url() -> None:
    with pytest.raises(ValueError, match="URL is not approved"):
        validate_blueprint_replacements(
            blueprint_package(url="https://outside.example"), blueprint_context()
        )


def test_rejects_unapproved_link_inside_rich_text() -> None:
    package = blueprint_package()
    package.replacements.append(
        FieldReplacement(
            field_id="acf-copy",
            value='<p>Lees <a href="https://outside.example">meer</a>.</p>',
        )
    )

    with pytest.raises(ValueError, match="URL is not approved"):
        validate_blueprint_replacements(package, blueprint_context())


def test_rejects_unsafe_approved_cta_url() -> None:
    payload = blueprint_context().model_dump()
    payload["approved_cta_urls"] = ["javascript:alert(1)"]

    with pytest.raises(ValidationError, match="Approved CTA URL"):
        PagePackageContext.model_validate(payload)


def test_rejects_duplicate_schema_field_ids() -> None:
    context = blueprint_context()
    context.blueprint_schema.blocks[0].fields.append(
        context.blueprint_schema.blocks[0].fields[0]
    )

    with pytest.raises(ValueError, match="duplicate blueprint field ID"):
        validate_blueprint_replacements(blueprint_package(), context)


def test_rejects_missing_required_replacement_and_html_in_heading() -> None:
    package = blueprint_package()
    package.replacements = [
        FieldReplacement(field_id="acf-title", value="<b>DSG revisie</b>"),
        FieldReplacement(field_id="acf-cta-url", value="/offerte-aanvragen/"),
    ]

    with pytest.raises(ValueError, match="HTML is not allowed"):
        validate_blueprint_replacements(package, blueprint_context())

    package.replacements = [
        FieldReplacement(field_id="acf-title", value="DSG revisie Schiedam")
    ]
    with pytest.raises(ValueError, match="required blueprint field"):
        validate_blueprint_replacements(package, blueprint_context())
