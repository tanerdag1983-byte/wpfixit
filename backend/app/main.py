from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes.ai_settings import router as ai_settings_router
from app.api.routes.crawls import router as crawls_router
from app.api.routes.dataforseo import router as dataforseo_router
from app.api.routes.dashboards import router as dashboards_router
from app.api.routes.ga4 import router as ga4_router
from app.api.routes.google import router as google_router
from app.api.routes.page_packages import router as page_packages_router
from app.api.routes.preferences import router as preferences_router
from app.api.routes.priorities import router as priorities_router
from app.api.routes.projects import router as projects_router
from app.api.routes.wordpress import router as wordpress_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    configuration_errors = settings.production_configuration_errors()
    if configuration_errors:
        raise RuntimeError(
            "Missing production configuration: "
            + ", ".join(configuration_errors)
        )
    application = FastAPI(
        title="WP FixPilot API",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_host_list(),
    )
    application.include_router(projects_router)
    application.include_router(wordpress_router)
    application.include_router(dashboards_router)
    application.include_router(crawls_router)
    application.include_router(dataforseo_router)
    application.include_router(page_packages_router)
    application.include_router(ai_settings_router)
    application.include_router(google_router)
    application.include_router(priorities_router)
    application.include_router(preferences_router)
    application.include_router(ga4_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "wp-fixpilot-api",
        }

    return application


app = create_app()
