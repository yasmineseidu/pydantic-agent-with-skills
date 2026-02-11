"""CORS configuration for FastAPI."""

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

if TYPE_CHECKING:
    from src.settings import Settings

logger = logging.getLogger(__name__)


def configure_cors(app: FastAPI, settings: "Settings") -> None:
    """
    Add CORS middleware to FastAPI app.

    Reads allowed origins from settings.cors_origins.
    Allows credentials, all methods, and all headers.

    Args:
        app: FastAPI application instance
        settings: Settings with cors_origins list

    Returns:
        None (modifies app in-place)
    """
    origins = list(settings.cors_origins)

    # Prevent dangerous combination: allow_credentials=True with wildcard origin.
    # Browsers reject Access-Control-Allow-Origin: * when credentials are included,
    # and permitting it can enable CSRF-like attacks.
    if "*" in origins:
        origins.remove("*")
        logger.warning(
            "cors_wildcard_removed: allow_credentials=True is incompatible with "
            "wildcard origin '*'. Removed '*' from allowed origins."
        )

    logger.info("cors_configured: origins=%s, allow_credentials=True", origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
