import hashlib
import html
import json

from app.domains.page_packages.schemas import (
    GeneratedPagePackage,
    PagePackageContext,
    PagePackageGenerationResult,
)
from app.domains.recommendations.provider import ProviderGenerationError


def page_package_system_prompt(company_context: str) -> str:
    return (
        "Maak een complete Nederlandse SEO-landingspagina als strikt JSON volgens "
        "het opgegeven schema. Gebruik het focuszoekwoord natuurlijk, houd merk- en "
        "voertuigentiteiten exact gescheiden en verzin geen garanties, prijzen, "
        "locaties of certificeringen. Gebruik alleen de aangeleverde interne links. "
        "Alle HTML moet "
        "semantisch zijn en mag geen scripts, formulieren, inline event handlers of "
        "javascript-URL's bevatten. Het resultaat is een concept voor menselijke "
        "beoordeling en mag nooit automatisch worden gepubliceerd.\n\n"
        f"Projectcontext:\n{company_context[:10_000] or 'Niet ingesteld.'}"
    )


def generation_result(
    package: GeneratedPagePackage,
    *,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> PagePackageGenerationResult:
    return PagePackageGenerationResult(
        package=package,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


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
                "contract": "page-package-v1",
                "context": context.model_dump(),
                "model": model,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()


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
