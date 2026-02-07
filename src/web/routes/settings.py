"""User settings routes for business information and preferences.

Handles the /einstellungen page and settings updates via HTMX.
Settings are stored in SQLite database with JSON serialization.
"""

import json
import logging
from datetime import date as date_type
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import SenderInfo, UserSettings, VatRate
from src.db.repository import SettingsRepository

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")

# Legacy JSON settings file (for migration)
LEGACY_SETTINGS_FILE = Path("data/user_settings.json")

# Database keys
SETTINGS_KEY = "user_settings"
MIGRATED_KEY = "settings_migrated"

# Settings cache (shared between sync and async operations)
_settings_cache: UserSettings | None = None
_migration_done: bool = False


# =============================================================================
# Sync API (for backward compatibility)
# =============================================================================


def load_settings() -> UserSettings:
    """Load user settings from cache or fallback to JSON file.

    For full database support, use load_settings_async() in async contexts.
    This sync version uses cached settings or falls back to legacy JSON.
    """
    global _settings_cache

    if _settings_cache is not None:
        return _settings_cache

    # Fallback: try legacy JSON file
    if LEGACY_SETTINGS_FILE.exists():
        try:
            data = json.loads(LEGACY_SETTINGS_FILE.read_text())
            _settings_cache = _deserialize_settings(data)
            return _settings_cache
        except (json.JSONDecodeError, ValueError):
            pass

    _settings_cache = UserSettings()
    return _settings_cache


def save_settings(settings: UserSettings) -> None:
    """Update the settings cache.

    For full database persistence, use save_settings_async() in async contexts.
    This sync version only updates the cache (database save happens async).
    """
    global _settings_cache
    _settings_cache = settings


def invalidate_settings_cache() -> None:
    """Invalidate the settings cache (for testing or manual refresh)."""
    global _settings_cache
    _settings_cache = None


# =============================================================================
# Async API (database-backed)
# =============================================================================


async def get_settings_repo() -> SettingsRepository:
    """FastAPI dependency for SettingsRepository."""
    return SettingsRepository()


async def load_settings_async(repo: SettingsRepository | None = None) -> UserSettings:
    """Load user settings from database.

    Migrates from legacy JSON file on first access.
    """
    global _settings_cache, _migration_done

    if _settings_cache is not None:
        return _settings_cache

    repo = repo or SettingsRepository()

    # Check if migration is needed
    if not _migration_done:
        await _migrate_from_json(repo)
        _migration_done = True

    # Load from database
    settings_json = await repo.get(SETTINGS_KEY)
    if settings_json:
        try:
            data = json.loads(settings_json)
            _settings_cache = _deserialize_settings(data)
            return _settings_cache
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse settings from database: {e}")

    # Return default settings
    _settings_cache = UserSettings()
    return _settings_cache


async def save_settings_async(
    settings: UserSettings, repo: SettingsRepository | None = None
) -> None:
    """Save user settings to database and update cache."""
    global _settings_cache

    repo = repo or SettingsRepository()

    # Serialize and store
    settings_json = _serialize_settings(settings)
    await repo.set(SETTINGS_KEY, settings_json)

    # Update cache
    _settings_cache = settings
    logger.info("Settings saved to database")


async def _migrate_from_json(repo: SettingsRepository) -> None:
    """Migrate settings from legacy JSON file to database.

    One-time migration on first access.
    """
    # Check if already migrated
    migrated = await repo.get(MIGRATED_KEY)
    if migrated == "true":
        return

    if LEGACY_SETTINGS_FILE.exists():
        try:
            data = json.loads(LEGACY_SETTINGS_FILE.read_text())
            settings = _deserialize_settings(data)
            settings_json = _serialize_settings(settings)
            await repo.set(SETTINGS_KEY, settings_json)
            logger.info("Migrated settings from JSON file to database")

            # Rename old file as backup
            backup_path = LEGACY_SETTINGS_FILE.with_suffix(".json.bak")
            LEGACY_SETTINGS_FILE.rename(backup_path)
            logger.info(f"Backed up old settings file to {backup_path}")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to migrate settings from JSON: {e}")

    # Mark migration as complete
    await repo.set(MIGRATED_KEY, "true")


def _serialize_settings(settings: UserSettings) -> str:
    """Serialize UserSettings to JSON string."""
    data = settings.model_dump()

    # Convert special types to serializable format
    if data.get("default_vat_rate"):
        data["default_vat_rate"] = str(data["default_vat_rate"].value)
    if data.get("quarterly_est_amount"):
        data["quarterly_est_amount"] = str(data["quarterly_est_amount"])
    if data.get("activity_start_date"):
        data["activity_start_date"] = data["activity_start_date"].isoformat()

    return json.dumps(data, indent=2)


def _deserialize_settings(data: dict) -> UserSettings:
    """Deserialize JSON data to UserSettings."""
    # Convert string representations back to proper types
    if data.get("default_vat_rate"):
        data["default_vat_rate"] = VatRate(data["default_vat_rate"])
    if data.get("quarterly_est_amount"):
        data["quarterly_est_amount"] = Decimal(data["quarterly_est_amount"])
    if data.get("activity_start_date"):
        if isinstance(data["activity_start_date"], str):
            data["activity_start_date"] = date_type.fromisoformat(
                data["activity_start_date"]
            )

    return UserSettings(**data)


def get_tax_year() -> int:
    """Get the currently selected tax year from settings.

    Returns settings.tax_year if set, otherwise current year.
    """
    from datetime import date
    settings = load_settings()
    return settings.tax_year or date.today().year


# =============================================================================
# Settings Page
# =============================================================================


@router.get("/einstellungen", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Render the settings page."""
    from datetime import date
    settings = await load_settings_async()
    lang = settings.language
    _ = get_translator(lang)

    # Generate list of years (current year and 5 years back)
    current_year = date.today().year
    available_years = list(range(current_year, current_year - 6, -1))

    return templates.TemplateResponse(
        "pages/settings.html",
        {
            "request": request,
            "settings": settings,
            "_": _,
            "lang": lang,
            "current_year": current_year,
            "available_years": available_years,
            "vat_rates": [
                ("0.00", _("vat.zero")),
                ("0.19", _("vat.standard")),
                ("0.07", _("vat.reduced")),
            ],
            "date_formats": [
                ("iso", _("date_format.iso")),
                ("german", _("date_format.german")),
                ("us", _("date_format.us")),
            ],
            "languages": [
                ("de", _("language.de")),
                ("en", _("language.en")),
            ],
        },
    )


# =============================================================================
# Settings Update (HTMX)
# =============================================================================


@router.post("/settings/update", response_class=HTMLResponse)
async def update_settings(
    request: Request,
    # Business Identity
    business_name: Annotated[str, Form()] = "",
    # Address
    street: Annotated[str, Form()] = "",
    address_details: Annotated[str, Form()] = "",
    zip_code: Annotated[str, Form()] = "",
    city: Annotated[str, Form()] = "",
    country: Annotated[str, Form()] = "Germany",
    # Contact
    phone: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    website: Annotated[str, Form()] = "",
    # Tax Information
    vat_id: Annotated[str, Form()] = "",
    tax_number: Annotated[str, Form()] = "",
    # Bank Details
    bank_name: Annotated[str, Form()] = "",
    iban: Annotated[str, Form()] = "",
    bic_swift: Annotated[str, Form()] = "",
    # Invoice Preferences
    default_payment_terms: Annotated[int, Form()] = 14,
    default_vat_rate: Annotated[str, Form()] = "0.00",
    invoice_prefix: Annotated[str, Form()] = "",
    # Display Preferences
    preferred_currency: Annotated[str, Form()] = "EUR",
    date_format: Annotated[str, Form()] = "iso",
    language: Annotated[str, Form()] = "de",
    tax_year: Annotated[int | None, Form()] = None,
    # Tax Obligation Settings
    is_freiberufler: Annotated[str, Form()] = "on",  # Checkbox value
    has_eu_clients: Annotated[str, Form()] = "",  # Checkbox value
    ust_frequency: Annotated[str, Form()] = "monthly",
    quarterly_est_amount: Annotated[str, Form()] = "0",
    activity_start_date: Annotated[str, Form()] = "",  # Date string (YYYY-MM-DD) or empty
) -> HTMLResponse:
    """Update user settings via HTMX form submission."""
    from datetime import date as date_type
    from decimal import Decimal

    # Parse activity_start_date
    parsed_activity_start_date = None
    if activity_start_date:
        try:
            parsed_activity_start_date = date_type.fromisoformat(activity_start_date)
        except ValueError:
            pass  # Invalid date format, keep as None

    settings = UserSettings(
        business_name=business_name,
        street=street,
        address_details=address_details,
        zip_code=zip_code,
        city=city,
        country=country,
        phone=phone,
        email=email,
        website=website,
        vat_id=vat_id,
        tax_number=tax_number,
        bank_name=bank_name,
        iban=iban,
        bic_swift=bic_swift,
        default_payment_terms=default_payment_terms,
        default_vat_rate=VatRate(default_vat_rate),
        invoice_prefix=invoice_prefix,
        preferred_currency=preferred_currency,
        date_format=date_format,
        language=language,
        tax_year=tax_year,
        # Checkboxes: "on" if checked, empty string if not
        is_freiberufler=is_freiberufler == "on",
        has_eu_clients=has_eu_clients == "on",
        ust_frequency=ust_frequency,
        quarterly_est_amount=Decimal(quarterly_est_amount) if quarterly_est_amount else Decimal("0"),
        activity_start_date=parsed_activity_start_date,
    )

    await save_settings_async(settings)

    # Get translated success message
    _ = get_translator(language)
    success_msg = _("settings.saved")

    # Return success toast notification with redirect to reload page with new language
    return HTMLResponse(f"""
        <div id="settings-toast"
             class="fixed bottom-6 right-6 bg-sage text-white px-6 py-4 rounded-lg shadow-lg flex items-center gap-3 z-50 animate-slide-up"
             hx-swap-oob="true">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
            </svg>
            <span class="font-medium">{success_msg}</span>
        </div>
        <script>
            setTimeout(() => {{
                const toast = document.getElementById('settings-toast');
                if (toast) {{
                    toast.style.opacity = '0';
                    toast.style.transform = 'translateY(20px)';
                    setTimeout(() => {{
                        toast.remove();
                        // Reload page to apply language changes
                        window.location.reload();
                    }}, 300);
                }}
            }}, 2000);
        </script>
    """)


# =============================================================================
# Helper functions
# =============================================================================


def get_current_sender() -> SenderInfo:
    """Get SenderInfo from current settings."""
    settings = load_settings()
    return settings.to_sender_info()


def get_current_language() -> str:
    """Get current language setting."""
    settings = load_settings()
    return settings.language


def get_i18n_context() -> dict:
    """Get i18n context for templates.

    Returns dict with:
        - _: translator function
        - lang: current language code
    """
    lang = get_current_language()
    return {
        "_": get_translator(lang),
        "lang": lang,
    }


def get_activity_start_date() -> date_type | None:
    """Get the activity start date from settings.

    Returns date if set, None otherwise.
    Used to filter out data before the freelance activity began.
    """
    settings = load_settings()
    return settings.activity_start_date
