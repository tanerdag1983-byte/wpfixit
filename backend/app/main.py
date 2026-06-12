from fastapi import FastAPI

app = FastAPI(
    title="WP FixPilot API",
    version="0.1.0",
    docs_url="/docs",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "wp-fixpilot-api",
    }

