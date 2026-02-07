"""Business meal (Bewirtung) service.

Handles business meal expense creation with automatic deductibility calculation.
"""

from decimal import Decimal

from src.core.cache import invalidate_financial_caches
from src.core.models import (
    BEWIRTUNG_DEDUCTION_RATE,
    INTERNAL_EVENT_CAP_PER_PERSON,
    BusinessMeal,
    BusinessMealInput,
)
from src.db.repository import BusinessMealRepository


class BewirtungService:
    """Service for business meal expense operations.

    Orchestrates business meal creation with automatic deduction calculations.
    """

    def __init__(
        self,
        meal_repo: BusinessMealRepository | None = None,
    ):
        """Initialize business meal service.

        Args:
            meal_repo: Business meal repository (default: new instance)
        """
        self.meal_repo = meal_repo or BusinessMealRepository()

    async def create_business_meal(
        self,
        meal_input: BusinessMealInput,
    ) -> BusinessMeal:
        """Create a new business meal expense with deductibility calculated.

        Automatically calculates:
        - 70% deduction for external business meals
        - 100% for internal events (capped at 110 EUR/person)

        Args:
            meal_input: BusinessMealInput data

        Returns:
            Created BusinessMeal with deductions calculated
        """
        # Calculate deductible amount based on type
        if meal_input.is_internal:
            # Internal events: 100% up to 110 EUR per person
            cap = INTERNAL_EVENT_CAP_PER_PERSON * meal_input.attendee_count
            deductible = min(meal_input.total_amount, cap)
        else:
            # External: 70% deduction
            deductible = meal_input.total_amount * BEWIRTUNG_DEDUCTION_RATE

        # Quantize to 2 decimals
        deductible = deductible.quantize(Decimal("0.01"))

        result = await self.meal_repo.create(meal_input, deductible)

        await invalidate_financial_caches()
        return result

    async def get_business_meal(self, meal_id: int) -> BusinessMeal | None:
        """Get business meal by ID.

        Args:
            meal_id: Business meal ID

        Returns:
            BusinessMeal or None
        """
        return await self.meal_repo.get_by_id(meal_id)

    async def get_business_meals(
        self,
        year: int | None = None,
        is_internal: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BusinessMeal]:
        """Get business meals with filters.

        Args:
            year: Filter by year
            is_internal: Filter by internal/external
            limit: Max results
            offset: Result offset

        Returns:
            List of BusinessMeal objects
        """
        return await self.meal_repo.get_all(
            year=year,
            is_internal=is_internal,
            limit=limit,
            offset=offset,
        )

    async def get_annual_totals(self, year: int) -> dict:
        """Get annual business meal totals.

        Args:
            year: Tax year

        Returns:
            Dict with total_amount, deductible_amount, internal_count, external_count
        """
        return await self.meal_repo.get_annual_totals(year)

    async def delete_business_meal(self, meal_id: int) -> bool:
        """Soft delete a business meal expense.

        Args:
            meal_id: ID to delete

        Returns:
            True if deleted
        """
        result = await self.meal_repo.delete(meal_id)
        if result:
            await invalidate_financial_caches()
        return result

    def calculate_deduction_preview(
        self,
        total_amount: Decimal,
        attendee_count: int,
        is_internal: bool,
    ) -> dict:
        """Preview deduction calculation without saving.

        Useful for live form feedback.

        Args:
            total_amount: Total meal cost
            attendee_count: Number of attendees
            is_internal: Whether internal event

        Returns:
            Dict with total, deductible, non_deductible, rate_applied, warning
        """
        if is_internal:
            cap = INTERNAL_EVENT_CAP_PER_PERSON * attendee_count
            deductible = min(total_amount, cap)
            rate_applied = Decimal("1.0")
            warning = total_amount > cap
            per_person = total_amount / attendee_count if attendee_count > 0 else total_amount
        else:
            deductible = total_amount * BEWIRTUNG_DEDUCTION_RATE
            rate_applied = BEWIRTUNG_DEDUCTION_RATE
            warning = False
            per_person = total_amount / attendee_count if attendee_count > 0 else total_amount

        deductible = deductible.quantize(Decimal("0.01"))
        non_deductible = (total_amount - deductible).quantize(Decimal("0.01"))

        return {
            "total_amount": total_amount,
            "deductible_amount": deductible,
            "non_deductible_amount": non_deductible,
            "rate_applied": rate_applied,
            "is_internal": is_internal,
            "attendee_count": attendee_count,
            "per_person_amount": per_person.quantize(Decimal("0.01")),
            "cap_per_person": INTERNAL_EVENT_CAP_PER_PERSON if is_internal else None,
            "cap_exceeded": warning,
        }

    async def get_monthly_summary(
        self,
        year: int,
    ) -> dict[str, dict]:
        """Get monthly business meal summary.

        Args:
            year: Tax year

        Returns:
            Dict mapping month (YYYY-MM) to summary dict
        """
        meals = await self.meal_repo.get_all(year=year, limit=1000)

        monthly: dict[str, dict] = {}

        for meal in meals:
            month_key = meal.date.strftime("%Y-%m")
            if month_key not in monthly:
                monthly[month_key] = {
                    "total_amount": Decimal("0"),
                    "deductible_amount": Decimal("0"),
                    "internal_count": 0,
                    "external_count": 0,
                    "meal_count": 0,
                }
            monthly[month_key]["total_amount"] += meal.total_amount
            monthly[month_key]["deductible_amount"] += meal.deductible_amount
            if meal.is_internal:
                monthly[month_key]["internal_count"] += 1
            else:
                monthly[month_key]["external_count"] += 1
            monthly[month_key]["meal_count"] += 1

        return monthly


# FastAPI dependency
async def get_bewirtung_service() -> BewirtungService:
    """FastAPI dependency for BewirtungService."""
    return BewirtungService()
