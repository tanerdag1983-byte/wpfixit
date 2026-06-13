from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionConfigurationError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise EncryptionConfigurationError("WP_FIXPILOT_ENCRYPTION_KEY is required")
    return Fernet(key.encode())


def encrypt_text(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_text(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as error:
        raise EncryptionConfigurationError(
            "Encrypted value cannot be decrypted"
        ) from error
