"""Gift expense (Geschenke) service.

Handles gift tracking with per-recipient limit enforcement.
"""

from decimal import Decimal

from src.core.cache import invalidate_financial_caches
from src.core.models import (
    GIFT_LIMIT_PER_RECIPIENT,
    GiftExpense,
    GiftExpenseInput,
    GiftRecipientSummary,
)
from src.core.tax.geschenke import GeschenkeCalculator, geschenke_calculator
from src.db.repository import GiftExpenseRepository


class GiftService:
    """Service for gift expense operations.

    Orchestrates gift creation with automatic deductibility calculation
    and per-recipient limit tracking.
    """

    def __init__(
        self,
        gift_repo: GiftExpenseRepository | None = None,
        calculator: GeschenkeCalculator | None = None,
    ):
        """Initialize gift service.

        Args:
            gift_repo: Gift expense repository (default: new instance)
            calculator: Geschenke calculator (default: module instance)
        """
        self.gift_repo = gift_repo or GiftExpenseRepository()
        self.calculator = calculator or geschenke_calculator

    async def create_gift_expense(
        self,
        gift_input: GiftExpenseInput,
    ) -> tuple[GiftExpense, bool]:
        """Create a new gift expense with deductibility calculated.

        Checks recipient's cumulative total and applies cliff effect if
        limit is exceeded. Also retroactively updates any previous gifts
        if the new gift pushes total over the limit.

        Args:
            gift_input: GiftExpenseInput data

        Returns:
            Tuple of (created GiftExpense, warning_triggered)
            warning_triggered is True if approaching or exceeded limit
        """
        year = gift_input.date.year

        # Get cumulative before this gift
        cumulative_before = await self.gift_repo.get_recipient_total(
            gift_input.recipient_name,
            year,
        )

        # Create gift expense with calculated deductibility
        gift = self.calculator.create_gift_expense(gift_input, cumulative_before)
        result = await self.gift_repo.create(gift)

        # Check if this gift pushed total over limit
        if result.cumulative_year_total > GIFT_LIMIT_PER_RECIPIENT:
            # Retroactively update all gifts to this recipient as non-deductible
            all_gifts = await self.gift_repo.get_gifts_to_recipient(
                gift_input.recipient_name,
                year,
            )
            updated_gifts = self.calculator.update_deductibility_retroactive(all_gifts)
            for updated in updated_gifts:
                await self.gift_repo.update_deductibility(
                    updated.id,
                    updated.is_deductible,
                    updated.cumulative_year_total,
                )

        # Determine if warning should be shown
        warning = (
            result.cumulative_year_total >= GIFT_LIMIT_PER_RECIPIENT * Decimal("0.8")
        )

        await invalidate_financial_caches()
        return result, warning

    async def get_gift_expense(self, gift_id: int) -> GiftExpense | None:
        """Get gift expense by ID.

        Args:
            gift_id: Gift expense ID

        Returns:
            GiftExpense or None
        """
        return await self.gift_repo.get_by_id(gift_id)

    async def get_gift_expenses(
        self,
        year: int | None = None,
        recipient_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GiftExpense]:
        """Get gift expenses with filters.

        Args:
            year: Filter by year
            recipient_name: Filter by recipient
            limit: Max results
            offset: Result offset

        Returns:
            List of GiftExpense objects
        """
        return await self.gift_repo.get_all(
            year=year,
            recipient_name=recipient_name,
            limit=limit,
            offset=offset,
        )

    async def get_recipient_summaries(
        self,
        year: int,
    ) -> list[GiftRecipientSummary]:
        """Get gift summaries grouped by recipient.

        Args:
            year: Tax year

        Returns:
            List of GiftRecipientSummary objects
        """
        return await self.gift_repo.get_recipient_summaries(year)

    async def get_at_risk_recipients(
        self,
        year: int,
    ) -> list[GiftRecipientSummary]:
        """Get recipients at risk of exceeding gift limit.

        Returns recipients at 80%+ of the 50 EUR limit.

        Args:
            year: Tax year

        Returns:
            List of at-risk recipient summaries
        """
        summaries = await self.gift_repo.get_recipient_summaries(year)
        return self.calculator.get_at_risk_recipients(summaries)

    async def get_recipient_status(
        self,
        recipient_name: str,
        year: int,
    ) -> dict:
        """Get gift limit status for a specific recipient.

        Args:
            recipient_name: Recipient name
            year: Tax year

        Returns:
            Dict with total, remaining, is_over, is_near_limit
        """
        total = await self.gift_repo.get_recipient_total(recipient_name, year)
        status = self.calculator.get_recipient_status(recipient_name, year, total)
        return {
            "recipient_name": status.recipient_name,
            "year": status.year,
            "total_gifts_net": status.total_gifts_net,
            "limit": status.limit,
            "remaining": status.remaining,
            "is_over_limit": status.is_over_limit,
            "is_near_limit": status.is_near_limit,
        }

    async def get_unique_recipients(self) -> list[str]:
        """Get list of unique recipient names for autocomplete.

        Returns:
            List of unique recipient names
        """
        return await self.gift_repo.get_unique_recipients()

    async def delete_gift_expense(self, gift_id: int) -> bool:
        """Soft delete a gift expense.

        Note: This may change deductibility of other gifts to same recipient.
        Consider recalculating after deletion.

        Args:
            gift_id: ID to delete

        Returns:
            True if deleted
        """
        # Get gift before deletion to know recipient
        gift = await self.gift_repo.get_by_id(gift_id)
        if not gift:
            return False

        result = await self.gift_repo.delete(gift_id)
        if result:
            # Recalculate deductibility for remaining gifts
            year = gift.date.year
            remaining_gifts = await self.gift_repo.get_gifts_to_recipient(
                gift.recipient_name,
                year,
            )
            if remaining_gifts:
                updated = self.calculator.update_deductibility_retroactive(remaining_gifts)
                for g in updated:
                    await self.gift_repo.update_deductibility(
                        g.id,
                        g.is_deductible,
                        g.cumulative_year_total,
                    )

            await invalidate_financial_caches()
        return result


# FastAPI dependency
async def get_gift_service() -> GiftService:
    """FastAPI dependency for GiftService."""
    return GiftService()
