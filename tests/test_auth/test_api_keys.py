"""Unit tests for API key generation, hashing, and validation."""

from src.auth.api_keys import (
    generate_api_key,
    hash_api_key,
    validate_api_key_format,
    API_KEY_TOTAL_LENGTH,
    API_KEY_PREFIX_LENGTH,
)


class TestGenerateApiKey:
    """Tests for API key generation."""

    def test_returns_three_element_tuple(self) -> None:
        """Generated API key should be a 3-element tuple."""
        result = generate_api_key()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_full_key_starts_with_ska_prefix(self) -> None:
        """Full API key should start with 'ska_' prefix."""
        full_key, _, _ = generate_api_key()
        assert full_key.startswith("ska_")

    def test_full_key_has_correct_total_length(self) -> None:
        """Full API key should be exactly 68 characters."""
        full_key, _, _ = generate_api_key()
        assert len(full_key) == API_KEY_TOTAL_LENGTH
        assert len(full_key) == 68

    def test_key_prefix_is_first_12_characters(self) -> None:
        """Key prefix should be first 12 characters of full key."""
        full_key, key_prefix, _ = generate_api_key()
        assert key_prefix == full_key[:API_KEY_PREFIX_LENGTH]
        assert len(key_prefix) == API_KEY_PREFIX_LENGTH
        assert len(key_prefix) == 12

    def test_key_hash_is_valid_hex_string(self) -> None:
        """Key hash should be 64-character hex string."""
        _, _, key_hash = generate_api_key()
        assert len(key_hash) == 64
        assert all(c in "0123456789abcdef" for c in key_hash)

    def test_generated_hash_matches_hash_function(self) -> None:
        """Hash from generation should match hash_api_key() result."""
        full_key, _, generated_hash = generate_api_key()
        computed_hash = hash_api_key(full_key)
        assert generated_hash == computed_hash

    def test_generated_keys_are_unique(self) -> None:
        """Multiple calls should generate different keys."""
        full_key_1, _, _ = generate_api_key()
        full_key_2, _, _ = generate_api_key()
        assert full_key_1 != full_key_2


class TestHashApiKey:
    """Tests for API key hashing."""

    def test_hash_is_deterministic(self) -> None:
        """Hashing the same key twice should produce identical hashes."""
        test_key = "ska_" + "a" * 64
        hash_1 = hash_api_key(test_key)
        hash_2 = hash_api_key(test_key)
        assert hash_1 == hash_2

    def test_different_keys_produce_different_hashes(self) -> None:
        """Different API keys should produce different hashes."""
        key_1 = "ska_" + "a" * 64
        key_2 = "ska_" + "b" * 64
        hash_1 = hash_api_key(key_1)
        hash_2 = hash_api_key(key_2)
        assert hash_1 != hash_2


class TestValidateApiKeyFormat:
    """Tests for API key format validation."""

    def test_valid_generated_key_passes_validation(self) -> None:
        """A generated API key should pass format validation."""
        full_key, _, _ = generate_api_key()
        assert validate_api_key_format(full_key) is True

    def test_invalid_prefix_fails_validation(self) -> None:
        """Key with wrong prefix should fail validation."""
        invalid_key = "xxx_" + "a" * 64
        assert validate_api_key_format(invalid_key) is False

    def test_key_too_short_fails_validation(self) -> None:
        """Key shorter than 68 characters should fail validation."""
        short_key = "ska_abc"
        assert validate_api_key_format(short_key) is False

    def test_key_too_long_fails_validation(self) -> None:
        """Key longer than 68 characters should fail validation."""
        long_key = "ska_" + "a" * 65
        assert validate_api_key_format(long_key) is False

    def test_non_hex_characters_fail_validation(self) -> None:
        """Key with non-hex characters should fail validation."""
        invalid_hex_key = "ska_" + "g" * 64
        assert validate_api_key_format(invalid_hex_key) is False

    def test_empty_string_fails_validation(self) -> None:
        """Empty string should fail validation."""
        assert validate_api_key_format("") is False

    def test_key_with_mixed_case_hex_passes_validation(self) -> None:
        """Key with mixed case hex characters should pass validation."""
        mixed_case_key = "ska_" + "aAbBcC" + "f" * 58
        assert validate_api_key_format(mixed_case_key) is True

    def test_key_with_spaces_fails_validation(self) -> None:
        """Key with spaces should fail validation."""
        key_with_spaces = "ska_" + "a" * 32 + " " + "a" * 31
        assert validate_api_key_format(key_with_spaces) is False

    def test_key_with_special_characters_fails_validation(self) -> None:
        """Key with special characters should fail validation."""
        key_with_special = "ska_" + "a" * 60 + "!@#$"
        assert validate_api_key_format(key_with_special) is False
