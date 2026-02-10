"""Authentication API endpoints for Phase 4 auth system."""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db, get_settings
from src.api.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from src.auth.api_keys import generate_api_key
from src.auth.dependencies import get_current_user, require_role
from src.auth.jwt import create_access_token, create_refresh_token, decode_token
from src.auth.password import hash_password, verify_password
from src.db.models.auth import ApiKeyORM, RefreshTokenORM
from src.db.models.user import TeamMembershipORM, TeamORM, UserORM, UserRole
from src.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=LoginResponse, status_code=201)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """
    Register a new user account with automatic team creation.

    Creates a new user, a personal team owned by the user, and a team
    membership with the 'owner' role. Returns JWT token pair for immediate
    authentication.

    Args:
        request: Registration details (email, password, display_name)
        db: Async database session
        settings: Application settings for JWT configuration

    Returns:
        LoginResponse with tokens, user_id, and team_id

    Raises:
        HTTPException: 400 if email already exists or password validation fails
        HTTPException: 500 if database error occurs

    Rate Limit:
        10 requests per minute per IP (implemented in Wave 5)
    """
    # Check if email already exists
    stmt = select(UserORM).where(UserORM.email == request.email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        logger.warning(f"register_error: reason=email_exists, email={request.email}")
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password (raises ValueError if weak)
    try:
        password_hash = hash_password(request.password)
    except ValueError as e:
        logger.warning(f"register_error: reason=weak_password, email={request.email}")
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Create user
    user = UserORM(
        email=request.email,
        password_hash=password_hash,
        display_name=request.display_name,
        is_active=True,
    )
    db.add(user)
    await db.flush()  # Get user.id for team creation

    # Create team (slug = email prefix + random suffix for uniqueness)
    team_slug = f"{request.email.split('@')[0]}-{user.id.hex[:8]}"
    team = TeamORM(
        name=f"{request.display_name}'s Team",
        slug=team_slug,
        owner_id=user.id,
        settings={},
        shared_skill_names=[],
    )
    db.add(team)
    await db.flush()  # Get team.id for membership

    # Create team membership (owner role)
    membership = TeamMembershipORM(
        user_id=user.id,
        team_id=team.id,
        role=UserRole.OWNER,
    )
    db.add(membership)

    # Create tokens
    access_token = create_access_token(user.id, team.id, UserRole.OWNER.value)
    refresh_token_str = create_refresh_token(user.id)

    # Store refresh token in database
    token_hash = hashlib.sha256(refresh_token_str.encode("utf-8")).hexdigest()
    refresh_token = RefreshTokenORM(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.jwt_refresh_token_expire_days),
    )
    db.add(refresh_token)

    await db.commit()

    logger.info(f"register_success: user_id={user.id}, team_id={team.id}, email={request.email}")

    return LoginResponse(
        tokens=TokenPair(
            access_token=access_token,
            refresh_token=refresh_token_str,
            token_type="bearer",
        ),
        user_id=user.id,
        team_id=team.id,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    Authenticate user and return JWT token pair.

    Validates email and password, then returns access and refresh tokens.
    Uses same error message for wrong password and non-existent email to
    prevent user enumeration attacks.

    Args:
        request: Login credentials (email, password)
        db: Async database session

    Returns:
        LoginResponse with tokens, user_id, and team_id

    Raises:
        HTTPException: 401 if credentials are invalid or user is inactive

    Rate Limit:
        10 requests per minute per IP (implemented in Wave 5)
    """
    # Look up user by email
    stmt = select(UserORM).where(UserORM.email == request.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # CRITICAL: Same error for wrong password AND non-existent email (no user enumeration)
    if not user or not verify_password(request.password, user.password_hash):
        logger.warning(f"login_error: reason=invalid_credentials, email={request.email}")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check if user is active
    if not user.is_active:
        logger.warning(f"login_error: reason=user_inactive, user_id={user.id}")
        raise HTTPException(status_code=401, detail="User account is inactive")

    # Get user's primary team (first membership, ordered by created_at)
    membership_stmt = (
        select(TeamMembershipORM)
        .where(TeamMembershipORM.user_id == user.id)
        .order_by(TeamMembershipORM.created_at)
        .limit(1)
    )
    membership_result = await db.execute(membership_stmt)
    membership: TeamMembershipORM | None = membership_result.scalar_one_or_none()

    if not membership:
        logger.error(f"login_error: reason=no_team_membership, user_id={user.id}")
        raise HTTPException(status_code=500, detail="User has no team membership")

    # Create tokens
    access_token = create_access_token(user.id, membership.team_id, membership.role)
    refresh_token_str = create_refresh_token(user.id)

    # Store refresh token in database
    token_hash = hashlib.sha256(refresh_token_str.encode("utf-8")).hexdigest()
    refresh_token = RefreshTokenORM(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),  # Default 7 days
    )
    db.add(refresh_token)
    await db.commit()

    logger.info(
        f"login_success: user_id={user.id}, team_id={membership.team_id}, role={membership.role}"
    )

    return LoginResponse(
        tokens=TokenPair(
            access_token=access_token,
            refresh_token=refresh_token_str,
            token_type="bearer",
        ),
        user_id=user.id,
        team_id=membership.team_id,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    """
    Refresh access token using a valid refresh token.

    Validates the refresh token, checks it has not been revoked, creates a
    new token pair, and revokes the old refresh token (refresh token rotation).

    Args:
        request: Refresh request with refresh_token
        db: Async database session
        settings: Application settings for JWT configuration

    Returns:
        New TokenPair with access_token and refresh_token

    Raises:
        HTTPException: 401 if refresh token is invalid, expired, or revoked
    """
    # Decode refresh token
    try:
        payload = decode_token(request.refresh_token)
    except ValueError as e:
        logger.warning(f"refresh_error: reason=invalid_token, error={str(e)}")
        raise HTTPException(status_code=401, detail=str(e)) from e

    # Verify token type
    if payload.token_type != "refresh":
        logger.warning(f"refresh_error: reason=invalid_token_type, type={payload.token_type}")
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Hash token for lookup
    token_hash = hashlib.sha256(request.refresh_token.encode("utf-8")).hexdigest()

    # Look up token in database
    stmt = select(RefreshTokenORM).where(RefreshTokenORM.token_hash == token_hash)
    result = await db.execute(stmt)
    stored_token = result.scalar_one_or_none()

    if not stored_token:
        logger.warning(f"refresh_error: reason=token_not_found, user_id={payload.sub}")
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Check if revoked
    if stored_token.revoked_at is not None:
        logger.warning(
            f"refresh_error: reason=token_revoked, user_id={payload.sub}, "
            f"revoked_at={stored_token.revoked_at.isoformat()}"
        )
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    # Check expiry (already checked by decode_token, but be explicit)
    now = datetime.now(timezone.utc)
    if stored_token.expires_at < now:
        logger.warning(
            f"refresh_error: reason=token_expired, user_id={payload.sub}, "
            f"expired_at={stored_token.expires_at.isoformat()}"
        )
        raise HTTPException(status_code=401, detail="Refresh token has expired")

    # Get user's primary team
    membership_stmt = (
        select(TeamMembershipORM)
        .where(TeamMembershipORM.user_id == payload.sub)
        .order_by(TeamMembershipORM.created_at)
        .limit(1)
    )
    membership_result = await db.execute(membership_stmt)
    membership: TeamMembershipORM | None = membership_result.scalar_one_or_none()

    if not membership:
        logger.error(f"refresh_error: reason=no_team_membership, user_id={payload.sub}")
        raise HTTPException(status_code=500, detail="User has no team membership")

    # Create new token pair
    new_access_token = create_access_token(payload.sub, membership.team_id, membership.role)
    new_refresh_token_str = create_refresh_token(payload.sub)

    # Store new refresh token
    new_token_hash = hashlib.sha256(new_refresh_token_str.encode("utf-8")).hexdigest()
    new_refresh_token = RefreshTokenORM(
        user_id=payload.sub,
        token_hash=new_token_hash,
        expires_at=now + timedelta(days=settings.jwt_refresh_token_expire_days),
    )
    db.add(new_refresh_token)

    # Revoke old refresh token (refresh token rotation)
    stored_token.revoked_at = now
    db.add(stored_token)

    await db.commit()

    logger.info(
        f"refresh_success: user_id={payload.sub}, team_id={membership.team_id}, "
        f"old_token_revoked=True"
    )

    return TokenPair(
        access_token=new_access_token,
        refresh_token=new_refresh_token_str,
        token_type="bearer",
    )


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_api_key(
    request: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: tuple[UserORM, Optional[UUID]] = Depends(require_role("admin")),
) -> ApiKeyCreatedResponse:
    """
    Create a new API key (requires admin role or higher).

    Generates a cryptographically secure API key. The full key is returned
    ONCE and never stored. Only the hash is stored in the database.

    Args:
        request: API key creation details (name, scopes, expires_in_days)
        db: Async database session
        current_user: Authenticated user and team_id (from require_role dependency)

    Returns:
        ApiKeyCreatedResponse with full_key (shown once) and metadata

    Raises:
        HTTPException: 403 if user lacks admin role
        HTTPException: 401 if team_id not available in auth context
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(f"create_api_key_error: user_id={user.id}, reason=no_team_context")
        raise HTTPException(status_code=401, detail="Team context required")

    # Generate API key
    full_key, key_prefix, key_hash = generate_api_key()

    # Calculate expiration
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=request.expires_in_days)

    # Create API key record
    api_key = ApiKeyORM(
        team_id=team_id,
        user_id=user.id,
        name=request.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=request.scopes,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)  # Get created_at timestamp

    logger.info(
        f"api_key_created: user_id={user.id}, team_id={team_id}, "
        f"key_prefix={key_prefix}, name={request.name}, "
        f"expires_at={expires_at.isoformat() if expires_at else 'never'}"
    )

    return ApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        is_active=api_key.is_active,
        full_key=full_key,  # ONLY returned at creation time
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
) -> list[ApiKeyResponse]:
    """
    List all API keys for the authenticated user.

    Returns metadata for all API keys created by the user. Does NOT include
    full keys (only prefix). Users can see their own keys regardless of role.

    Args:
        db: Async database session
        current_user: Authenticated user and team_id (from get_current_user dependency)

    Returns:
        List of ApiKeyResponse with metadata (no full keys)
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(f"list_api_keys_error: user_id={user.id}, reason=no_team_context")
        raise HTTPException(status_code=401, detail="Team context required")

    # Get all API keys for user in team
    stmt = (
        select(ApiKeyORM)
        .where(ApiKeyORM.user_id == user.id, ApiKeyORM.team_id == team_id)
        .order_by(ApiKeyORM.created_at.desc())
    )
    result = await db.execute(stmt)
    api_keys = result.scalars().all()

    logger.info(
        f"list_api_keys_success: user_id={user.id}, team_id={team_id}, count={len(api_keys)}"
    )

    return [
        ApiKeyResponse(
            id=key.id,
            name=key.name,
            key_prefix=key.key_prefix,
            scopes=key.scopes,
            created_at=key.created_at,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
            is_active=key.is_active,
        )
        for key in api_keys
    ]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
) -> None:
    """
    Revoke an API key (set is_active=False).

    Users can revoke their own keys. Admins can revoke any key in their team.

    Args:
        key_id: UUID of the API key to revoke
        db: Async database session
        current_user: Authenticated user and team_id

    Raises:
        HTTPException: 404 if API key not found
        HTTPException: 403 if user doesn't own the key (and is not admin)
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(f"revoke_api_key_error: user_id={user.id}, reason=no_team_context")
        raise HTTPException(status_code=401, detail="Team context required")

    # Look up API key
    stmt = select(ApiKeyORM).where(ApiKeyORM.id == key_id, ApiKeyORM.team_id == team_id)
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if not api_key:
        logger.warning(
            f"revoke_api_key_error: user_id={user.id}, team_id={team_id}, "
            f"key_id={key_id}, reason=not_found"
        )
        raise HTTPException(status_code=404, detail="API key not found")

    # Check ownership (users can revoke their own keys, admins can revoke any)
    if api_key.user_id != user.id:
        # Check if user is admin or higher
        membership_stmt = select(TeamMembershipORM).where(
            TeamMembershipORM.user_id == user.id, TeamMembershipORM.team_id == team_id
        )
        membership_result = await db.execute(membership_stmt)
        membership: TeamMembershipORM | None = membership_result.scalar_one_or_none()

        if not membership or membership.role not in [UserRole.ADMIN, UserRole.OWNER]:
            logger.warning(
                f"revoke_api_key_error: user_id={user.id}, team_id={team_id}, "
                f"key_id={key_id}, reason=not_owner_or_admin"
            )
            raise HTTPException(
                status_code=403,
                detail="Cannot revoke another user's API key (requires admin role)",
            )

    # Revoke key (set is_active=False)
    api_key.is_active = False
    db.add(api_key)
    await db.commit()

    logger.info(
        f"api_key_revoked: user_id={user.id}, team_id={team_id}, key_id={key_id}, "
        f"key_prefix={api_key.key_prefix}"
    )
