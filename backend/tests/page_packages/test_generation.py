import pytest
from pydantic import ValidationError

from app.domains.page_packages.schemas import GeneratedPagePackage


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
