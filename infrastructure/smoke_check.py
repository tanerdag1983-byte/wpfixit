#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PRODUCTION_ENV = (
    "WP_FIXPILOT_DATABASE_URL",
    "WP_FIXPILOT_FRONTEND_URL",
    "WP_FIXPILOT_CORS_ORIGINS",
    "WP_FIXPILOT_TRUSTED_HOSTS",
    "WP_FIXPILOT_SUPABASE_URL",
    "WP_FIXPILOT_ENCRYPTION_KEY",
)


def configuration_errors() -> list[str]:
    errors = []
    if os.getenv("WP_FIXPILOT_ENVIRONMENT") == "production":
        errors.extend(
            f"missing environment variable: {name}"
            for name in REQUIRED_PRODUCTION_ENV
            if not os.getenv(name)
        )

    render = ROOT / "infrastructure/render.yaml"
    if "healthCheckPath: /health" not in render.read_text():
        errors.append("Render health check is not configured")

    with (ROOT / "frontend/vercel.json").open() as file:
        vercel = json.load(file)
    if not vercel.get("rewrites"):
        errors.append("Vercel SPA rewrite is not configured")

    with (ROOT / "infrastructure/supabase/config.toml").open("rb") as file:
        supabase = tomllib.load(file)
    if supabase.get("auth", {}).get("site_url") != "http://localhost:5173":
        errors.append("Supabase local site URL is invalid")
    return errors


def health_error(url: str) -> str | None:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=10) as response:
            payload = json.load(response)
    except Exception as error:
        return f"API health check failed: {error}"
    if payload.get("status") != "ok":
        return "API health response did not report ok"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url")
    args = parser.parse_args()
    errors = configuration_errors()
    if args.api_url:
        error = health_error(args.api_url)
        if error:
            errors.append(error)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    print("Deployment smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
