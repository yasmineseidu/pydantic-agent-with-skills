"""Error handling middleware for FastAPI."""

import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from src.api.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)


async def error_handling_middleware(request: Request, call_next: Callable) -> Response:
    """
    Catch exceptions and return standardized JSON error responses.

    Handles different exception types:
    - ValueError → 400 Bad Request
    - HTTPException → passthrough with original status
    - IntegrityError (SQLAlchemy) → 409 Conflict
    - Exception → 500 Internal Server Error

    All errors wrapped in ErrorResponse schema with structured logging.

    Args:
        request: Incoming FastAPI request
        call_next: Next middleware/handler in chain

    Returns:
        Response object (either success or error JSON)
    """
    request_id = getattr(request.state, "request_id", None)

    try:
        response: Response = await call_next(request)
        return response

    except ValueError as e:
        logger.warning(
            f"validation_error: path={request.url.path}, error={str(e)}, request_id={request_id}"
        )
        error = ErrorResponse(
            error="validation_error",
            message=str(e),
            request_id=request_id,
        )
        return JSONResponse(status_code=400, content=error.model_dump())

    except HTTPException as e:
        # HTTPException already has status_code and detail, passthrough
        logger.info(
            f"http_exception: path={request.url.path}, status={e.status_code}, "
            f"detail={e.detail}, request_id={request_id}"
        )
        error = ErrorResponse(
            error="http_error",
            message=str(e.detail),
            request_id=request_id,
        )
        return JSONResponse(status_code=e.status_code, content=error.model_dump())

    except IntegrityError as e:
        logger.warning(
            f"integrity_error: path={request.url.path}, error={str(e)}, request_id={request_id}"
        )
        error = ErrorResponse(
            error="conflict",
            message="Resource conflict or constraint violation",
            details={"db_error": str(e.orig) if hasattr(e, "orig") else str(e)},
            request_id=request_id,
        )
        return JSONResponse(status_code=409, content=error.model_dump())

    except Exception as e:
        logger.exception(
            f"internal_error: path={request.url.path}, error={str(e)}, request_id={request_id}"
        )
        error = ErrorResponse(
            error="internal_error",
            message="An unexpected error occurred",
            request_id=request_id,
        )
        return JSONResponse(status_code=500, content=error.model_dump())
