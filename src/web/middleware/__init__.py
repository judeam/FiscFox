"""Web middleware for FastAPI application."""

from src.web.middleware.rate_limit import limiter, setup_rate_limiting

__all__ = ["limiter", "setup_rate_limiting"]
