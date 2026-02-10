"""Authentication and authorization utilities."""

from src.auth.api_keys import (
    generate_api_key,
    hash_api_key,
    validate_api_key_format,
)
from src.auth.dependencies import (
    get_current_user,
    require_role,
)
from src.auth.jwt import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.auth.password import (
    hash_password,
    validate_password_strength,
    verify_password,
)

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "generate_api_key",
    "get_current_user",
    "hash_api_key",
    "hash_password",
    "require_role",
    "TokenPayload",
    "validate_api_key_format",
    "validate_password_strength",
    "verify_password",
]
