"""HTTP request tools for the agent."""

import asyncio
import ipaddress
import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from pydantic_ai import RunContext

logger = logging.getLogger(__name__)

# Hosts blocked to prevent SSRF attacks
BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "169.254.169.254",
    "metadata.google.internal",
}


def _validate_url(url: str) -> Optional[str]:
    """Validate URL is safe for external requests.

    Checks URL scheme (http/https only) and blocks access to private/internal
    hosts to prevent SSRF attacks.

    Args:
        url: The URL to validate.

    Returns:
        Error message string if validation fails, None if URL is safe.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Error: Invalid URL scheme '{parsed.scheme}'. Only http/https allowed."
    hostname = parsed.hostname or ""
    if not hostname:
        return "Error: URL has no hostname."
    if hostname in BLOCKED_HOSTS:
        return f"Error: Access to host '{hostname}' is blocked."
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return f"Error: Access to private/internal IP '{hostname}' is blocked."
    except ValueError:
        pass  # hostname is a domain name, not an IP - that's fine
    return None


# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds

# Shared client for connection pooling
_http_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


async def close_http_client() -> None:
    """Close the shared HTTP client to release resources.

    Should be called during application shutdown to prevent resource leaks.
    Safe to call multiple times or when no client has been created.
    """
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("http_client_closed: shared client shut down")


async def http_get(
    ctx: RunContext[Any],
    url: str,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    """
    Make an HTTP GET request to a URL.

    Use this tool when you need to fetch data from an API or website.
    Returns the response as text (JSON responses are returned as formatted JSON).
    Automatically retries up to 3 times on rate limit (429) errors with backoff.

    Args:
        ctx: Agent runtime context
        url: The URL to fetch
        headers: Optional headers to include in the request

    Returns:
        Response body as text, or error message if request fails
    """
    validation_error = _validate_url(url)
    if validation_error is not None:
        logger.warning(f"http_get_blocked: url={url}, reason={validation_error}")
        return validation_error

    client = await get_http_client()
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"http_get: url={url}, attempt={attempt + 1}/{MAX_RETRIES}")

            response = await client.get(url, headers=headers or {})

            # Handle rate limiting with retry
            if response.status_code == 429:
                delay = RETRY_BASE_DELAY * (2**attempt)  # Exponential backoff
                logger.warning(
                    f"http_get_rate_limited: url={url}, attempt={attempt + 1}, retrying in {delay}s"
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
                    continue
                else:
                    return f"Error: Rate limited (HTTP 429) after {MAX_RETRIES} retries. Try again later."

            # Check for other HTTP errors (no retry)
            if response.status_code >= 400:
                logger.warning(f"http_get_error: url={url}, status={response.status_code}")
                return f"Error: HTTP {response.status_code} - {response.reason_phrase}"

            # Try to parse as JSON for nicer formatting
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    data = response.json()
                    formatted = json.dumps(data, indent=2)
                    logger.info(
                        f"http_get_success: url={url}, status={response.status_code}, "
                        f"type=json, length={len(formatted)}"
                    )
                    return formatted
                except json.JSONDecodeError:
                    pass

            # Return as text
            text = response.text
            logger.info(
                f"http_get_success: url={url}, status={response.status_code}, "
                f"type=text, length={len(text)}"
            )

            # Truncate very long responses
            if len(text) > 50000:
                text = text[:50000] + "\n\n... (response truncated)"

            return text

        except httpx.TimeoutException:
            logger.error(f"http_get_timeout: url={url}")
            last_error = f"Error: Request timed out for {url}"
        except httpx.RequestError as e:
            logger.error(f"http_get_request_error: url={url}, error={str(e)}")
            last_error = f"Error: Request failed - {str(e)}"
        except Exception as e:
            logger.exception(f"http_get_error: url={url}, error={str(e)}")
            last_error = f"Error: {str(e)}"

    return last_error or "Error: Request failed after retries"


async def http_post(
    ctx: RunContext[Any],
    url: str,
    body: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    """
    Make an HTTP POST request to a URL.

    Use this tool when you need to send data to an API.
    The body should be a JSON string if sending JSON data.

    Args:
        ctx: Agent runtime context
        url: The URL to post to
        body: Request body (as JSON string for JSON APIs)
        headers: Optional headers to include in the request

    Returns:
        Response body as text, or error message if request fails
    """
    validation_error = _validate_url(url)
    if validation_error is not None:
        logger.warning(f"http_post_blocked: url={url}, reason={validation_error}")
        return validation_error

    try:
        client = await get_http_client()

        logger.info(f"http_post: url={url}, body_length={len(body) if body else 0}")

        # Prepare headers
        request_headers = headers or {}

        # If body looks like JSON, set content-type
        if body and body.strip().startswith(("{", "[")):
            if "content-type" not in {k.lower() for k in request_headers}:
                request_headers["Content-Type"] = "application/json"

        response = await client.post(url, content=body, headers=request_headers)

        # Check for HTTP errors
        if response.status_code >= 400:
            logger.warning(f"http_post_error: url={url}, status={response.status_code}")
            return f"Error: HTTP {response.status_code} - {response.reason_phrase}\n{response.text}"

        # Try to parse as JSON for nicer formatting
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = response.json()
                formatted = json.dumps(data, indent=2)
                logger.info(
                    f"http_post_success: url={url}, status={response.status_code}, "
                    f"type=json, length={len(formatted)}"
                )
                return formatted
            except json.JSONDecodeError:
                pass

        # Return as text
        text = response.text
        logger.info(
            f"http_post_success: url={url}, status={response.status_code}, "
            f"type=text, length={len(text)}"
        )

        # Truncate very long responses
        if len(text) > 50000:
            text = text[:50000] + "\n\n... (response truncated)"

        return text

    except httpx.TimeoutException:
        logger.error(f"http_post_timeout: url={url}")
        return f"Error: Request timed out for {url}"
    except httpx.RequestError as e:
        logger.error(f"http_post_request_error: url={url}, error={str(e)}")
        return f"Error: Request failed - {str(e)}"
    except Exception as e:
        logger.exception(f"http_post_error: url={url}, error={str(e)}")
        return f"Error: {str(e)}"
