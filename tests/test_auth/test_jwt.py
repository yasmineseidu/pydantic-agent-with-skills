"""Unit tests for JWT token management."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from uuid import uuid4

from jose import jwt as jose_jwt

from src.auth.jwt import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
)


@pytest.fixture
def mock_settings():
    """Fixture providing mocked settings with JWT configuration."""
    settings = MagicMock()
    settings.jwt_secret_key = "test-secret-key-for-unit-tests"
    settings.jwt_algorithm = "HS256"
    settings.jwt_access_token_expire_minutes = 30
    settings.jwt_refresh_token_expire_days = 7

    with patch("src.auth.jwt.load_settings", return_value=settings):
        yield settings


class TestTokenPayload:
    """Tests for TokenPayload dataclass."""

    def test_token_payload_is_frozen(self) -> None:
        """TokenPayload should be immutable (frozen dataclass)."""
        payload = TokenPayload(
            sub=uuid4(),
            team_id=uuid4(),
            role="admin",
            exp=datetime.now(timezone.utc),
            token_type="access",
        )
        with pytest.raises(AttributeError):
            payload.role = "member"  # type: ignore

    def test_token_payload_with_optional_fields_none(self) -> None:
        """TokenPayload with None optional fields should be valid."""
        uid = uuid4()
        payload = TokenPayload(
            sub=uid,
            team_id=None,
            role=None,
            exp=datetime.now(timezone.utc),
            token_type="refresh",
        )
        assert payload.sub == uid
        assert payload.team_id is None
        assert payload.role is None


class TestCreateAccessToken:
    """Tests for access token creation."""

    def test_returns_jwt_string(self, mock_settings: MagicMock) -> None:
        """Access token should return a valid JWT string."""
        token = create_access_token(uuid4(), uuid4(), "admin")
        assert isinstance(token, str)
        parts = token.split(".")
        assert len(parts) == 3  # header.payload.signature

    def test_contains_correct_claims(self, mock_settings: MagicMock) -> None:
        """Access token should contain all required claims."""
        uid = uuid4()
        tid = uuid4()
        token = create_access_token(uid, tid, "admin")

        payload = jose_jwt.decode(token, "test-secret-key-for-unit-tests", algorithms=["HS256"])

        assert payload["sub"] == str(uid)
        assert payload["team_id"] == str(tid)
        assert payload["role"] == "admin"
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_claims_with_different_roles(self, mock_settings: MagicMock) -> None:
        """Access token should preserve different role values."""
        uid = uuid4()
        tid = uuid4()

        for role in ["admin", "member", "viewer"]:
            token = create_access_token(uid, tid, role)
            payload = jose_jwt.decode(token, "test-secret-key-for-unit-tests", algorithms=["HS256"])
            assert payload["role"] == role

    def test_no_secret_raises_error(self) -> None:
        """Missing jwt_secret_key should raise ValueError."""
        settings = MagicMock()
        settings.jwt_secret_key = None

        with patch("src.auth.jwt.load_settings", return_value=settings):
            with pytest.raises(ValueError, match="jwt_secret_key"):
                create_access_token(uuid4(), uuid4(), "admin")

    def test_expiry_is_in_future(self, mock_settings: MagicMock) -> None:
        """Access token should have expiry in the future."""
        token = create_access_token(uuid4(), uuid4(), "admin")
        payload = jose_jwt.decode(token, "test-secret-key-for-unit-tests", algorithms=["HS256"])

        exp_timestamp = payload["exp"]
        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        now = datetime.now(timezone.utc)

        assert exp_dt > now
        # Should be approximately 30 minutes in the future
        assert (exp_dt - now).total_seconds() < 31 * 60  # less than 31 minutes
        assert (exp_dt - now).total_seconds() > 29 * 60  # more than 29 minutes


class TestCreateRefreshToken:
    """Tests for refresh token creation."""

    def test_returns_jwt_string(self, mock_settings: MagicMock) -> None:
        """Refresh token should return a valid JWT string."""
        token = create_refresh_token(uuid4())
        parts = token.split(".")
        assert len(parts) == 3  # header.payload.signature

    def test_contains_refresh_claims(self, mock_settings: MagicMock) -> None:
        """Refresh token should contain correct claims."""
        uid = uuid4()
        token = create_refresh_token(uid)

        payload = jose_jwt.decode(token, "test-secret-key-for-unit-tests", algorithms=["HS256"])

        assert payload["sub"] == str(uid)
        assert payload["type"] == "refresh"
        assert "team_id" not in payload
        assert "role" not in payload
        assert "exp" in payload

    def test_no_secret_raises_error(self) -> None:
        """Missing jwt_secret_key should raise ValueError for refresh token."""
        settings = MagicMock()
        settings.jwt_secret_key = None

        with patch("src.auth.jwt.load_settings", return_value=settings):
            with pytest.raises(ValueError, match="jwt_secret_key"):
                create_refresh_token(uuid4())

    def test_expiry_is_in_future(self, mock_settings: MagicMock) -> None:
        """Refresh token should have expiry ~7 days in the future."""
        token = create_refresh_token(uuid4())
        payload = jose_jwt.decode(token, "test-secret-key-for-unit-tests", algorithms=["HS256"])

        exp_timestamp = payload["exp"]
        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        now = datetime.now(timezone.utc)

        assert exp_dt > now
        # Should be approximately 7 days in the future
        assert (exp_dt - now).total_seconds() < 7.1 * 24 * 60 * 60  # less than 7.1 days
        assert (exp_dt - now).total_seconds() > 6.9 * 24 * 60 * 60  # more than 6.9 days


class TestDecodeToken:
    """Tests for token decoding and validation."""

    def test_decode_access_token(self, mock_settings: MagicMock) -> None:
        """Decoding a valid access token should return TokenPayload."""
        uid = uuid4()
        tid = uuid4()
        token = create_access_token(uid, tid, "member")

        result = decode_token(token)

        assert isinstance(result, TokenPayload)
        assert result.sub == uid
        assert result.team_id == tid
        assert result.role == "member"
        assert result.token_type == "access"

    def test_decode_refresh_token(self, mock_settings: MagicMock) -> None:
        """Decoding a valid refresh token should return TokenPayload."""
        uid = uuid4()
        token = create_refresh_token(uid)

        result = decode_token(token)

        assert isinstance(result, TokenPayload)
        assert result.sub == uid
        assert result.team_id is None
        assert result.role is None
        assert result.token_type == "refresh"

    def test_expired_token_raises_error(self, mock_settings: MagicMock) -> None:
        """Decoding an expired token should raise ValueError."""
        uid = uuid4()
        tid = uuid4()

        # Create an expired token manually
        expired_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        payload = {
            "sub": str(uid),
            "team_id": str(tid),
            "role": "admin",
            "type": "access",
            "exp": expired_time,
        }
        token = jose_jwt.encode(payload, "test-secret-key-for-unit-tests", algorithm="HS256")

        with patch("src.auth.jwt.load_settings", return_value=mock_settings):
            with pytest.raises(ValueError, match="expired"):
                decode_token(token)

    def test_wrong_secret_raises_error(self, mock_settings: MagicMock) -> None:
        """Token signed with wrong secret should raise ValueError."""
        uid = uuid4()
        tid = uuid4()

        # Create token with wrong secret
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        payload = {
            "sub": str(uid),
            "team_id": str(tid),
            "role": "admin",
            "type": "access",
            "exp": future_time,
        }
        token = jose_jwt.encode(payload, "wrong-secret", algorithm="HS256")

        with patch("src.auth.jwt.load_settings", return_value=mock_settings):
            with pytest.raises(ValueError, match="Invalid token"):
                decode_token(token)

    def test_malformed_token_raises_error(self, mock_settings: MagicMock) -> None:
        """Malformed token should raise ValueError."""
        with patch("src.auth.jwt.load_settings", return_value=mock_settings):
            with pytest.raises(ValueError):
                decode_token("not.a.valid.jwt")

    def test_empty_token_raises_error(self, mock_settings: MagicMock) -> None:
        """Empty token string should raise ValueError."""
        with patch("src.auth.jwt.load_settings", return_value=mock_settings):
            with pytest.raises(ValueError):
                decode_token("")

    def test_missing_sub_claim_raises_error(self, mock_settings: MagicMock) -> None:
        """Token missing 'sub' claim should raise ValueError."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        payload = {
            "type": "access",
            "exp": future_time,
        }
        token = jose_jwt.encode(payload, "test-secret-key-for-unit-tests", algorithm="HS256")

        with patch("src.auth.jwt.load_settings", return_value=mock_settings):
            with pytest.raises(ValueError):
                decode_token(token)

    def test_missing_type_claim_raises_error(self, mock_settings: MagicMock) -> None:
        """Token missing 'type' claim should raise ValueError."""
        uid = uuid4()
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        payload = {
            "sub": str(uid),
            "exp": future_time,
        }
        token = jose_jwt.encode(payload, "test-secret-key-for-unit-tests", algorithm="HS256")

        with patch("src.auth.jwt.load_settings", return_value=mock_settings):
            with pytest.raises(ValueError):
                decode_token(token)

    def test_missing_exp_claim_raises_error(self, mock_settings: MagicMock) -> None:
        """Token missing 'exp' claim should raise ValueError."""
        uid = uuid4()
        payload = {
            "sub": str(uid),
            "type": "access",
        }
        token = jose_jwt.encode(payload, "test-secret-key-for-unit-tests", algorithm="HS256")

        with patch("src.auth.jwt.load_settings", return_value=mock_settings):
            with pytest.raises(ValueError):
                decode_token(token)

    def test_invalid_uuid_in_sub_raises_error(self, mock_settings: MagicMock) -> None:
        """Token with invalid UUID in 'sub' should raise ValueError."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        payload = {
            "sub": "not-a-valid-uuid",
            "type": "access",
            "exp": future_time,
        }
        token = jose_jwt.encode(payload, "test-secret-key-for-unit-tests", algorithm="HS256")

        with patch("src.auth.jwt.load_settings", return_value=mock_settings):
            with pytest.raises(ValueError):
                decode_token(token)

    def test_invalid_uuid_in_team_id_raises_error(self, mock_settings: MagicMock) -> None:
        """Token with invalid UUID in 'team_id' should raise ValueError."""
        uid = uuid4()
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        payload = {
            "sub": str(uid),
            "team_id": "not-a-valid-uuid",
            "type": "access",
            "exp": future_time,
        }
        token = jose_jwt.encode(payload, "test-secret-key-for-unit-tests", algorithm="HS256")

        with patch("src.auth.jwt.load_settings", return_value=mock_settings):
            with pytest.raises(ValueError):
                decode_token(token)

    def test_no_secret_on_decode_raises_error(self) -> None:
        """Missing jwt_secret_key should raise ValueError on decode."""
        settings = MagicMock()
        settings.jwt_secret_key = None

        token = "some.jwt.token"

        with patch("src.auth.jwt.load_settings", return_value=settings):
            with pytest.raises(ValueError, match="jwt_secret_key"):
                decode_token(token)

    def test_decoded_exp_is_datetime_in_utc(self, mock_settings: MagicMock) -> None:
        """Decoded token should have exp as datetime in UTC."""
        token = create_access_token(uuid4(), uuid4(), "admin")
        result = decode_token(token)

        assert isinstance(result.exp, datetime)
        assert result.exp.tzinfo == timezone.utc
        assert result.exp > datetime.now(timezone.utc)


class TestTokenIntegration:
    """Integration tests for token creation and decoding."""

    def test_roundtrip_access_token(self, mock_settings: MagicMock) -> None:
        """Create and decode access token should roundtrip correctly."""
        uid = uuid4()
        tid = uuid4()
        role = "editor"

        token = create_access_token(uid, tid, role)
        result = decode_token(token)

        assert result.sub == uid
        assert result.team_id == tid
        assert result.role == role
        assert result.token_type == "access"

    def test_roundtrip_refresh_token(self, mock_settings: MagicMock) -> None:
        """Create and decode refresh token should roundtrip correctly."""
        uid = uuid4()

        token = create_refresh_token(uid)
        result = decode_token(token)

        assert result.sub == uid
        assert result.team_id is None
        assert result.role is None
        assert result.token_type == "refresh"

    def test_different_tokens_for_same_user(self, mock_settings: MagicMock) -> None:
        """Creating tokens for same user decodes to same subject/team/role."""
        uid = uuid4()
        tid = uuid4()

        token1 = create_access_token(uid, tid, "admin")
        token2 = create_access_token(uid, tid, "admin")

        # Both should decode to same user/team/role
        result1 = decode_token(token1)
        result2 = decode_token(token2)

        assert result1.sub == result2.sub == uid
        assert result1.team_id == result2.team_id == tid
        assert result1.role == result2.role == "admin"

    def test_access_and_refresh_tokens_different_expirations(
        self, mock_settings: MagicMock
    ) -> None:
        """Access token should expire sooner than refresh token."""
        uid = uuid4()
        tid = uuid4()

        access_token = create_access_token(uid, tid, "admin")
        refresh_token = create_refresh_token(uid)

        access_result = decode_token(access_token)
        refresh_result = decode_token(refresh_token)

        # Refresh token should expire much later
        assert refresh_result.exp > access_result.exp
        time_diff = (refresh_result.exp - access_result.exp).total_seconds()
        # Difference should be ~6.5 days (7 days - 30 minutes)
        assert time_diff > 6 * 24 * 60 * 60  # at least 6 days
