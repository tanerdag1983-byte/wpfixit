from fastapi import FastAPI

from app.api.routes.projects import router as projects_router
from app.api.routes.wordpress import router as wordpress_router

app = FastAPI(
    title="WP FixPilot API",
    version="0.1.0",
    docs_url="/docs",
)
app.include_router(projects_router)
app.include_router(wordpress_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "wp-fixpilot-api",
    }
