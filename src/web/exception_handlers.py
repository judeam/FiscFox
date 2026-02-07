"""FastAPI exception handlers for FiscFox.

Provides structured error handling that returns HTML responses
suitable for HTMX partial updates.
"""

import logging

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.core.exceptions import (
    DuplicateUploadError,
    ExtractionError,
    FileTooLargeError,
    InvalidFileTypeError,
    NotFoundError,
    FiscFoxError,
    RepositoryError,
    UploadError,
    ValidationError,
)

logger = logging.getLogger(__name__)


def _error_html(title: str, message: str, code: str, status_code: int) -> HTMLResponse:
    """Generate HTML error response for HTMX.

    Returns a styled error alert that can be swapped into the DOM.
    """
    html = f"""
    <div class="alert alert-error" role="alert" data-error-code="{code}">
        <div class="alert-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
        </div>
        <div class="alert-content">
            <strong>{title}</strong>
            <p>{message}</p>
        </div>
        <button type="button" class="alert-close" onclick="this.parentElement.remove()">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
        </button>
    </div>
    """
    return HTMLResponse(content=html, status_code=status_code)


async def fiscfox_error_handler(request: Request, exc: FiscFoxError) -> HTMLResponse:
    """Handle all FiscFox domain exceptions.

    Returns HTML error responses suitable for HTMX partial updates.
    """
    logger.warning(f"FiscFox error: {exc.code} - {exc.message}", extra={"details": exc.details})

    # Map exception types to HTTP status codes and user-friendly titles
    if isinstance(exc, NotFoundError):
        return _error_html("Nicht gefunden", exc.message, exc.code, 404)

    if isinstance(exc, ValidationError):
        return _error_html("Validierungsfehler", exc.message, exc.code, 422)

    if isinstance(exc, FileTooLargeError):
        return _error_html("Datei zu groß", exc.message, exc.code, 413)

    if isinstance(exc, InvalidFileTypeError):
        return _error_html("Ungültiger Dateityp", exc.message, exc.code, 415)

    if isinstance(exc, DuplicateUploadError):
        return _error_html("Duplikat erkannt", exc.message, exc.code, 409)

    if isinstance(exc, UploadError):
        return _error_html("Upload-Fehler", exc.message, exc.code, 400)

    if isinstance(exc, ExtractionError):
        return _error_html("Extraktionsfehler", exc.message, exc.code, 422)

    if isinstance(exc, RepositoryError):
        return _error_html("Datenbankfehler", exc.message, exc.code, 500)

    # Default for any other FiscFoxError
    return _error_html("Fehler", exc.message, exc.code, 400)


async def generic_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
    """Handle unexpected exceptions with a generic error response."""
    logger.exception(f"Unexpected error: {exc}")
    return _error_html(
        "Unerwarteter Fehler",
        "Ein unerwarteter Fehler ist aufgetreten. Bitte versuchen Sie es erneut.",
        "INTERNAL_ERROR",
        500,
    )


def register_exception_handlers(app) -> None:
    """Register all exception handlers with the FastAPI app.

    Args:
        app: FastAPI application instance
    """
    # Register handler for all FiscFox exceptions
    app.add_exception_handler(FiscFoxError, fiscfox_error_handler)

    # Optionally register a catch-all for unexpected errors
    # Uncomment if you want to handle all exceptions with HTML responses
    # app.add_exception_handler(Exception, generic_exception_handler)
