"""FastAPI route modules."""
from src.web.routes.assets import router as assets_router
from src.web.routes.bewirtung import router as bewirtung_router
from src.web.routes.clients import router as clients_router
from src.web.routes.dashboard import router as dashboard_router
from src.web.routes.expenses import router as expenses_router
from src.web.routes.gifts import router as gifts_router
from src.web.routes.health_insurance import router as health_insurance_router
from src.web.routes.homeoffice import router as homeoffice_router
from src.web.routes.invoices import router as invoices_router
from src.web.routes.pages import router as pages_router
from src.web.routes.settings import router as settings_router
from src.web.routes.travel import router as travel_router
from src.web.routes.upload import router as upload_router

__all__ = [
    "assets_router",
    "bewirtung_router",
    "clients_router",
    "dashboard_router",
    "expenses_router",
    "gifts_router",
    "health_insurance_router",
    "homeoffice_router",
    "invoices_router",
    "pages_router",
    "settings_router",
    "travel_router",
    "upload_router",
]
