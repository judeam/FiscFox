"""Expense service for business expense management.

Handles expense booking with proper VAT (Vorsteuer) calculations.
"""

from datetime import date
from decimal import Decimal

from src.core.cache import invalidate_financial_caches
from src.core.models import (
    Expense,
    ExpenseCategory,
    ExpenseInput,
)
from src.db.repository import ExpenseRepository


class ExpenseService:
    """Service for expense operations.

    Orchestrates expense creation, retrieval, and calculations.
    """

    def __init__(
        self,
        expense_repo: ExpenseRepository | None = None,
    ):
        """Initialize expense service.

        Args:
            expense_repo: Expense repository (default: new instance)
        """
        self.expense_repo = expense_repo or ExpenseRepository()

    async def book_expense(self, expense: ExpenseInput) -> Expense:
        """Book a new expense.

        Creates expense record with calculated VAT (Vorsteuer).

        Args:
            expense: ExpenseInput data

        Returns:
            Created Expense with ID and computed fields
        """
        result = await self.expense_repo.create(expense)
        await invalidate_financial_caches()
        return result

    async def get_expense(self, expense_id: int) -> Expense | None:
        """Get expense by ID.

        Args:
            expense_id: Expense ID

        Returns:
            Expense or None
        """
        return await self.expense_repo.get_by_id(expense_id)

    async def get_expenses(
        self,
        year: int | None = None,
        category: ExpenseCategory | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Expense]:
        """Get expenses with filters.

        Args:
            year: Filter by year
            category: Filter by category
            limit: Max results
            offset: Result offset

        Returns:
            List of Expense objects
        """
        from src.web.routes.settings import get_activity_start_date

        return await self.expense_repo.get_all(
            year=year,
            category=category,
            limit=limit,
            offset=offset,
            activity_start_date=get_activity_start_date(),
        )

    async def get_expenses_by_period(
        self,
        start_date: date,
        end_date: date,
    ) -> list[Expense]:
        """Get expenses within date range.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of Expense objects
        """
        return await self.expense_repo.get_by_period(start_date, end_date)

    async def update_expense(
        self,
        expense_id: int,
        expense: ExpenseInput,
    ) -> Expense | None:
        """Update an expense.

        Note: For booked/finalized expenses, consider using storno.

        Args:
            expense_id: ID to update
            expense: New data

        Returns:
            Updated Expense or None
        """
        result = await self.expense_repo.update(expense_id, expense)
        if result:
            await invalidate_financial_caches()
        return result

    async def delete_expense(self, expense_id: int) -> bool:
        """Soft delete an expense.

        Args:
            expense_id: ID to delete

        Returns:
            True if deleted
        """
        result = await self.expense_repo.delete(expense_id)
        if result:
            await invalidate_financial_caches()
        return result

    async def get_category_breakdown(
        self,
        year: int | None = None,
    ) -> dict[ExpenseCategory, Decimal]:
        """Get expense totals by category.

        Args:
            year: Filter by year (default: current year)

        Returns:
            Dictionary mapping category to total net amount
        """
        from src.web.routes.settings import get_activity_start_date

        year = year or date.today().year
        expenses = await self.expense_repo.get_all(
            year=year, limit=1000, activity_start_date=get_activity_start_date()
        )

        breakdown: dict[ExpenseCategory, Decimal] = {
            cat: Decimal("0") for cat in ExpenseCategory
        }

        for exp in expenses:
            breakdown[exp.category] += exp.amount_net

        return breakdown

    async def get_monthly_totals(
        self,
        year: int | None = None,
    ) -> dict[str, tuple[Decimal, Decimal]]:
        """Get monthly expense totals.

        Args:
            year: Filter by year

        Returns:
            Dictionary mapping month (YYYY-MM) to (net, vorsteuer) tuple
        """
        from src.web.routes.settings import get_activity_start_date

        year = year or date.today().year
        expenses = await self.expense_repo.get_all(
            year=year, limit=1000, activity_start_date=get_activity_start_date()
        )

        monthly: dict[str, tuple[Decimal, Decimal]] = {}

        for exp in expenses:
            month_key = exp.date.strftime("%Y-%m")
            current = monthly.get(month_key, (Decimal("0"), Decimal("0")))
            monthly[month_key] = (
                current[0] + exp.amount_net,
                current[1] + exp.vat_amount,
            )

        return monthly

    async def get_recent_expenses(self, limit: int = 5) -> list[Expense]:
        """Get most recent expenses.

        Args:
            limit: Max results

        Returns:
            List of recent expenses
        """
        from src.web.routes.settings import get_activity_start_date

        return await self.expense_repo.get_all(
            limit=limit, activity_start_date=get_activity_start_date()
        )


# FastAPI dependency
async def get_expense_service() -> ExpenseService:
    """FastAPI dependency for ExpenseService."""
    return ExpenseService()
