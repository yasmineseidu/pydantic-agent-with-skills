"""Authentication request/response schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """User registration request.

    Args:
        email: Valid email address (RFC 5322 simplified pattern)
        password: Password with minimum 8 characters
        display_name: User's display name (1-100 characters)
    """

    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    password: str = Field(..., min_length=8)
    display_name: str = Field(..., min_length=1, max_length=100)


class LoginRequest(BaseModel):
    """User login request.

    Args:
        email: User's registered email address
        password: User's password
    """

    email: str
    password: str


class TokenPair(BaseModel):
    """JWT access and refresh tokens.

    Args:
        access_token: Short-lived JWT for API requests (typically 15-60 minutes)
        refresh_token: Long-lived JWT for obtaining new access tokens (typically 7-30 days)
        token_type: Token type identifier (always "bearer")
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Successful login response.

    Args:
        tokens: JWT token pair for authentication
        user_id: ID of the authenticated user
        team_id: ID of the user's primary team
    """

    tokens: TokenPair
    user_id: UUID
    team_id: UUID


class RefreshRequest(BaseModel):
    """Token refresh request.

    Args:
        refresh_token: Valid refresh token obtained from login
    """

    refresh_token: str


class ApiKeyCreate(BaseModel):
    """Create a new API key request.

    Args:
        name: Descriptive name for the API key (1-100 characters)
        scopes: List of permission scopes (e.g., ["read:agents", "write:chat"])
        expires_in_days: Optional expiration period in days (1-365), None for no expiration
    """

    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=list)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


class ApiKeyResponse(BaseModel):
    """API key metadata response.

    Args:
        id: Unique API key identifier
        name: Descriptive name
        key_prefix: First 8 characters of the key (e.g., "sk_live_abc12345...")
        scopes: Permission scopes
        created_at: Creation timestamp
        expires_at: Expiration timestamp (None if no expiration)
        last_used_at: Last usage timestamp (None if never used)
        is_active: Whether the key is currently active
    """

    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Response when creating a new API key — includes the full key (shown once).

    Args:
        full_key: Complete API key (only returned at creation time, never stored in plaintext)

    Note:
        The full_key is only returned once. Users must store it securely.
        Subsequent GET requests will only return the key_prefix.
    """

    full_key: str
