"""Password hashing and validation using bcrypt."""

import logging
import re

import bcrypt

logger = logging.getLogger(__name__)

# Password validation constants
MIN_LENGTH = 8
ROUNDS = 12


def validate_password_strength(password: str) -> list[str]:
    """
    Validate password strength against security requirements.

    Returns a list of validation error messages. An empty list means the
    password is valid.

    Requirements:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit

    Args:
        password: The password string to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    if len(password) < MIN_LENGTH:
        errors.append(f"Password must be at least {MIN_LENGTH} characters long")

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r"[0-9]", password):
        errors.append("Password must contain at least one digit")

    return errors


def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password using bcrypt with 12 rounds.

    Validates password strength before hashing. Raises ValueError if
    the password does not meet security requirements.

    Args:
        plain_password: The plaintext password to hash

    Returns:
        The bcrypt hash as a string

    Raises:
        ValueError: If password fails strength validation
    """
    # Validate password strength first
    validation_errors = validate_password_strength(plain_password)
    if validation_errors:
        error_msg = "; ".join(validation_errors)
        raise ValueError(error_msg)

    logger.info("hash_password: generating bcrypt hash with rounds=12")

    # Hash the password
    salt = bcrypt.gensalt(rounds=ROUNDS)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)

    # Return as string
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.

    Uses bcrypt's timing-safe comparison. Never raises exceptions on
    mismatch - only returns False.

    Args:
        plain_password: The plaintext password to verify
        hashed_password: The bcrypt hash to verify against

    Returns:
        True if password matches, False otherwise
    """
    try:
        logger.info("verify_password: checking password against hash")

        # bcrypt.checkpw performs timing-safe comparison
        result = bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

        return result

    except (ValueError, TypeError):
        # Invalid hash format or encoding issues
        logger.warning("verify_password: hash validation failed, returning False")
        return False
