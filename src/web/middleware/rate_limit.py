"""Rate limiting middleware using slowapi.

Provides configurable rate limits for different endpoint types
to protect against abuse and ensure fair resource usage.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# =============================================================================
# Rate Limit Configuration
# =============================================================================

# HTMX partial updates (high frequency expected)
HTMX_LIMIT = "200/minute"

# JSON API endpoints
API_LIMIT = "60/minute"

# File uploads (expensive operations)
UPLOAD_LIMIT = "10/minute"

# Dashboard/heavy computations
COMPUTATION_LIMIT = "30/minute"

# Settings updates
SETTINGS_LIMIT = "20/minute"


def get_request_identifier(request: Request) -> str:
    """Get rate limit key based on remote address.

    For single-user deployment, this is mainly protection against
    accidental rapid-fire requests or browser bugs.
    """
    return get_remote_address(request)


# Create limiter instance
limiter = Limiter(
    key_func=get_request_identifier,
    default_limits=[API_LIMIT],
    storage_uri="memory://",  # In-memory storage for single instance
)


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> HTMLResponse:
    """Custom rate limit handler returning HTML for HTMX compatibility.

    Returns an HTML error alert that HTMX can display to the user.
    """
    logger.warning(f"Rate limit exceeded: {exc.detail} from {get_remote_address(request)}")

    html = """
    <div class="alert alert-warning" role="alert" data-error-code="RATE_LIMITED">
        <div class="alert-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
        </div>
        <div class="alert-content">
            <strong>Zu viele Anfragen</strong>
            <p>Bitte warten Sie einen Moment und versuchen Sie es erneut.</p>
        </div>
        <button type="button" class="alert-close" onclick="this.parentElement.remove()">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
        </button>
    </div>
    """
    return HTMLResponse(content=html, status_code=429)


def setup_rate_limiting(app: FastAPI) -> None:
    """Configure rate limiting for the FastAPI application.

    Args:
        app: FastAPI application instance
    """
    # Store limiter in app state
    app.state.limiter = limiter

    # Register custom exception handler
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    logger.info("Rate limiting configured with limits: "
                f"HTMX={HTMX_LIMIT}, API={API_LIMIT}, Upload={UPLOAD_LIMIT}")
