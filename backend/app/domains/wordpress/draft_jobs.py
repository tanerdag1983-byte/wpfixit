import hashlib
import json
import secrets
from urllib.parse import urlsplit

JOB_CONTRACT_VERSION = "wordpress-draft-job-v1"


def new_project_key() -> tuple[str, str]:
    raw = "wpfx_" + secrets.token_urlsafe(32)
    return raw, hash_project_key(raw)


def hash_project_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def hash_draft_job_payload(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_site_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.casefold() != "https":
        raise ValueError("WordPress site URL must use HTTPS")
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("WordPress site URL must be an HTTPS origin")
    host = parsed.hostname.casefold()
    if ":" in host:
        host = f"[{host}]"
    authority = host if parsed.port in {None, 443} else f"{host}:{parsed.port}"
    return f"https://{authority}"
