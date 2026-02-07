"""Report data models for tax reports and financial summaries.

These models are used to pass structured data from ReportService to templates.
All monetary values use Decimal for precision.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class ReportPeriodType(StrEnum):
    """Report period type for filtering."""

    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


# =============================================================================
# USt-Voranmeldung (Monthly VAT Return)
# =============================================================================


@dataclass
class UstVoranmeldungData:
    """USt-Voranmeldung (Monthly VAT Return) data.

    Contains VAT breakdown by rate for § 18 UStG filing.
    """

    period: str  # "Januar 2026" or "Q1 2026"
    period_start: date
    period_end: date
    year: int

    # Revenue breakdown by VAT rate
    revenue_standard_net: Decimal  # Net amount at 19%
    revenue_standard_vat: Decimal  # VAT collected at 19%
    revenue_reduced_net: Decimal  # Net amount at 7%
    revenue_reduced_vat: Decimal  # VAT collected at 7%
    reverse_charge_net: Decimal  # Net at 0% (EU B2B)

    # Expense breakdown (Vorsteuer)
    vorsteuer_standard: Decimal  # Input VAT 19%
    vorsteuer_reduced: Decimal  # Input VAT 7%

    # Calculated totals
    total_ust_collected: Decimal  # Sum of all VAT collected
    total_vorsteuer: Decimal  # Sum of all input VAT
    zahllast: Decimal  # Net liability (USt - Vorsteuer)

    # Flags
    is_nullmeldung: bool  # True if all Reverse Charge (zero liability)


# =============================================================================
# Zusammenfassende Meldung (EC Sales List)
# =============================================================================


@dataclass
class ZsmClientEntry:
    """Single client entry for Zusammenfassende Meldung (§ 18a UStG)."""

    client_id: int
    client_name: str
    vat_id: str  # EU VAT ID (e.g., NL123456789B01)
    country_code: str  # ISO 2-letter code
    total_net: Decimal  # Total Reverse Charge amount
    invoice_count: int


@dataclass
class ZsmData:
    """Zusammenfassende Meldung (EC Sales List) data.

    Lists all EU reverse charge invoices grouped by client VAT ID.
    § 18a UStG - EC Sales List reporting.
    """

    period: str  # "Q1 2026"
    period_start: date
    period_end: date
    year: int
    quarter: int

    entries: list[ZsmClientEntry] = field(default_factory=list)
    total_reverse_charge: Decimal = Decimal("0")
    client_count: int = 0


# =============================================================================
# EÜR (Einnahmen-Überschuss-Rechnung)
# =============================================================================


@dataclass
class EurCategoryBreakdown:
    """EÜR expense category breakdown."""

    category_key: str  # ExpenseCategory value (e.g., "software")
    amount_net: Decimal
    vorsteuer: Decimal


@dataclass
class EurData:
    """Einnahmen-Überschuss-Rechnung (Income Statement) data.

    Anlage EÜR for income tax return.
    § 4 Abs. 3 EStG - Cash basis accounting.
    """

    year: int

    # Revenue breakdown
    revenue_domestic_net: Decimal  # Domestic (19% VAT)
    revenue_domestic_vat: Decimal  # VAT on domestic
    revenue_reduced_net: Decimal  # Reduced rate (7%)
    revenue_reduced_vat: Decimal  # VAT on reduced
    revenue_eu_net: Decimal  # Reverse Charge (0%)
    total_einnahmen: Decimal  # Sum of all revenue (net)

    # Expenses by category
    expense_categories: list[EurCategoryBreakdown] = field(default_factory=list)
    total_ausgaben: Decimal = Decimal("0")
    total_vorsteuer: Decimal = Decimal("0")

    # Result
    gewinn: Decimal = Decimal("0")  # Profit (Einnahmen - Ausgaben)

    @property
    def is_loss(self) -> bool:
        """Check if result is a loss (Verlust)."""
        return self.gewinn < Decimal("0")


# =============================================================================
# Jahresübersicht (Annual Overview)
# =============================================================================


@dataclass
class AnnualOverviewData:
    """Jahresübersicht (Annual Overview) with tax estimates.

    Comprehensive year summary with income tax calculation.
    """

    year: int

    # Revenue metrics
    total_revenue_gross: Decimal
    total_revenue_net: Decimal

    # Expense metrics
    total_expenses_gross: Decimal
    total_expenses_net: Decimal

    # Tax calculations
    taxable_income: Decimal  # Revenue net - Expenses net
    einkommensteuer: Decimal  # Income tax (§ 32a EStG)
    solidaritaetszuschlag: Decimal  # 5.5% Soli
    total_ust_collected: Decimal  # VAT collected
    total_vorsteuer: Decimal  # Input VAT
    ust_zahllast: Decimal  # Net VAT liability
    total_tax_burden: Decimal  # ESt + Soli + USt liability
    effective_tax_rate: Decimal  # As percentage

    # Net result
    net_after_tax: Decimal  # Taxable income - Income tax

    # Year-over-year comparison (None if no prior year data)
    yoy_revenue_change: Decimal | None = None  # Percentage change
    yoy_expense_change: Decimal | None = None

    # Monthly breakdown for charts (month number -> amount)
    monthly_revenue: dict[int, Decimal] = field(default_factory=dict)
    monthly_expenses: dict[int, Decimal] = field(default_factory=dict)
