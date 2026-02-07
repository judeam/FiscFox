"""Home office (Homeoffice) service.

Handles home office day tracking with daily cap enforcement and method selection.
"""

from datetime import date
from decimal import Decimal

from src.core.cache import invalidate_financial_caches
from src.core.models import (
    HOME_OFFICE_ANNUAL_CAP,
    HOME_OFFICE_DAILY_RATE,
    HOME_OFFICE_MAX_DAYS,
    HomeOfficeDay,
    HomeOfficeDayInput,
    HomeOfficeSettings,
    HomeOfficeSettingsInput,
)
from src.db.repository import HomeOfficeRepository


class HomeOfficeService:
    """Service for home office operations.

    Orchestrates home office day tracking and settings management.
    Supports two methods:
    - Homeoffice-Pauschale: 6 EUR/day, max 210 days = 1,260 EUR
    - Häusliches Arbeitszimmer: Pro-rata room costs or 1,260 EUR flat rate
    """

    def __init__(
        self,
        repo: HomeOfficeRepository | None = None,
    ):
        """Initialize home office service.

        Args:
            repo: Home office repository (default: new instance)
        """
        self.repo = repo or HomeOfficeRepository()

    async def get_settings(self, year: int) -> HomeOfficeSettings | None:
        """Get home office settings for a year.

        Args:
            year: Tax year

        Returns:
            HomeOfficeSettings or None if not configured
        """
        return await self.repo.get_settings(year)

    async def save_settings(
        self,
        settings_input: HomeOfficeSettingsInput,
    ) -> HomeOfficeSettings:
        """Save home office settings for a year.

        Args:
            settings_input: Settings configuration

        Returns:
            Saved HomeOfficeSettings
        """
        result = await self.repo.save_settings(settings_input)
        await invalidate_financial_caches()
        return result

    async def add_home_office_day(
        self,
        day_input: HomeOfficeDayInput,
    ) -> tuple[HomeOfficeDay, bool]:
        """Record a home office day.

        Checks if day limit is exceeded and returns warning.

        Args:
            day_input: HomeOfficeDayInput data

        Returns:
            Tuple of (created HomeOfficeDay, limit_warning)
            limit_warning is True if at or beyond 210 days
        """
        year = day_input.date.year

        # Get current count
        current_count = await self.repo.get_day_count(year)

        # Create the day
        result = await self.repo.add_day(day_input)

        # Check if limit reached
        new_count = current_count + 1
        warning = new_count >= HOME_OFFICE_MAX_DAYS

        await invalidate_financial_caches()
        return result, warning

    async def get_home_office_days(
        self,
        year: int,
        month: int | None = None,
        limit: int = 366,
        offset: int = 0,
    ) -> list[HomeOfficeDay]:
        """Get home office days for a year.

        Args:
            year: Tax year
            month: Optional month filter (1-12)
            limit: Max results
            offset: Result offset

        Returns:
            List of HomeOfficeDay objects
        """
        return await self.repo.get_days(
            year=year,
            month=month,
            limit=limit,
            offset=offset,
        )

    async def delete_home_office_day(self, day_id: int) -> bool:
        """Delete a home office day.

        Args:
            day_id: Day ID to delete

        Returns:
            True if deleted
        """
        result = await self.repo.delete_day(day_id)
        if result:
            await invalidate_financial_caches()
        return result

    async def get_annual_summary(self, year: int) -> dict:
        """Get annual home office summary.

        Calculates deduction based on selected method.

        Args:
            year: Tax year

        Returns:
            Dict with day_count, method, deduction, remaining_days, etc.
        """
        settings = await self.repo.get_settings(year)
        day_count = await self.repo.get_day_count(year)

        # Default to Pauschale method if no settings
        method = settings.method if settings else "pauschale"

        if method == "pauschale":
            # 6 EUR per day, max 210 days
            effective_days = min(day_count, HOME_OFFICE_MAX_DAYS)
            deduction = HOME_OFFICE_DAILY_RATE * effective_days
            deduction = min(deduction, HOME_OFFICE_ANNUAL_CAP)
            remaining_days = max(0, HOME_OFFICE_MAX_DAYS - day_count)
        elif method == "arbeitszimmer_flat":
            # 1,260 EUR flat rate for separate room
            deduction = HOME_OFFICE_ANNUAL_CAP
            remaining_days = None  # Not applicable
        elif method == "arbeitszimmer_actual" and settings:
            # Pro-rata actual costs
            if settings.total_sqm and settings.room_sqm and settings.monthly_costs:
                ratio = settings.room_sqm / settings.total_sqm
                annual_costs = settings.monthly_costs * 12
                deduction = (annual_costs * ratio).quantize(Decimal("0.01"))
            else:
                deduction = Decimal("0")
            remaining_days = None
        else:
            deduction = Decimal("0")
            remaining_days = HOME_OFFICE_MAX_DAYS

        return {
            "year": year,
            "day_count": day_count,
            "method": method,
            "deduction": deduction,
            "remaining_days": remaining_days,
            "daily_rate": HOME_OFFICE_DAILY_RATE,
            "max_days": HOME_OFFICE_MAX_DAYS,
            "annual_cap": HOME_OFFICE_ANNUAL_CAP,
            "settings": settings,
        }

    async def get_monthly_breakdown(self, year: int) -> dict[str, dict]:
        """Get monthly home office day breakdown.

        Args:
            year: Tax year

        Returns:
            Dict mapping month number (1-12) to summary dict
        """
        days = await self.repo.get_days(year=year)

        monthly: dict[str, dict] = {}
        for i in range(1, 13):
            monthly[str(i)] = {"count": 0, "deduction": Decimal("0")}

        running_total = 0
        for day in sorted(days, key=lambda d: d.date):
            month = str(day.date.month)
            monthly[month]["count"] += 1
            running_total += 1

            # Only count up to max days for deduction
            if running_total <= HOME_OFFICE_MAX_DAYS:
                monthly[month]["deduction"] += HOME_OFFICE_DAILY_RATE

        return monthly

    def validate_day(
        self,
        day_date: date,
        existing_travel_dates: list[date] | None = None,
    ) -> tuple[bool, str | None]:
        """Validate if a day can be recorded as home office.

        Cannot claim home office and commute/travel on same day.

        Args:
            day_date: Date to validate
            existing_travel_dates: List of dates with travel expenses

        Returns:
            Tuple of (is_valid, error_message)
        """
        if existing_travel_dates and day_date in existing_travel_dates:
            return False, "Cannot claim home office on a travel expense day"

        # Could add more validation (weekends, holidays, etc.)
        return True, None


# FastAPI dependency
async def get_homeoffice_service() -> HomeOfficeService:
    """FastAPI dependency for HomeOfficeService."""
    return HomeOfficeService()
