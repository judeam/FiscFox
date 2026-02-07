"""Health insurance service for Krankenversicherung management.

Handles health insurance payment tracking and tax deduction calculations
per § 10 EStG (Vorsorgeaufwendungen/Sonderausgaben).
"""

from datetime import date

from src.core.cache import invalidate_financial_caches
from src.core.models import (
    CoverageType,
    HealthInsurance,
    HealthInsuranceDeduction,
    HealthInsuranceInput,
    HealthInsuranceProvider,
    HealthInsuranceSummary,
    InsuranceType,
)
from src.core.tax.health_insurance import HealthInsuranceCalculator
from src.db.repository import (
    HealthInsuranceProviderRepository,
    HealthInsuranceRepository,
)


class HealthInsuranceService:
    """Service for health insurance operations.

    Orchestrates health insurance payment tracking and tax deduction
    calculations following German tax law § 10 EStG.

    Tax deduction rules:
    - Basisabsicherung: Unlimited deduction
    - Pflegepflichtversicherung: Unlimited deduction
    - GKV with Krankengeld: 4% reduction applies
    - Wahlleistungen/Zusatzversicherung: Limited to EUR 2,800/year (freelancers)
    """

    def __init__(
        self,
        health_insurance_repo: HealthInsuranceRepository | None = None,
        provider_repo: HealthInsuranceProviderRepository | None = None,
        calculator: HealthInsuranceCalculator | None = None,
    ):
        """Initialize health insurance service.

        Args:
            health_insurance_repo: Health insurance repository (default: new instance)
            provider_repo: Provider repository (default: new instance)
            calculator: Tax calculator (default: freelancer settings)
        """
        self.health_insurance_repo = health_insurance_repo or HealthInsuranceRepository()
        self.provider_repo = provider_repo or HealthInsuranceProviderRepository()
        self.calculator = calculator or HealthInsuranceCalculator(is_freelancer=True)

    async def create_health_insurance(
        self,
        health_insurance: HealthInsuranceInput,
    ) -> HealthInsurance:
        """Create a new health insurance payment record.

        Args:
            health_insurance: HealthInsuranceInput data

        Returns:
            Created HealthInsurance with ID and computed fields
        """
        result = await self.health_insurance_repo.create(health_insurance)
        await invalidate_financial_caches()
        return result

    async def get_health_insurance(
        self,
        health_insurance_id: int,
    ) -> HealthInsurance | None:
        """Get health insurance payment by ID.

        Args:
            health_insurance_id: Health insurance ID

        Returns:
            HealthInsurance or None
        """
        return await self.health_insurance_repo.get_by_id(health_insurance_id)

    async def get_health_insurances(
        self,
        year: int | None = None,
        insurance_type: InsuranceType | None = None,
        coverage_type: CoverageType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HealthInsurance]:
        """Get health insurance payments with filters.

        Args:
            year: Filter by year
            insurance_type: Filter by GKV/PKV
            coverage_type: Filter by coverage type
            limit: Max results
            offset: Result offset

        Returns:
            List of HealthInsurance objects
        """
        return await self.health_insurance_repo.get_all(
            year=year,
            insurance_type=insurance_type,
            coverage_type=coverage_type,
            limit=limit,
            offset=offset,
        )

    async def get_health_insurances_by_year(
        self,
        year: int,
    ) -> list[HealthInsurance]:
        """Get all health insurance payments for a specific year.

        Args:
            year: Tax year

        Returns:
            List of HealthInsurance objects
        """
        return await self.health_insurance_repo.get_by_year(year)

    async def delete_health_insurance(
        self,
        health_insurance_id: int,
    ) -> bool:
        """Soft delete a health insurance payment.

        Args:
            health_insurance_id: ID to delete

        Returns:
            True if deleted
        """
        result = await self.health_insurance_repo.delete(health_insurance_id)
        if result:
            await invalidate_financial_caches()
        return result

    async def storno_health_insurance(
        self,
        health_insurance_id: int,
    ) -> HealthInsurance | None:
        """Create a storno (reversal) for a health insurance payment.

        Used for booked/finalized payments that cannot be deleted.

        Args:
            health_insurance_id: ID to reverse

        Returns:
            Created storno HealthInsurance or None
        """
        result = await self.health_insurance_repo.storno(health_insurance_id)
        if result:
            await invalidate_financial_caches()
        return result

    async def get_summary(
        self,
        year: int | None = None,
    ) -> HealthInsuranceSummary:
        """Get annual health insurance summary.

        Provides aggregated data for display and reporting.

        Args:
            year: Tax year (default: current year)

        Returns:
            HealthInsuranceSummary with totals and deductions
        """
        year = year or date.today().year
        payments = await self.health_insurance_repo.get_by_year(year)
        return self.calculator.calculate_annual_summary(payments, year)

    async def get_deduction(
        self,
        year: int | None = None,
    ) -> HealthInsuranceDeduction:
        """Get detailed tax deduction breakdown for Anlage Vorsorgeaufwand.

        Provides all values needed for the German tax return form:
        - Line 16/17: Beiträge zur Krankenversicherung (Basisabsicherung)
        - Line 18/19: Beiträge zur Pflegeversicherung
        - Line 20/21: Sonstige Vorsorgeaufwendungen (Wahlleistungen)

        Args:
            year: Tax year (default: current year)

        Returns:
            HealthInsuranceDeduction with all values for tax return
        """
        year = year or date.today().year
        payments = await self.health_insurance_repo.get_by_year(year)
        return self.calculator.calculate_deduction(payments, year)

    async def get_providers(
        self,
        insurance_type: InsuranceType | None = None,
    ) -> list[HealthInsuranceProvider]:
        """Get list of health insurance providers.

        Args:
            insurance_type: Filter by GKV/PKV (None for all)

        Returns:
            List of HealthInsuranceProvider objects
        """
        if insurance_type:
            return await self.provider_repo.get_by_type(insurance_type)
        return await self.provider_repo.get_all()

    async def get_provider(
        self,
        provider_id: int,
    ) -> HealthInsuranceProvider | None:
        """Get a specific provider by ID.

        Args:
            provider_id: Provider ID

        Returns:
            HealthInsuranceProvider or None
        """
        return await self.provider_repo.get_by_id(provider_id)

    async def get_recent_payments(
        self,
        limit: int = 5,
    ) -> list[HealthInsurance]:
        """Get most recent health insurance payments.

        Args:
            limit: Max results

        Returns:
            List of recent payments
        """
        return await self.health_insurance_repo.get_all(limit=limit)

    async def get_coverage_breakdown(
        self,
        year: int | None = None,
    ) -> dict[CoverageType, dict]:
        """Get payment totals by coverage type.

        Args:
            year: Filter by year (default: current year)

        Returns:
            Dictionary mapping coverage type to totals and deductible amounts
        """
        year = year or date.today().year
        payments = await self.health_insurance_repo.get_by_year(year)

        from decimal import Decimal

        breakdown: dict[CoverageType, dict] = {}

        for coverage in CoverageType:
            coverage_payments = [p for p in payments if p.coverage_type == coverage]
            total_paid = sum(p.amount for p in coverage_payments)
            total_deductible = sum(p.deductible_amount for p in coverage_payments)

            breakdown[coverage] = {
                "total_paid": total_paid.quantize(Decimal("0.01")) if coverage_payments else Decimal("0"),
                "total_deductible": total_deductible.quantize(Decimal("0.01")) if coverage_payments else Decimal("0"),
                "payment_count": len(coverage_payments),
            }

        return breakdown


# FastAPI dependency
async def get_health_insurance_service() -> HealthInsuranceService:
    """FastAPI dependency for HealthInsuranceService."""
    return HealthInsuranceService()
