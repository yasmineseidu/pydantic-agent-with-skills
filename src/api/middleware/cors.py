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
    origins = settings.cors_origins

    logger.info(f"cors_configured: origins={origins}, allow_credentials=True")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
