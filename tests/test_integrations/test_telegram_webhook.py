"""Unit tests for Telegram webhook signature validation."""

import hashlib
import hmac

from integrations.telegram.webhook import validate_telegram_signature


class TestTelegramWebhookValidation:
    """Tests for Telegram HMAC signature validation."""

    def test_valid_signature(self) -> None:
        """Test validation succeeds with correct signature."""
        bot_token = "123456:ABC-DEF"
        payload = b'{"update_id": 123, "message": {"text": "hello"}}'
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        signature = hmac.new(secret_key, payload, hashlib.sha256).hexdigest()
        assert validate_telegram_signature(bot_token, payload, signature) is True

    def test_invalid_signature(self) -> None:
        """Test validation fails with incorrect signature."""
        bot_token = "123456:ABC-DEF"
        payload = b'{"update_id": 123}'
        assert validate_telegram_signature(bot_token, payload, "wrong_signature") is False

    def test_tampered_payload(self) -> None:
        """Test validation fails when payload is tampered."""
        bot_token = "123456:ABC-DEF"
        original = b'{"update_id": 123, "message": {"text": "hello"}}'
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        signature = hmac.new(secret_key, original, hashlib.sha256).hexdigest()
        tampered = b'{"update_id": 999, "message": {"text": "hacked"}}'
        assert validate_telegram_signature(bot_token, tampered, signature) is False

    def test_wrong_bot_token(self) -> None:
        """Test validation fails with wrong bot token."""
        correct_token = "123456:ABC-DEF"
        wrong_token = "999999:XYZ-GHI"
        payload = b'{"update_id": 123}'
        secret_key = hashlib.sha256(correct_token.encode()).digest()
        signature = hmac.new(secret_key, payload, hashlib.sha256).hexdigest()
        assert validate_telegram_signature(wrong_token, payload, signature) is False

    def test_empty_payload(self) -> None:
        """Test validation handles empty payload."""
        bot_token = "123456:ABC-DEF"
        payload = b""
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        signature = hmac.new(secret_key, payload, hashlib.sha256).hexdigest()
        assert validate_telegram_signature(bot_token, payload, signature) is True

    def test_string_payload_converted(self) -> None:
        """Test validation handles string payload (converts to bytes)."""
        bot_token = "123456:ABC-DEF"
        payload_str = '{"update_id": 123}'
        payload_bytes = payload_str.encode("utf-8")
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        signature = hmac.new(secret_key, payload_bytes, hashlib.sha256).hexdigest()
        assert validate_telegram_signature(bot_token, payload_str, signature) is True
