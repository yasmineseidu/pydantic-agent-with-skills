"""Unit tests for Slack webhook signature validation."""

import hashlib
import hmac
import time

from integrations.slack.webhook import validate_slack_signature


class TestSlackWebhookValidation:
    """Tests for Slack signing secret validation."""

    def test_valid_signature(self) -> None:
        """Test validation succeeds with correct signature."""
        signing_secret = "my_signing_secret"
        timestamp = str(int(time.time()))
        body = b'{"type":"url_verification","challenge":"abc123"}'
        base_string = f"v0:{timestamp}:".encode() + body
        computed_hmac = hmac.new(signing_secret.encode(), base_string, hashlib.sha256).hexdigest()
        signature = f"v0={computed_hmac}"
        assert validate_slack_signature(signing_secret, timestamp, body, signature) is True

    def test_invalid_signature(self) -> None:
        """Test validation fails with incorrect signature."""
        signing_secret = "my_signing_secret"
        timestamp = str(int(time.time()))
        body = b'{"type":"event_callback"}'
        assert (
            validate_slack_signature(signing_secret, timestamp, body, "v0=wrong_signature") is False
        )

    def test_expired_timestamp(self) -> None:
        """Test validation fails when timestamp > 5 minutes old."""
        signing_secret = "my_signing_secret"
        old_timestamp = str(int(time.time()) - (60 * 10))
        body = b'{"type":"event_callback"}'
        base_string = f"v0:{old_timestamp}:".encode() + body
        computed_hmac = hmac.new(signing_secret.encode(), base_string, hashlib.sha256).hexdigest()
        signature = f"v0={computed_hmac}"
        assert validate_slack_signature(signing_secret, old_timestamp, body, signature) is False

    def test_tampered_body(self) -> None:
        """Test validation fails when body is tampered."""
        signing_secret = "my_signing_secret"
        timestamp = str(int(time.time()))
        original_body = b'{"type":"event_callback","data":"original"}'
        base_string = f"v0:{timestamp}:".encode() + original_body
        computed_hmac = hmac.new(signing_secret.encode(), base_string, hashlib.sha256).hexdigest()
        signature = f"v0={computed_hmac}"
        tampered_body = b'{"type":"event_callback","data":"hacked"}'
        assert (
            validate_slack_signature(signing_secret, timestamp, tampered_body, signature) is False
        )

    def test_wrong_signing_secret(self) -> None:
        """Test validation fails with wrong signing secret."""
        correct_secret = "my_signing_secret"
        wrong_secret = "wrong_secret"
        timestamp = str(int(time.time()))
        body = b'{"type":"event_callback"}'
        base_string = f"v0:{timestamp}:".encode() + body
        computed_hmac = hmac.new(correct_secret.encode(), base_string, hashlib.sha256).hexdigest()
        signature = f"v0={computed_hmac}"
        assert validate_slack_signature(wrong_secret, timestamp, body, signature) is False

    def test_string_body_converted(self) -> None:
        """Test validation handles string body (converts to bytes)."""
        signing_secret = "my_signing_secret"
        timestamp = str(int(time.time()))
        body_str = '{"type":"url_verification"}'
        body_bytes = body_str.encode("utf-8")
        base_string = f"v0:{timestamp}:".encode() + body_bytes
        computed_hmac = hmac.new(signing_secret.encode(), base_string, hashlib.sha256).hexdigest()
        signature = f"v0={computed_hmac}"
        assert validate_slack_signature(signing_secret, timestamp, body_str, signature) is True
