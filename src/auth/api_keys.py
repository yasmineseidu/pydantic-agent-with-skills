"""API key generation, hashing, and validation."""

import hashlib
import logging
import secrets
import re

logger = logging.getLogger(__name__)

# API key constants
API_KEY_PREFIX = "ska_"
API_KEY_RANDOM_BYTES = 32  # 32 bytes = 64 hex chars
API_KEY_TOTAL_LENGTH = len(API_KEY_PREFIX) + (API_KEY_RANDOM_BYTES * 2)  # 68 chars
API_KEY_PREFIX_LENGTH = 12


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key with prefix and hash.

    Generates a cryptographically secure random API key. The full key is
    returned once to the user and NEVER stored. Only the hash is stored
    in the database for verification.

    Returns:
        A tuple of (full_key, key_prefix, key_hash):
        - full_key: Complete key (ska_... 68 chars total), shown to user once
        - key_prefix: First 12 chars (ska_a1b2c3d4...), stored for display
        - key_hash: SHA-256 hex digest, stored in database for lookup

    Example:
        >>> full, prefix, hash_val = generate_api_key()
        >>> len(full)
        68
        >>> full.startswith("ska_")
        True
        >>> len(prefix)
        12
        >>> len(hash_val)
        64
    """
    # Generate cryptographically secure random bytes
    random_bytes = secrets.token_hex(API_KEY_RANDOM_BYTES)
    full_key = API_KEY_PREFIX + random_bytes

    # Extract prefix (first 12 chars: "ska_" + 8 hex chars)
    key_prefix = full_key[:API_KEY_PREFIX_LENGTH]

    # Hash the full key for database storage
    key_hash = hashlib.sha256(full_key.encode("utf-8")).hexdigest()

    logger.info(f"generate_api_key: prefix={key_prefix}, hash_len={len(key_hash)}")

    return full_key, key_prefix, key_hash


def hash_api_key(key: str) -> str:
    """
    Hash an API key using SHA-256.

    Deterministic hashing used for lookup when validating API requests.
    The hash of a key matches the hash returned from generate_api_key().

    Args:
        key: The API key to hash

    Returns:
        SHA-256 hex digest of the key (64 character string)

    Example:
        >>> key = "ska_" + "a" * 64
        >>> hash_val = hash_api_key(key)
        >>> len(hash_val)
        64
        >>> hash_api_key(key) == hash_api_key(key)
        True
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def validate_api_key_format(key: str) -> bool:
    """
    Validate API key format without checking if it exists in the database.

    Validates the format of an API key:
    - Must start with "ska_" prefix
    - Total length must be 68 characters
    - Remaining 64 characters must be valid hexadecimal

    This is a format check only. It does NOT verify if the key is active,
    belongs to a user, or exists in the database.

    Args:
        key: The API key to validate

    Returns:
        True if format is valid, False otherwise

    Example:
        >>> validate_api_key_format("ska_" + "a" * 64)
        True
        >>> validate_api_key_format("ska_" + "g" * 64)
        False
        >>> validate_api_key_format("invalid_key")
        False
    """
    # Check prefix
    if not key.startswith(API_KEY_PREFIX):
        return False

    # Check total length
    if len(key) != API_KEY_TOTAL_LENGTH:
        return False

    # Extract the random portion and validate it's hex
    random_part = key[len(API_KEY_PREFIX) :]

    # Check if all characters are valid hex (0-9, a-f, A-F)
    if not re.match(r"^[0-9a-fA-F]+$", random_part):
        return False

    return True
