"""FastAPI dependencies for authentication and authorization."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Header, Request, WebSocket
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.api_keys import hash_api_key, validate_api_key_format
from src.auth.jwt import decode_token, TokenPayload
from src.auth.permissions import check_team_permission
from src.db.models.auth import ApiKeyORM
from src.db.models.user import UserORM
from src.db.engine import get_session
from src.settings import Settings, load_settings

logger = logging.getLogger(__name__)


async def get_current_user(
    authorization: str = Header(...),
    settings: Settings = Depends(load_settings),
    request: Request,
) -> tuple[UserORM, Optional[UUID]]:
    """
    Extract and validate user from Authorization header (JWT or API key).

    Supports two authentication modes:
    - Bearer token: "Bearer <jwt_token>" → validates JWT and returns user
    - API key: "ApiKey <ska_...>" → validates API key and returns user

    Args:
        authorization: Authorization header value (required)
        request: FastAPI request object (for app.state engine)
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

    if request is None:
        logger.error("get_current_user_error: reason=request_missing")
        raise HTTPException(status_code=500, detail="Request context unavailable")

    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        logger.error("get_current_user_error: reason=engine_not_initialized")
        raise HTTPException(
            status_code=500,
            detail="Database engine not initialized. Ensure DATABASE_URL is set and app lifespan has run.",
        )

    async for session in get_session(engine):
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

                if payload.team_id:
                    request.state.team_id = payload.team_id

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
                logger.exception(
                    f"get_current_user_error: reason=unexpected_jwt_error, error={str(e)}"
                )
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

            request.state.team_id = api_key.team_id

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

    logger.error("get_current_user_error: reason=session_unavailable")
    raise HTTPException(status_code=500, detail="Authentication failed due to session error")


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


async def authenticate_websocket(
    websocket: WebSocket,
    db: AsyncSession,
    settings: Settings,
) -> tuple[UserORM, UUID]:
    """Authenticate a WebSocket connection via query param or first message.

    Supports two auth methods:
    1. Query parameter: ?token=<jwt> - validated before accept
    2. First message: {"type": "auth", "token": "..."} - with 10s timeout after accept

    Args:
        websocket: The WebSocket connection to authenticate.
        db: Async database session for user lookups.
        settings: Application settings with JWT configuration.

    Returns:
        Tuple of (UserORM, team_id) on successful authentication.

    Raises:
        WebSocketDisconnect: Connection closed with code 4001 on auth failure.
    """
    token: Optional[str] = websocket.query_params.get("token")

    if token:
        # Method 1: Query parameter auth (validate before accept)
        user, team_id = await _validate_ws_token(token, db)
        if user is None or team_id is None:
            await websocket.close(code=4001, reason="Authentication failed")
            raise WebSocketDisconnect(code=4001, reason="Authentication failed")
        await websocket.accept()
        logger.info(
            f"authenticate_websocket_success: method=query_param, user_id={user.id}, "
            f"team_id={team_id}"
        )
        return user, team_id

    # Method 2: First message auth (accept first, then wait for auth message)
    await websocket.accept()
    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("authenticate_websocket_error: reason=authentication_timeout")
        await websocket.close(code=4001, reason="Authentication timeout")
        raise WebSocketDisconnect(code=4001, reason="Authentication timeout")
    except Exception as e:
        logger.warning(f"authenticate_websocket_error: reason=receive_failed, error={str(e)}")
        await websocket.close(code=4001, reason="Authentication failed")
        raise WebSocketDisconnect(code=4001, reason="Authentication failed")

    # Validate message structure
    if not isinstance(message, dict) or message.get("type") != "auth" or "token" not in message:
        logger.warning("authenticate_websocket_error: reason=invalid_auth_message")
        await websocket.close(code=4001, reason="Authentication failed")
        raise WebSocketDisconnect(code=4001, reason="Authentication failed")

    user, team_id = await _validate_ws_token(message["token"], db)
    if user is None or team_id is None:
        await websocket.close(code=4001, reason="Authentication failed")
        raise WebSocketDisconnect(code=4001, reason="Authentication failed")

    await websocket.send_json({"type": "auth_ok"})
    logger.info(
        f"authenticate_websocket_success: method=first_message, user_id={user.id}, "
        f"team_id={team_id}"
    )
    return user, team_id


async def _validate_ws_token(
    token: str,
    db: AsyncSession,
) -> tuple[Optional[UserORM], Optional[UUID]]:
    """Validate a JWT token for WebSocket authentication.

    Args:
        token: JWT token string to validate.
        db: Async database session for user lookup.

    Returns:
        Tuple of (UserORM, team_id) on success, or (None, None) on failure.
    """
    try:
        payload: TokenPayload = decode_token(token)

        if payload.token_type != "access":
            logger.warning(
                f"_validate_ws_token_error: reason=invalid_token_type, type={payload.token_type}"
            )
            return None, None

        now = datetime.now(timezone.utc)
        if payload.exp < now:
            logger.warning(f"_validate_ws_token_error: reason=token_expired, user_id={payload.sub}")
            return None, None

        if not payload.team_id:
            logger.warning(
                f"_validate_ws_token_error: reason=missing_team_id, user_id={payload.sub}"
            )
            return None, None

        stmt = select(UserORM).where(UserORM.id == payload.sub)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(
                f"_validate_ws_token_error: reason=user_not_found, user_id={payload.sub}"
            )
            return None, None

        if not user.is_active:
            logger.warning(f"_validate_ws_token_error: reason=user_inactive, user_id={user.id}")
            return None, None

        return user, payload.team_id

    except ValueError as e:
        logger.warning(f"_validate_ws_token_error: reason=jwt_decode_failed, error={str(e)}")
        return None, None
    except Exception as e:
        logger.exception(f"_validate_ws_token_error: reason=unexpected_error, error={str(e)}")
        return None, None
