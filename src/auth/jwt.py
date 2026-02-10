"""JWT access and refresh token management."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from src.settings import load_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenPayload:
    """Decoded JWT token payload."""

    sub: UUID
    team_id: Optional[UUID]
    role: Optional[str]
    exp: datetime
    token_type: str


def create_access_token(user_id: UUID, team_id: UUID, role: str) -> str:
    """
    Create a JWT access token for authenticated user.

    Args:
        user_id: User UUID to encode in token
        team_id: Team UUID for scoping access
        role: User's role in the team

    Returns:
        Signed JWT access token string

    Raises:
        ValueError: If jwt_secret_key is not configured
    """
    settings = load_settings()

    if not settings.jwt_secret_key:
        raise ValueError("jwt_secret_key must be configured in settings")

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    payload = {
        "sub": str(user_id),
        "team_id": str(team_id),
        "role": role,
        "exp": exp,
        "type": "access",
    }

    try:
        token: str = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        logger.info(
            f"access_token_created: user_id={user_id}, team_id={team_id}, "
            f"role={role}, exp={exp.isoformat()}"
        )
        return token
    except Exception as e:
        logger.exception(f"access_token_creation_error: user_id={user_id}, error={str(e)}")
        raise ValueError(f"Failed to create access token: {str(e)}") from e


def create_refresh_token(user_id: UUID) -> str:
    """
    Create a JWT refresh token for token renewal.

    Args:
        user_id: User UUID to encode in token

    Returns:
        Signed JWT refresh token string

    Raises:
        ValueError: If jwt_secret_key is not configured
    """
    settings = load_settings()

    if not settings.jwt_secret_key:
        raise ValueError("jwt_secret_key must be configured in settings")

    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    payload = {
        "sub": str(user_id),
        "exp": exp,
        "type": "refresh",
    }

    try:
        token: str = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        logger.info(f"refresh_token_created: user_id={user_id}, exp={exp.isoformat()}")
        return token
    except Exception as e:
        logger.exception(f"refresh_token_creation_error: user_id={user_id}, error={str(e)}")
        raise ValueError(f"Failed to create refresh token: {str(e)}") from e


def decode_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string to decode

    Returns:
        TokenPayload with decoded user_id, team_id, role, expiry, and token_type

    Raises:
        ValueError: If token is expired, invalid, or malformed
    """
    settings = load_settings()

    if not settings.jwt_secret_key:
        raise ValueError("jwt_secret_key must be configured in settings")

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

        # Parse required fields
        user_id = UUID(payload["sub"])
        token_type = payload["type"]
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

        # Parse optional fields (only present in access tokens)
        team_id = UUID(payload["team_id"]) if "team_id" in payload else None
        role = payload.get("role")

        logger.info(f"token_decoded: user_id={user_id}, type={token_type}")

        return TokenPayload(
            sub=user_id,
            team_id=team_id,
            role=role,
            exp=exp,
            token_type=token_type,
        )
    except ExpiredSignatureError as e:
        logger.warning(f"token_expired: error={str(e)}")
        raise ValueError("Token has expired") from e
    except JWTError as e:
        logger.warning(f"token_invalid: error={str(e)}")
        raise ValueError("Invalid token") from e
    except (KeyError, ValueError) as e:
        logger.warning(f"token_parse_error: error={str(e)}")
        raise ValueError("Invalid token") from e
