"""Travel expense (Reisekosten) service.

Handles travel expense creation with automatic per diem and km calculations.
"""

from datetime import date
from decimal import Decimal

from src.core.cache import invalidate_financial_caches
from src.core.models import (
    TravelExpense,
    TravelExpenseInput,
)
from src.core.tax.reisekosten import ReisekostenCalculator, reisekosten_calculator
from src.db.repository import TravelExpenseRepository


class TravelService:
    """Service for travel expense operations.

    Orchestrates travel expense creation with automatic deduction calculations.
    """

    def __init__(
        self,
        travel_repo: TravelExpenseRepository | None = None,
        calculator: ReisekostenCalculator | None = None,
    ):
        """Initialize travel service.

        Args:
            travel_repo: Travel expense repository (default: new instance)
            calculator: Reisekosten calculator (default: module instance)
        """
        self.travel_repo = travel_repo or TravelExpenseRepository()
        self.calculator = calculator or reisekosten_calculator

    async def create_travel_expense(
        self,
        travel: TravelExpenseInput,
    ) -> TravelExpense:
        """Create a new travel expense with calculated deductions.

        Automatically calculates per diem and km allowance based on input.

        Args:
            travel: TravelExpenseInput data

        Returns:
            Created TravelExpense with all deductions calculated
        """
        # Calculate all deductions using the calculator
        calculated = self.calculator.create_travel_expense(travel)

        # Store in database
        result = await self.travel_repo.create(travel, calculated)

        await invalidate_financial_caches()
        return result

    async def get_travel_expense(self, travel_id: int) -> TravelExpense | None:
        """Get travel expense by ID.

        Args:
            travel_id: Travel expense ID

        Returns:
            TravelExpense or None
        """
        return await self.travel_repo.get_by_id(travel_id)

    async def get_travel_expenses(
        self,
        year: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TravelExpense]:
        """Get travel expenses with filters.

        Args:
            year: Filter by year
            limit: Max results
            offset: Result offset

        Returns:
            List of TravelExpense objects
        """
        return await self.travel_repo.get_all(
            year=year,
            limit=limit,
            offset=offset,
        )

    async def get_travel_by_period(
        self,
        start_date: date,
        end_date: date,
    ) -> list[TravelExpense]:
        """Get travel expenses within date range.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of TravelExpense objects
        """
        return await self.travel_repo.get_by_period(start_date, end_date)

    async def get_annual_totals(self, year: int) -> dict:
        """Get annual travel expense totals.

        Args:
            year: Tax year

        Returns:
            Dict with per_diem_total, km_total, total_deduction
        """
        return await self.travel_repo.get_annual_totals(year)

    async def delete_travel_expense(self, travel_id: int) -> bool:
        """Soft delete a travel expense.

        Args:
            travel_id: ID to delete

        Returns:
            True if deleted
        """
        result = await self.travel_repo.delete(travel_id)
        if result:
            await invalidate_financial_caches()
        return result

    def calculate_per_diem_preview(
        self,
        absence_hours: Decimal,
        country_code: str = "DE",
        is_travel_day: bool = False,
        is_overnight: bool = False,
        breakfast_provided: bool = False,
        lunch_provided: bool = False,
        dinner_provided: bool = False,
    ) -> dict:
        """Preview per diem calculation without saving.

        Useful for live form feedback.

        Args:
            absence_hours: Hours absent
            country_code: Country code
            is_travel_day: Is arrival/departure day
            is_overnight: Overnight stay
            breakfast_provided: Breakfast included
            lunch_provided: Lunch included
            dinner_provided: Dinner included

        Returns:
            Dict with base_rate, meal_reduction, final_amount, rate_type
        """
        result = self.calculator.calculate_per_diem(
            absence_hours=absence_hours,
            country_code=country_code,
            is_travel_day=is_travel_day,
            is_overnight=is_overnight,
            breakfast_provided=breakfast_provided,
            lunch_provided=lunch_provided,
            dinner_provided=dinner_provided,
        )
        return {
            "base_rate": result.base_rate,
            "meal_reduction": result.meal_reduction,
            "final_amount": result.final_amount,
            "rate_type": result.rate_type,
            "country": result.country,
        }

    def calculate_km_preview(
        self,
        km_driven: Decimal,
    ) -> dict:
        """Preview km allowance calculation without saving.

        Args:
            km_driven: Total kilometers driven

        Returns:
            Dict with total_km, rate_applied, deduction, breakdown
        """
        result = self.calculator.calculate_km_allowance(km_driven)
        return {
            "total_km": result.total_km,
            "rate_applied": result.rate_applied,
            "deduction": result.deduction,
            "breakdown": result.breakdown,
        }

    async def get_monthly_summary(
        self,
        year: int,
    ) -> dict[str, dict]:
        """Get monthly travel expense summary.

        Args:
            year: Tax year

        Returns:
            Dict mapping month (YYYY-MM) to summary dict
        """
        travels = await self.travel_repo.get_all(year=year, limit=1000)

        monthly: dict[str, dict] = {}

        for travel in travels:
            month_key = travel.date.strftime("%Y-%m")
            if month_key not in monthly:
                monthly[month_key] = {
                    "per_diem": Decimal("0"),
                    "km_deduction": Decimal("0"),
                    "total": Decimal("0"),
                    "trip_count": 0,
                }
            monthly[month_key]["per_diem"] += travel.per_diem_deduction
            monthly[month_key]["km_deduction"] += travel.km_deduction
            monthly[month_key]["total"] += travel.total_deduction
            monthly[month_key]["trip_count"] += 1

        return monthly

    def get_supported_countries(self) -> list[tuple[str, Decimal, Decimal]]:
        """Get list of supported countries with per diem rates.

        Returns:
            List of (country_code, 8+ rate, 24h rate) tuples
        """
        return self.calculator.list_supported_countries()


# FastAPI dependency
async def get_travel_service() -> TravelService:
    """FastAPI dependency for TravelService."""
    return TravelService()
