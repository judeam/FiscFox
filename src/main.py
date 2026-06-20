"""FiscFox - Freelance Tax Management System."""
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Configure logging (use LOG_LEVEL env var, default INFO)
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

from fastapi.staticfiles import StaticFiles

from src.db.repository import db_manager
from src.web.exception_handlers import register_exception_handlers
from src.web.middleware import setup_rate_limiting
from src.web.routes import (
    assets_router,
    bewirtung_router,
    clients_router,
    dashboard_router,
    expenses_router,
    gifts_router,
    health_insurance_router,
    homeoffice_router,
    invoices_router,
    pages_router,
    settings_router,
    travel_router,
    upload_router,
)
from src.web.routes.llm import router as llm_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize database and LLM service on startup."""
    await db_manager.initialize()

    # Warm the settings cache from the DB so the persisted language (and other
    # settings) are applied on every worker, including after --reload. The sync
    # load_settings() used by most routes only reads this cache, not the DB.
    try:
        from src.web.routes.settings import load_settings_async

        await load_settings_async()
    except Exception as e:
        logging.warning(f"Settings preload failed: {e}")

    # Initialize LLM service if enabled
    llm_service = None
    try:
        from src.llm.config import get_llm_settings
        from src.llm.service import get_llm_service

        settings = get_llm_settings()
        if settings.enabled:
            logging.info("Initializing LLM service...")
            llm_service = get_llm_service()
            # Model will be loaded lazily on first request
            logging.info("LLM service initialized (model will load on first use)")
    except ImportError:
        logging.info("LLM dependencies not installed, skipping LLM initialization")
    except Exception as e:
        logging.warning(f"LLM initialization failed: {e}")

    yield

    # Cleanup LLM service on shutdown
    if llm_service is not None:
        try:
            await llm_service.shutdown()
            logging.info("LLM service shut down")
        except Exception as e:
            logging.warning(f"LLM shutdown error: {e}")


app = FastAPI(
    title="FiscFox",
    description="Freiberufler Steuerverwaltung - German Freelance Tax Management",
    version="0.1.0",
    lifespan=lifespan,
)

# Register exception handlers for domain exceptions
register_exception_handlers(app)

# Set up rate limiting
setup_rate_limiting(app)

# Static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

# Include routers
app.include_router(dashboard_router)
app.include_router(assets_router, prefix="/assets", tags=["assets"])
app.include_router(bewirtung_router, prefix="/bewirtung", tags=["bewirtung"])
app.include_router(clients_router, prefix="/clients", tags=["clients"])
app.include_router(expenses_router, prefix="/expenses", tags=["expenses"])
app.include_router(gifts_router, prefix="/gifts", tags=["gifts"])
app.include_router(
    health_insurance_router,
    prefix="/krankenversicherung",
    tags=["health_insurance"],
)
app.include_router(homeoffice_router, prefix="/homeoffice", tags=["homeoffice"])
app.include_router(invoices_router, prefix="/invoices", tags=["invoices"])
app.include_router(travel_router, prefix="/travel", tags=["travel"])
app.include_router(upload_router, prefix="/upload", tags=["upload"])
app.include_router(pages_router, tags=["pages"])
app.include_router(settings_router, tags=["settings"])
app.include_router(llm_router)


# =============================================================================
# Health Check Endpoints
# =============================================================================


@app.get("/health", tags=["monitoring"])
async def health_check() -> JSONResponse:
    """Health check for container orchestration.

    Verifies database connectivity and returns service health status.
    Used by Docker HEALTHCHECK, Kubernetes liveness probes, etc.
    """
    try:
        async with db_manager.get_connection() as db:
            await db.execute("SELECT 1")
        return JSONResponse(
            {"status": "healthy", "database": "connected"},
            status_code=200,
        )
    except Exception as e:
        return JSONResponse(
            {"status": "unhealthy", "database": "disconnected", "error": str(e)},
            status_code=503,
        )


@app.get("/ready", tags=["monitoring"])
async def readiness_check() -> JSONResponse:
    """Readiness check for load balancers.

    Returns 200 when the service is ready to accept traffic.
    Used by Kubernetes readiness probes, load balancer health checks.
    """
    return JSONResponse({"status": "ready"}, status_code=200)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
