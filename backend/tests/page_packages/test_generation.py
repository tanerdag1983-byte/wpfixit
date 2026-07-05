import pytest
from pydantic import ValidationError

from app.domains.page_blueprints.schemas import BlueprintSchema
from app.domains.page_packages.generation import validate_blueprint_replacements
from app.domains.page_packages.schemas import (
    FieldReplacement,
    GeneratedBlueprintPackage,
    GeneratedPagePackage,
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
