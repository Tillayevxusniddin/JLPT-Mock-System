# apps/core/exceptions.py
"""
Global DRF exception handler.

- Known DRF exceptions (400, 401, 403, 404, 405, 429): returned with structured
  error body.
- Unhandled exceptions (500): logged server-side with a unique error_id; only a
  generic message + error_id is sent to the client. **No stack traces ever leak.**
"""
import logging
import traceback
import uuid

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    # Let DRF handle its own exceptions first (400, 401, 403, 404, 405, 429).
    response = exception_handler(exc, context)

    if response is not None:
        # Structured envelope for known DRF errors.
        return Response(
            {
                "error": response.data,
                "message": "An error occurred",
                "status_code": response.status_code,
            },
            status=response.status_code,
        )

    # --- Unhandled exception (500) -----------------------------------------
    # Generate a unique error ID so ops can correlate the client report with
    # the server-side log entry.  Never expose exc message or traceback.
    error_id = uuid.uuid4().hex[:12]

    # Log full details server-side for debugging.
    view = context.get("view")
    view_name = f"{view.__class__.__module__}.{view.__class__.__name__}" if view else "unknown"
    logger.error(
        "Unhandled exception [error_id=%s] in %s: %s",
        error_id,
        view_name,
        exc,
        exc_info=True,
    )

    return Response(
        {
            "detail": "An unexpected server error occurred. Please try again or contact support.",
            "error_id": error_id,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
