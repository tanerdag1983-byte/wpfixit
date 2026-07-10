import hashlib
import secrets


def new_project_key() -> tuple[str, str]:
    raw = "wpfx_" + secrets.token_urlsafe(32)
    return raw, hash_project_key(raw)


def hash_project_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
