"""FastAPI dependencies for authentication and authorization."""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.api_keys import hash_api_key, validate_api_key_format
from src.auth.jwt import decode_token, TokenPayload
from src.auth.permissions import check_team_permission
from src.db.models.auth import ApiKeyORM
from src.db.models.user import UserORM
from src.settings import Settings, load_settings

logger = logging.getLogger(__name__)


async def get_current_user(
    authorization: str = Header(...),
    settings: Settings = Depends(load_settings),
    session: AsyncSession = Depends(lambda: None),  # Will be overridden by routes that use this
) -> tuple[UserORM, Optional[UUID]]:
    """
    Extract and validate user from Authorization header (JWT or API key).

    Supports two authentication modes:
    - Bearer token: "Bearer <jwt_token>" → validates JWT and returns user
    - API key: "ApiKey <ska_...>" → validates API key and returns user

    Args:
        authorization: Authorization header value (required)
        session: Async SQLAlchemy session for database operations
        settings: Application settings with JWT configuration

    Returns:
        Tuple of (UserORM, team_id):
        - UserORM: Authenticated user object
        - team_id: UUID from JWT claims or API key's team_id (None if not available)

    Raises:
        HTTPException: 401 if authorization header is missing, malformed, invalid, or expired
        HTTPException: 401 if user not found in database

    Example:
        >>> # In a route
        >>> @router.get("/me")
        >>> async def get_me(current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user)):
        >>>     user, team_id = current_user
        >>>     return {"email": user.email, "team_id": str(team_id)}
    """
    if not authorization:
        logger.warning("get_current_user_error: reason=missing_authorization_header")
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Split authorization header: "Bearer <token>" or "ApiKey <key>"
    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        logger.warning("get_current_user_error: reason=malformed_authorization_header")
        raise HTTPException(status_code=401, detail="Malformed Authorization header")

    auth_type, credential = parts

    # Route 1: Bearer JWT token
    if auth_type.lower() == "bearer":
        try:
            payload: TokenPayload = decode_token(credential)

            # Verify token type
            if payload.token_type != "access":
                logger.warning(
                    f"get_current_user_error: reason=invalid_token_type, type={payload.token_type}"
                )
                raise HTTPException(status_code=401, detail="Invalid token type")

            # Check expiry (decode_token already checks, but be explicit)
            now = datetime.now(timezone.utc)
            if payload.exp < now:
                logger.warning(
                    f"get_current_user_error: reason=token_expired, user_id={payload.sub}"
                )
                raise HTTPException(status_code=401, detail="Token has expired")

            # Look up user in database
            stmt = select(UserORM).where(UserORM.id == payload.sub)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                logger.warning(
                    f"get_current_user_error: reason=user_not_found, user_id={payload.sub}"
                )
                raise HTTPException(status_code=401, detail="User not found")

            if not user.is_active:
                logger.warning(f"get_current_user_error: reason=user_inactive, user_id={user.id}")
                raise HTTPException(status_code=401, detail="User account is inactive")

            logger.info(
                f"get_current_user_success: auth_type=bearer, user_id={user.id}, "
                f"team_id={payload.team_id}, role={payload.role}"
            )
            return user, payload.team_id

        except ValueError as e:
            # decode_token raises ValueError for invalid/expired tokens
            logger.warning(f"get_current_user_error: reason=jwt_decode_failed, error={str(e)}")
            raise HTTPException(status_code=401, detail=str(e)) from e
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"get_current_user_error: reason=unexpected_jwt_error, error={str(e)}")
            raise HTTPException(status_code=401, detail="Authentication failed") from e

    # Route 2: API Key
    elif auth_type.lower() == "apikey":
        # Validate format first (cheap check)
        if not validate_api_key_format(credential):
            logger.warning("get_current_user_error: reason=invalid_api_key_format")
            raise HTTPException(status_code=401, detail="Invalid API key format")

        # Hash key for lookup
        key_hash = hash_api_key(credential)

        # Look up API key in database
        api_key_stmt = select(ApiKeyORM).where(ApiKeyORM.key_hash == key_hash)
        api_key_result = await session.execute(api_key_stmt)
        api_key = api_key_result.scalar_one_or_none()

        if not api_key:
            logger.warning("get_current_user_error: reason=api_key_not_found")
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Check if key is active
        if not api_key.is_active:
            logger.warning(
                f"get_current_user_error: reason=api_key_inactive, key_prefix={api_key.key_prefix}"
            )
            raise HTTPException(status_code=401, detail="API key is inactive")

        # Check if key has expired
        if api_key.expires_at:
            now = datetime.now(timezone.utc)
            if api_key.expires_at < now:
                logger.warning(
                    f"get_current_user_error: reason=api_key_expired, "
                    f"key_prefix={api_key.key_prefix}, expired_at={api_key.expires_at.isoformat()}"
                )
                raise HTTPException(status_code=401, detail="API key has expired")

        # Look up user
        user_stmt = select(UserORM).where(UserORM.id == api_key.user_id)
        user_result = await session.execute(user_stmt)
        user = user_result.scalar_one_or_none()

        if not user:
            logger.warning(
                f"get_current_user_error: reason=user_not_found_for_api_key, user_id={api_key.user_id}"
            )
            raise HTTPException(status_code=401, detail="User not found")

        if not user.is_active:
            logger.warning(
                f"get_current_user_error: reason=user_inactive, user_id={user.id}, "
                f"key_prefix={api_key.key_prefix}"
            )
            raise HTTPException(status_code=401, detail="User account is inactive")

        # Update last_used_at (fire and forget - don't await)
        # This is a common pattern for API key tracking
        api_key.last_used_at = datetime.now(timezone.utc)
        session.add(api_key)

        logger.info(
            f"get_current_user_success: auth_type=apikey, user_id={user.id}, "
            f"team_id={api_key.team_id}, key_prefix={api_key.key_prefix}"
        )
        return user, api_key.team_id

    else:
        logger.warning(f"get_current_user_error: reason=unsupported_auth_type, type={auth_type}")
        raise HTTPException(
            status_code=401,
            detail="Unsupported authorization type (use 'Bearer' or 'ApiKey')",
        )


def require_role(required_role: str) -> Callable:
    """
    Factory that creates a FastAPI dependency requiring a specific role level.

    Uses role hierarchy from ROLE_HIERARCHY: OWNER (4) > ADMIN (3) > MEMBER (2) > VIEWER (1).
    Higher roles inherit permissions of lower roles.

    Args:
        required_role: Minimum role required (owner/admin/member/viewer)

    Returns:
        FastAPI dependency function that enforces role requirement

    Raises:
        HTTPException: 403 if user lacks required role level
        HTTPException: 401 if team_id not available in auth context

    Example:
        >>> @router.delete("/agents/{agent_id}")
        >>> async def delete_agent(
        >>>     agent_id: UUID,
        >>>     current_user: tuple[UserORM, Optional[UUID]] = Depends(require_role("admin"))
        >>> ):
        >>>     user, team_id = current_user
        >>>     # Only admins and owners can reach here
        >>>     ...
    """

    async def role_checker(
        current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
        session: AsyncSession = Depends(),
    ) -> tuple[UserORM, Optional[UUID]]:
        """Check if user has required role level in their team."""
        user, team_id = current_user

        if not team_id:
            logger.warning(
                f"require_role_error: user_id={user.id}, required_role={required_role}, "
                f"reason=no_team_context"
            )
            raise HTTPException(
                status_code=401,
                detail="Team context required (JWT must include team_id or API key must be team-scoped)",
            )

        # Check permission using permissions.py logic
        has_permission = await check_team_permission(session, user.id, team_id, required_role)

        if not has_permission:
            logger.warning(
                f"require_role_denied: user_id={user.id}, team_id={team_id}, "
                f"required_role={required_role}"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions (requires {required_role} role or higher)",
            )

        logger.info(
            f"require_role_granted: user_id={user.id}, team_id={team_id}, "
            f"required_role={required_role}"
        )
        return user, team_id

    return role_checker
