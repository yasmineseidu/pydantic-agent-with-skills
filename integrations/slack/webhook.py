"""Slack webhook signature validation."""

import hashlib
import hmac
import time
from typing import Union


def validate_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: Union[bytes, str],
    signature: str,
) -> bool:
    """Validate Slack webhook signature (v0 scheme).

    Slack signs requests with HMAC-SHA256 using the app's signing secret.
    The base string is: v0:{timestamp}:{body}
    The signature header is: v0={computed_hmac}

    Security features:
    - Constant-time comparison (prevents timing attacks)
    - Timestamp replay protection (reject > 5 minutes old)

    Args:
        signing_secret: Slack app signing secret.
        timestamp: X-Slack-Request-Timestamp header value.
        body: Request body (bytes or string).
        signature: X-Slack-Signature header value (e.g., "v0=abc123...").

    Returns:
        True if signature is valid and timestamp is fresh, False otherwise.
    """
    # Replay protection: reject requests older than 5 minutes
    current_time = int(time.time())
    try:
        request_time = int(timestamp)
    except (ValueError, TypeError):
        return False
    if abs(current_time - request_time) > 60 * 5:
        return False

    # Convert body to bytes if string
    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        body_bytes = body

    # Construct base string: v0:{timestamp}:{body}
    base_string = f"v0:{timestamp}:".encode("utf-8") + body_bytes

    # Compute HMAC-SHA256
    computed_hmac = hmac.new(
        key=signing_secret.encode("utf-8"),
        msg=base_string,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Expected signature format: v0={hmac}
    expected_signature = f"v0={computed_hmac}"

    # Constant-time comparison (prevents timing attacks)
    return hmac.compare_digest(expected_signature, signature)
