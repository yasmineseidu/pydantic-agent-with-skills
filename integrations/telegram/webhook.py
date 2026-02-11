"""Telegram webhook signature validation."""

import hashlib
import hmac
from typing import Union


def validate_telegram_signature(
    bot_token: str,
    payload: Union[bytes, str],
    signature: str,
) -> bool:
    """Validate Telegram webhook HMAC signature.

    Telegram uses the SHA-256 hash of the bot token as the HMAC secret key,
    then computes HMAC-SHA256 of the payload and compares to the signature.

    Security: Uses constant-time comparison (hmac.compare_digest) to prevent
    timing attacks.

    Args:
        bot_token: Telegram bot token (e.g., "123456:ABC-DEF...").
        payload: Request body (bytes or string).
        signature: Expected HMAC signature from X-Telegram-Bot-Api-Secret-Token header.

    Returns:
        True if signature is valid, False otherwise.
    """
    # Convert payload to bytes if string
    if isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    else:
        payload_bytes = payload

    # Telegram uses SHA-256 hash of bot token as HMAC secret
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()

    # Compute HMAC-SHA256 of payload
    computed_signature = hmac.new(
        key=secret_key,
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison (prevents timing attacks)
    return hmac.compare_digest(computed_signature, signature)
