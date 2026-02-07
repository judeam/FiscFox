"""German VAT Calculator (Umsatzsteuer) per UStG.

Implements VAT calculations including:
- Standard rate (19%)
- Reduced rate (7%)
- Reverse Charge (0% for B2B international, § 13b UStG)
- Kleinunternehmerregelung (§ 19 UStG)
- USt-Voranmeldung liability calculation

All monetary values use Decimal for precision.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from src.core.models import (
    Expense,
    Invoice,
    TaxYearConfig,
    UmsatzsteuerResult,
    VatRate,
    get_tax_config,
)


class UstFrequency(StrEnum):
    """USt-Voranmeldung filing frequency based on prior year VAT liability."""
    MONTHLY = "monthly"      # > €7,500 prior year OR first 2 years of business
    QUARTERLY = "quarterly"  # €2,000 - €7,500 prior year
    ANNUAL = "annual"        # < €2,000 prior year


@dataclass
class VatBreakdown:
    """Detailed VAT breakdown by rate."""
    standard_base: Decimal = Decimal("0")     # Net amount at 19%
    standard_vat: Decimal = Decimal("0")      # VAT at 19%
    reduced_base: Decimal = Decimal("0")      # Net amount at 7%
    reduced_vat: Decimal = Decimal("0")       # VAT at 7%
    zero_base: Decimal = Decimal("0")         # Net amount at 0% (Reverse Charge)
    reverse_charge_base: Decimal = Decimal("0")  # B2B international


class UmsatzsteuerCalculator:
    """Calculator for German VAT (Umsatzsteuer, § 12 UStG).

    Handles:
    - Standard VAT calculation (19%/7%)
    - Input VAT (Vorsteuer) from expenses
    - Reverse Charge for international B2B (§ 13b UStG)
    - Kleinunternehmerregelung eligibility (§ 19 UStG)
    - USt-Voranmeldung liability calculation

    Usage:
        calc = UmsatzsteuerCalculator(2026)
        result = calc.calculate_period_liability(invoices, expenses, "2026-01")
        print(f"VAT liability: {result.zahllast} EUR")
    """

    # VAT rates as Decimal for precise calculation
    RATE_STANDARD = Decimal("0.19")  # 19%
    RATE_REDUCED = Decimal("0.07")   # 7%
    RATE_ZERO = Decimal("0.00")      # 0%

    def __init__(self, year: int):
        """Initialize calculator with tax year configuration.

        Args:
            year: Tax year
        """
        self.config: TaxYearConfig = get_tax_config(year)
        self.year = year

    def calculate_vat(self, net_amount: Decimal, rate: VatRate) -> Decimal:
        """Calculate VAT amount for a net amount.

        § 12 UStG - VAT rates

        Args:
            net_amount: Net amount (before VAT)
            rate: VAT rate to apply

        Returns:
            VAT amount
        """
        rate_decimal = Decimal(rate.value)
        vat = (net_amount * rate_decimal).quantize(Decimal("0.01"))
        return vat

    def extract_vat_from_gross(self, gross_amount: Decimal, rate: VatRate) -> tuple[Decimal, Decimal]:
        """Extract net amount and VAT from gross amount.

        Used for expenses where gross is recorded.

        Args:
            gross_amount: Gross amount (including VAT)
            rate: VAT rate

        Returns:
            Tuple of (net_amount, vat_amount)
        """
        rate_decimal = Decimal(rate.value)
        divisor = Decimal("1") + rate_decimal
        net = (gross_amount / divisor).quantize(Decimal("0.01"))
        vat = (gross_amount - net).quantize(Decimal("0.01"))
        return net, vat

    def calculate_invoice_breakdown(self, invoices: list[Invoice]) -> VatBreakdown:
        """Calculate VAT breakdown from invoices (Umsatzsteuer collected).

        Args:
            invoices: List of invoices

        Returns:
            VatBreakdown with amounts by rate
        """
        breakdown = VatBreakdown()

        for inv in invoices:
            # For invoices, amount is typically net
            net_amount = inv.amount_net
            vat_amount = inv.vat_amount

            if inv.vat_rate == VatRate.STANDARD:
                breakdown.standard_base += net_amount
                breakdown.standard_vat += vat_amount
            elif inv.vat_rate == VatRate.REDUCED:
                breakdown.reduced_base += net_amount
                breakdown.reduced_vat += vat_amount
            elif inv.vat_rate == VatRate.ZERO:
                # Reverse Charge - B2B international
                breakdown.zero_base += net_amount
                breakdown.reverse_charge_base += net_amount

        return breakdown

    def calculate_expense_vorsteuer(self, expenses: list[Expense]) -> VatBreakdown:
        """Calculate input VAT (Vorsteuer) from expenses.

        Vorsteuer can be deducted from collected USt.

        Args:
            expenses: List of expenses

        Returns:
            VatBreakdown with deductible VAT amounts
        """
        breakdown = VatBreakdown()

        for exp in expenses:
            net_amount = exp.amount_net
            vat_amount = exp.vat_amount

            if exp.vat_rate == VatRate.STANDARD:
                breakdown.standard_base += net_amount
                breakdown.standard_vat += vat_amount
            elif exp.vat_rate == VatRate.REDUCED:
                breakdown.reduced_base += net_amount
                breakdown.reduced_vat += vat_amount
            # No Vorsteuer deduction for zero-rated (insurance, education)

        return breakdown

    def calculate_period_liability(
        self,
        invoices: list[Invoice],
        expenses: list[Expense],
        period: str,
    ) -> UmsatzsteuerResult:
        """Calculate VAT liability for a period (month or quarter).

        Zahllast = Umsatzsteuer (collected) - Vorsteuer (paid)

        Args:
            invoices: Invoices for the period
            expenses: Expenses for the period
            period: Period identifier (e.g., '2026-01' or '2026-Q1')

        Returns:
            UmsatzsteuerResult with liability breakdown
        """
        # Calculate collected USt from invoices
        invoice_breakdown = self.calculate_invoice_breakdown(invoices)
        ust_collected = (
            invoice_breakdown.standard_vat +
            invoice_breakdown.reduced_vat
        )

        # Calculate deductible Vorsteuer from expenses
        expense_breakdown = self.calculate_expense_vorsteuer(expenses)
        vorsteuer = (
            expense_breakdown.standard_vat +
            expense_breakdown.reduced_vat
        )

        # Net liability (Zahllast)
        zahllast = ust_collected - vorsteuer

        # Check if this is a Nullmeldung (all Reverse Charge)
        total_invoice_net = (
            invoice_breakdown.standard_base +
            invoice_breakdown.reduced_base +
            invoice_breakdown.zero_base
        )
        is_nullmeldung = (
            ust_collected == Decimal("0") and
            invoice_breakdown.reverse_charge_base > Decimal("0")
        )

        # Check Kleinunternehmer eligibility (simplified check)
        # Full check requires prior year revenue
        kleinunternehmer_eligible = total_invoice_net <= self.config.kleinunternehmer_prev_year

        return UmsatzsteuerResult(
            period=period,
            umsatzsteuer_collected=ust_collected.quantize(Decimal("0.01")),
            vorsteuer_paid=vorsteuer.quantize(Decimal("0.01")),
            zahllast=zahllast.quantize(Decimal("0.01")),
            is_nullmeldung=is_nullmeldung,
            kleinunternehmer_eligible=kleinunternehmer_eligible,
        )

    def check_kleinunternehmer_eligibility(
        self,
        revenue_prior_year: Decimal,
        revenue_current_year: Decimal,
    ) -> tuple[bool, str | None]:
        """Check Kleinunternehmerregelung eligibility (§ 19 UStG).

        2025 Reform thresholds:
        - Previous year NET revenue ≤ €25,000
        - Current year expected NET revenue ≤ €100,000

        IMPORTANT: If €100,000 exceeded, immediate full VAT liability.

        Args:
            revenue_prior_year: Prior year NET revenue
            revenue_current_year: Current/expected year NET revenue

        Returns:
            Tuple of (is_eligible, reason_if_not_eligible)
        """
        # Check prior year threshold
        if revenue_prior_year > self.config.kleinunternehmer_prev_year:
            return False, (
                f"Vorjahresumsatz ({revenue_prior_year:,.2f} EUR) "
                f"übersteigt Grenze ({self.config.kleinunternehmer_prev_year:,.2f} EUR)"
            )

        # Check current year threshold
        if revenue_current_year > self.config.kleinunternehmer_curr_year:
            return False, (
                f"Aktueller Umsatz ({revenue_current_year:,.2f} EUR) "
                f"übersteigt Grenze ({self.config.kleinunternehmer_curr_year:,.2f} EUR) - "
                f"SOFORTIGE Umsatzsteuerpflicht!"
            )

        return True, None

    def determine_filing_frequency(
        self,
        prior_year_vat_liability: Decimal,
        is_new_business: bool = False,
    ) -> UstFrequency:
        """Determine USt-Voranmeldung filing frequency.

        Based on prior year VAT liability:
        - > €7,500: Monthly
        - €2,000 - €7,500: Quarterly
        - < €2,000: Annual

        Exception: First 2 calendar years of business → Monthly

        Args:
            prior_year_vat_liability: Prior year VAT liability
            is_new_business: True if in first 2 years of business

        Returns:
            Filing frequency
        """
        if is_new_business:
            return UstFrequency.MONTHLY

        if prior_year_vat_liability > Decimal("7500"):
            return UstFrequency.MONTHLY
        elif prior_year_vat_liability >= Decimal("2000"):
            return UstFrequency.QUARTERLY
        else:
            return UstFrequency.ANNUAL

    def calculate_reverse_charge_total(self, invoices: list[Invoice]) -> Decimal:
        """Calculate total Reverse Charge revenue for Zusammenfassende Meldung.

        B2B services to EU clients must be reported in ZM by 25th.
        § 13b UStG

        Args:
            invoices: All invoices

        Returns:
            Total Reverse Charge revenue (0% VAT B2B international)
        """
        total = Decimal("0")
        for inv in invoices:
            if inv.vat_rate == VatRate.ZERO:
                total += inv.amount_net
        return total.quantize(Decimal("0.01"))


def calculate_vat_from_gross(gross: Decimal, rate: VatRate) -> tuple[Decimal, Decimal]:
    """Convenience function to extract net and VAT from gross.

    Args:
        gross: Gross amount including VAT
        rate: VAT rate

    Returns:
        Tuple of (net, vat)
    """
    calc = UmsatzsteuerCalculator(2026)
    return calc.extract_vat_from_gross(gross, rate)


def calculate_vat_liability(
    invoices: list[Invoice],
    expenses: list[Expense],
    period: str,
    year: int = 2026,
) -> UmsatzsteuerResult:
    """Convenience function for VAT liability calculation.

    Args:
        invoices: Invoices for period
        expenses: Expenses for period
        period: Period identifier
        year: Tax year

    Returns:
        UmsatzsteuerResult with liability breakdown
    """
    calc = UmsatzsteuerCalculator(year)
    return calc.calculate_period_liability(invoices, expenses, period)
