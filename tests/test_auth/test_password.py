"""Unit tests for password hashing and validation module."""

import pytest

from src.auth.password import (
    hash_password,
    verify_password,
    validate_password_strength,
)


class TestValidatePasswordStrength:
    """Tests for password strength validation."""

    def test_valid_password_returns_empty_list(self) -> None:
        """A password meeting all requirements should return empty list."""
        result = validate_password_strength("TestPass1")
        assert result == []

    def test_password_too_short_below_minimum(self) -> None:
        """Password shorter than 8 characters should fail."""
        errors = validate_password_strength("Tp1")
        assert len(errors) > 0
        assert any("8 characters" in e for e in errors)

    def test_password_exactly_8_chars_valid(self) -> None:
        """A password with exactly 8 characters meeting other requirements is valid."""
        result = validate_password_strength("TestPas1")
        assert result == []

    def test_password_missing_uppercase(self) -> None:
        """Password without uppercase letter should fail."""
        errors = validate_password_strength("testpass1")
        assert len(errors) > 0
        assert any("uppercase" in e for e in errors)

    def test_password_missing_lowercase(self) -> None:
        """Password without lowercase letter should fail."""
        errors = validate_password_strength("TESTPASS1")
        assert len(errors) > 0
        assert any("lowercase" in e for e in errors)

    def test_password_missing_digit(self) -> None:
        """Password without digit should fail."""
        errors = validate_password_strength("TestPasss")
        assert len(errors) > 0
        assert any("digit" in e for e in errors)

    def test_password_multiple_failures(self) -> None:
        """Password failing multiple requirements should return multiple errors."""
        errors = validate_password_strength("ab")
        assert len(errors) >= 2  # short + missing uppercase + missing digit

    def test_password_only_digits(self) -> None:
        """Password with only digits should fail multiple checks."""
        errors = validate_password_strength("12345678")
        assert len(errors) >= 2  # no uppercase, no lowercase

    def test_password_only_letters_missing_digit(self) -> None:
        """Password with only letters should fail digit check."""
        errors = validate_password_strength("TestPass")
        assert len(errors) > 0
        assert any("digit" in e for e in errors)


class TestHashPassword:
    """Tests for password hashing with bcrypt."""

    def test_hash_password_returns_bcrypt_hash(self) -> None:
        """Hash should return a valid bcrypt hash string starting with $2b$."""
        hashed = hash_password("TestPass1")
        assert isinstance(hashed, str)
        assert hashed.startswith("$2b$12$")

    def test_hash_password_with_weak_password_raises_error(self) -> None:
        """Hashing a weak password should raise ValueError."""
        with pytest.raises(ValueError, match="8 characters"):
            hash_password("short")

    def test_hash_password_includes_all_validation_errors(self) -> None:
        """Error message should include all validation failures."""
        with pytest.raises(ValueError) as exc_info:
            hash_password("ab")
        error_msg = str(exc_info.value)
        assert "8 characters" in error_msg
        assert "uppercase" in error_msg

    def test_hash_password_different_salts_for_same_password(self) -> None:
        """Same password hashed twice should produce different hashes (different salts)."""
        hash1 = hash_password("TestPass1")
        hash2 = hash_password("TestPass1")
        assert hash1 != hash2  # Different salts produce different hashes

    def test_hash_password_different_passwords_different_hashes(self) -> None:
        """Different passwords should produce different hashes."""
        hash1 = hash_password("TestPass1")
        hash2 = hash_password("TestPass2")
        assert hash1 != hash2

    def test_hash_password_with_special_characters(self) -> None:
        """Password with special characters should hash successfully if strength is valid."""
        hashed = hash_password("TestPass1!")
        assert hashed.startswith("$2b$12$")

    def test_hash_password_with_long_password(self) -> None:
        """Long password (32+ chars) should hash successfully."""
        long_password = "TestPass1" * 5  # 45 characters
        hashed = hash_password(long_password)
        assert hashed.startswith("$2b$12$")


class TestVerifyPassword:
    """Tests for password verification."""

    def test_verify_password_correct_password_returns_true(self) -> None:
        """Correct password should verify against its hash."""
        hashed = hash_password("TestPass1")
        result = verify_password("TestPass1", hashed)
        assert result is True

    def test_verify_password_incorrect_password_returns_false(self) -> None:
        """Incorrect password should not verify."""
        hashed = hash_password("TestPass1")
        result = verify_password("WrongPass1", hashed)
        assert result is False

    def test_verify_password_empty_plain_password(self) -> None:
        """Empty plain password should not verify against any hash."""
        hashed = hash_password("TestPass1")
        result = verify_password("", hashed)
        assert result is False

    def test_verify_password_with_malformed_hash(self) -> None:
        """Malformed hash should not crash, return False."""
        result = verify_password("TestPass1", "not-a-valid-hash")
        assert result is False

    def test_verify_password_with_empty_hash(self) -> None:
        """Empty hash should not crash, return False."""
        result = verify_password("TestPass1", "")
        assert result is False

    def test_verify_password_with_none_like_hash(self) -> None:
        """Hash-like None value should not crash, return False."""
        result = verify_password("TestPass1", "null")
        assert result is False

    def test_verify_password_case_sensitive(self) -> None:
        """Password verification should be case-sensitive."""
        hashed = hash_password("TestPass1")
        result = verify_password("testpass1", hashed)
        assert result is False

    def test_verify_password_with_extra_whitespace(self) -> None:
        """Password with extra whitespace should not verify (whitespace matters)."""
        hashed = hash_password("TestPass1")
        result = verify_password("TestPass1 ", hashed)
        assert result is False
