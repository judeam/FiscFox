"""Health insurance tax deduction calculator (Vorsorgeaufwand).

Implements German health insurance deduction rules per § 10 EStG:
- Basisabsicherung (basic health coverage): Unlimited deduction
- Pflegepflichtversicherung (mandatory care): Unlimited deduction
- Wahlleistungen/Zusatzversicherung: Limited to EUR 2,800/year for freelancers
- GKV with Krankengeld: 4% reduction applies

Reference:
- § 10 Abs. 1 Nr. 3 EStG: Vorsorgeaufwendungen (health insurance contributions)
- § 10 Abs. 4 EStG: Höchstbeträge (annual limits)

All monetary values use Decimal for precision.
"""

from decimal import Decimal

from src.core.models import (
    HEALTH_INSURANCE_SONDERAUSGABEN_LIMIT,
    KRANKENGELD_REDUCTION_RATE,
    CoverageType,
    HealthInsurance,
    HealthInsuranceDeduction,
    HealthInsuranceSummary,
    InsuranceType,
)


class HealthInsuranceCalculator:
    """Calculate health insurance tax deductions per § 10 EStG.

    German health insurance contributions are deductible as Sonderausgaben
    (special expenses) with different rules for different coverage types:

    1. Basisabsicherung (basic health coverage):
       - 100% deductible, no upper limit
       - For GKV with Krankengeldanspruch: 4% reduction
       - § 10 Abs. 1 Nr. 3 Buchst. a EStG

    2. Pflegepflichtversicherung (mandatory care insurance):
       - 100% deductible, no upper limit
       - § 10 Abs. 1 Nr. 3 Buchst. a EStG

    3. Wahlleistungen / Zusatzversicherung (optional/supplementary):
       - Deductible up to annual limit
       - EUR 2,800 for freelancers (no employer subsidy)
       - EUR 1,900 for employees (with employer subsidy)
       - § 10 Abs. 4 EStG

    Usage:
        calculator = HealthInsuranceCalculator()

        # Calculate deduction for a single payment
        deductible = calculator.calculate_single_deduction(payment)

        # Calculate annual summary for tax return
        summary = calculator.calculate_annual_summary(payments, year=2026)

        # Get detailed deduction breakdown for Anlage Vorsorgeaufwand
        deduction = calculator.calculate_deduction(payments, year=2026)
    """

    def __init__(
        self,
        sonderausgaben_limit: Decimal = HEALTH_INSURANCE_SONDERAUSGABEN_LIMIT,
        is_freelancer: bool = True,
    ):
        """Initialize calculator with configuration.

        Args:
            sonderausgaben_limit: Annual limit for Wahlleistungen.
                                  Default: EUR 2,800 for freelancers.
            is_freelancer: True for freelancers (EUR 2,800 limit),
                          False for employees (EUR 1,900 limit).
        """
        # Freelancers get higher limit since no employer subsidy
        if is_freelancer:
            self.limit = sonderausgaben_limit
        else:
            self.limit = Decimal("1900")

    def calculate_single_deduction(self, payment: HealthInsurance) -> Decimal:
        """Calculate deductible amount for a single payment.

        Note: This does not account for annual limits on Wahlleistungen.
        Use calculate_annual_summary() for proper limit application.

        Args:
            payment: Health insurance payment record

        Returns:
            Deductible amount (before annual limit check for Wahlleistungen)
        """
        if payment.coverage_type in [
            CoverageType.BASIS_KRANKENVERSICHERUNG,
            CoverageType.PFLEGEPFLICHTVERSICHERUNG,
        ]:
            # Unlimited deduction, but 4% reduction for GKV with Krankengeld
            if payment.insurance_type == InsuranceType.GKV and payment.has_krankengeld:
                reduction = payment.amount * KRANKENGELD_REDUCTION_RATE
                return (payment.amount - reduction).quantize(Decimal("0.01"))
            return payment.amount

        # Wahlleistungen/Zusatzversicherung - full amount but subject to limit
        return payment.amount

    def calculate_annual_summary(
        self,
        payments: list[HealthInsurance],
        year: int,
    ) -> HealthInsuranceSummary:
        """Calculate annual summary for display and reporting.

        Args:
            payments: List of health insurance payments
            year: Tax year

        Returns:
            HealthInsuranceSummary with aggregated data
        """
        # Initialize accumulators
        total_paid = Decimal("0")
        basis_total = Decimal("0")
        basis_deductible = Decimal("0")
        wahlleistungen_total = Decimal("0")
        by_coverage: dict[str, Decimal] = {}
        by_provider: dict[int, dict] = {}

        # Filter to requested year
        year_payments = [p for p in payments if p.date.year == year]

        for payment in year_payments:
            total_paid += payment.amount

            # Track by coverage type
            coverage_key = payment.coverage_type.value
            by_coverage[coverage_key] = by_coverage.get(coverage_key, Decimal("0")) + payment.amount

            # Track by provider
            provider_id = payment.provider_id
            if provider_id not in by_provider:
                by_provider[provider_id] = {
                    "provider_id": provider_id,
                    "provider_name": (
                        payment.provider.short_name or payment.provider.name
                        if payment.provider
                        else f"Provider {provider_id}"
                    ),
                    "total": Decimal("0"),
                }
            by_provider[provider_id]["total"] += payment.amount

            # Calculate deductible by category
            if payment.coverage_type in [
                CoverageType.BASIS_KRANKENVERSICHERUNG,
                CoverageType.PFLEGEPFLICHTVERSICHERUNG,
            ]:
                basis_total += payment.amount
                # Apply 4% reduction for GKV with Krankengeld
                if payment.insurance_type == InsuranceType.GKV and payment.has_krankengeld:
                    reduction = payment.amount * KRANKENGELD_REDUCTION_RATE
                    basis_deductible += (payment.amount - reduction).quantize(Decimal("0.01"))
                else:
                    basis_deductible += payment.amount
            else:
                wahlleistungen_total += payment.amount

        # Apply annual limit to Wahlleistungen
        wahlleistungen_deductible = min(wahlleistungen_total, self.limit)
        remaining_limit = max(self.limit - wahlleistungen_total, Decimal("0"))

        # Total deductible
        total_deductible = basis_deductible + wahlleistungen_deductible

        return HealthInsuranceSummary(
            year=year,
            total_paid=total_paid.quantize(Decimal("0.01")),
            basis_total=basis_total.quantize(Decimal("0.01")),
            basis_deductible=basis_deductible.quantize(Decimal("0.01")),
            wahlleistungen_total=wahlleistungen_total.quantize(Decimal("0.01")),
            wahlleistungen_deductible=wahlleistungen_deductible.quantize(Decimal("0.01")),
            total_deductible=total_deductible.quantize(Decimal("0.01")),
            remaining_limit=remaining_limit.quantize(Decimal("0.01")),
            payment_count=len(year_payments),
            by_coverage=by_coverage,
            by_provider=list(by_provider.values()),
        )

    def calculate_deduction(
        self,
        payments: list[HealthInsurance],
        year: int,
    ) -> HealthInsuranceDeduction:
        """Calculate detailed deduction breakdown for Anlage Vorsorgeaufwand.

        This provides all values needed for the German tax return form:
        - Line 16/17: Beiträge zur Krankenversicherung (Basisabsicherung)
        - Line 18/19: Beiträge zur Pflegeversicherung
        - Line 20/21: Sonstige Vorsorgeaufwendungen (Wahlleistungen)

        Args:
            payments: List of health insurance payments
            year: Tax year

        Returns:
            HealthInsuranceDeduction with all values for tax return
        """
        # Initialize accumulators
        krankenversicherung_basis = Decimal("0")
        pflegeversicherung = Decimal("0")
        krankengeld_reduction = Decimal("0")
        wahlleistungen_paid = Decimal("0")
        total_paid = Decimal("0")

        # Filter to requested year
        year_payments = [p for p in payments if p.date.year == year]

        for payment in year_payments:
            total_paid += payment.amount

            if payment.coverage_type == CoverageType.BASIS_KRANKENVERSICHERUNG:
                # Basic health coverage
                if payment.insurance_type == InsuranceType.GKV and payment.has_krankengeld:
                    # 4% reduction for GKV with Krankengeld
                    reduction = payment.amount * KRANKENGELD_REDUCTION_RATE
                    krankengeld_reduction += reduction.quantize(Decimal("0.01"))
                    krankenversicherung_basis += (payment.amount - reduction).quantize(Decimal("0.01"))
                else:
                    krankenversicherung_basis += payment.amount

            elif payment.coverage_type == CoverageType.PFLEGEPFLICHTVERSICHERUNG:
                # Mandatory care insurance
                pflegeversicherung += payment.amount

            else:
                # Wahlleistungen / Zusatzversicherung
                wahlleistungen_paid += payment.amount

        # Apply annual limit to Wahlleistungen
        wahlleistungen_deductible = min(wahlleistungen_paid, self.limit)
        wahlleistungen_exceeded = max(wahlleistungen_paid - self.limit, Decimal("0"))

        # Total deductible
        total_deductible = krankenversicherung_basis + pflegeversicherung + wahlleistungen_deductible

        # Effective deduction rate
        if total_paid > 0:
            effective_rate = ((total_deductible / total_paid) * 100).quantize(Decimal("0.01"))
        else:
            effective_rate = Decimal("0")

        return HealthInsuranceDeduction(
            year=year,
            krankenversicherung_basis=krankenversicherung_basis.quantize(Decimal("0.01")),
            pflegeversicherung=pflegeversicherung.quantize(Decimal("0.01")),
            krankengeld_reduction=krankengeld_reduction.quantize(Decimal("0.01")),
            wahlleistungen_paid=wahlleistungen_paid.quantize(Decimal("0.01")),
            wahlleistungen_deductible=wahlleistungen_deductible.quantize(Decimal("0.01")),
            wahlleistungen_exceeded=wahlleistungen_exceeded.quantize(Decimal("0.01")),
            total_paid=total_paid.quantize(Decimal("0.01")),
            total_deductible=total_deductible.quantize(Decimal("0.01")),
            effective_deduction_rate=effective_rate,
        )
