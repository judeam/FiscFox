"""Asset service for fixed asset (Anlagevermögen) management.

Handles asset creation with automatic depreciation method suggestion
and schedule generation.
"""

from datetime import date
from decimal import Decimal

from src.core.cache import invalidate_financial_caches
from src.core.models import (
    Asset,
    AssetCategory,
    AssetInput,
    DepreciationRecord,
)
from src.core.tax.afa import AfaCalculator, afa_calculator
from src.db.repository import AssetRepository


class AssetService:
    """Service for fixed asset operations.

    Orchestrates asset creation, depreciation calculation, and schedule generation.
    """

    def __init__(
        self,
        asset_repo: AssetRepository | None = None,
        calculator: AfaCalculator | None = None,
    ):
        """Initialize asset service.

        Args:
            asset_repo: Asset repository (default: new instance)
            calculator: AfA calculator (default: module instance)
        """
        self.asset_repo = asset_repo or AssetRepository()
        self.calculator = calculator or afa_calculator

    async def create_asset(self, asset: AssetInput) -> Asset:
        """Create a new asset with depreciation schedule.

        If no depreciation method is provided, the optimal method is
        automatically suggested based on value and category.

        Args:
            asset: AssetInput data

        Returns:
            Created Asset with ID
        """
        # Auto-suggest method if not provided
        if asset.depreciation_method is None:
            suggestion = self.calculator.suggest_method(
                asset.acquisition_cost,
                asset.category,
                asset.purchase_date,
            )
            asset = AssetInput(
                name=asset.name,
                purchase_date=asset.purchase_date,
                acquisition_cost=asset.acquisition_cost,
                vat_amount=asset.vat_amount,
                vat_rate=asset.vat_rate,
                category=asset.category,
                useful_life_years=suggestion.useful_life_years,
                depreciation_method=suggestion.method,
                private_use_percent=asset.private_use_percent,
                description=asset.description,
            )

        result = await self.asset_repo.create(asset)

        # Generate depreciation schedule
        schedule = self.calculator.generate_schedule(asset)
        for record in schedule:
            record.asset_id = result.id
            await self.asset_repo.create_depreciation_record(record)

        await invalidate_financial_caches()
        return result

    async def get_asset(self, asset_id: int) -> Asset | None:
        """Get asset by ID.

        Args:
            asset_id: Asset ID

        Returns:
            Asset or None
        """
        return await self.asset_repo.get_by_id(asset_id)

    async def get_assets(
        self,
        year: int | None = None,
        category: AssetCategory | None = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Asset]:
        """Get assets with filters.

        Args:
            year: Filter by purchase year
            category: Filter by category
            active_only: Exclude disposed/fully depreciated assets
            limit: Max results
            offset: Result offset

        Returns:
            List of Asset objects
        """
        return await self.asset_repo.get_all(
            year=year,
            category=category,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )

    async def get_depreciation_schedule(
        self,
        asset_id: int,
    ) -> list[DepreciationRecord]:
        """Get depreciation schedule for an asset.

        Args:
            asset_id: Asset ID

        Returns:
            List of DepreciationRecord objects
        """
        return await self.asset_repo.get_depreciation_records(asset_id)

    async def get_annual_depreciation(self, year: int) -> Decimal:
        """Get total depreciation deduction for a year.

        Args:
            year: Tax year

        Returns:
            Total depreciation amount
        """
        return await self.asset_repo.get_annual_depreciation(year)

    async def get_depreciation_suggestion(
        self,
        cost: Decimal,
        category: AssetCategory,
        purchase_date: date | None = None,
    ) -> dict:
        """Get depreciation method suggestion for an asset.

        Args:
            cost: Net acquisition cost
            category: Asset category
            purchase_date: Purchase date for degressive eligibility

        Returns:
            Dict with method, useful_life, first_year_amount, explanation
        """
        suggestion = self.calculator.suggest_method(cost, category, purchase_date)
        return {
            "method": suggestion.method.value,
            "useful_life_years": suggestion.useful_life_years,
            "first_year_depreciation": suggestion.first_year_depreciation,
            "explanation": suggestion.explanation,
            "alternative_method": (
                suggestion.alternative_method.value
                if suggestion.alternative_method
                else None
            ),
            "alternative_explanation": suggestion.alternative_explanation,
        }

    async def dispose_asset(
        self,
        asset_id: int,
        disposed_date: date,
        disposal_amount: Decimal,
    ) -> Asset | None:
        """Record asset disposal (sale or scrapping).

        Calculates disposal gain/loss for tax purposes.

        Args:
            asset_id: Asset ID
            disposed_date: Date of disposal
            disposal_amount: Sale proceeds (0 for scrapping)

        Returns:
            Updated Asset or None
        """
        asset = await self.asset_repo.get_by_id(asset_id)
        if not asset:
            return None

        # Calculate gain/loss
        gain_loss = self.calculator.calculate_disposal_gain(
            asset.current_book_value,
            disposal_amount,
        )

        result = await self.asset_repo.dispose(
            asset_id,
            disposed_date,
            disposal_amount,
        )

        await invalidate_financial_caches()
        return result

    async def delete_asset(self, asset_id: int) -> bool:
        """Soft delete an asset.

        Args:
            asset_id: ID to delete

        Returns:
            True if deleted
        """
        result = await self.asset_repo.delete(asset_id)
        if result:
            await invalidate_financial_caches()
        return result

    async def get_category_breakdown(
        self,
        year: int | None = None,
    ) -> dict[AssetCategory, dict]:
        """Get asset statistics by category.

        Args:
            year: Filter by purchase year

        Returns:
            Dict mapping category to {count, total_cost, total_book_value}
        """
        assets = await self.asset_repo.get_all(
            year=year,
            active_only=False,
            limit=1000,
        )

        breakdown: dict[AssetCategory, dict] = {}

        for asset in assets:
            if asset.category not in breakdown:
                breakdown[asset.category] = {
                    "count": 0,
                    "total_cost": Decimal("0"),
                    "total_book_value": Decimal("0"),
                }
            breakdown[asset.category]["count"] += 1
            breakdown[asset.category]["total_cost"] += asset.acquisition_cost
            breakdown[asset.category]["total_book_value"] += asset.current_book_value

        return breakdown

    async def get_assets_expiring_this_year(
        self,
        year: int | None = None,
    ) -> list[Asset]:
        """Get assets that will be fully depreciated this year.

        Useful for year-end planning.

        Args:
            year: Tax year (default: current year)

        Returns:
            List of assets completing depreciation this year
        """
        year = year or date.today().year
        assets = await self.asset_repo.get_all(active_only=True, limit=1000)

        expiring = []
        for asset in assets:
            schedule = await self.asset_repo.get_depreciation_records(asset.id)
            for record in schedule:
                if record.year == year and record.book_value_end <= Decimal("0.01"):
                    expiring.append(asset)
                    break

        return expiring


# FastAPI dependency
async def get_asset_service() -> AssetService:
    """FastAPI dependency for AssetService."""
    return AssetService()
