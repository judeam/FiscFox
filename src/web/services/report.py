"""Report service for generating tax reports and financial summaries.

Aggregates data from repositories and tax calculators for:
- USt-Voranmeldung (Monthly VAT Return)
- Zusammenfassende Meldung (EC Sales List)
- Einnahmen-Überschuss-Rechnung (EÜR)
- Jahresübersicht (Annual Overview)

All monetary values use Decimal for precision.
"""

import calendar
import logging
from datetime import date
from decimal import Decimal

from src.core.models import ExpenseCategory, VatRate
from src.core.tax import EinkommensteuerCalculator, UmsatzsteuerCalculator
from src.db.repository import (
    ClientRepository,
    ExpenseRepository,
    InvoiceRepository,
)
from src.web.models.reports import (
    AnnualOverviewData,
    EurCategoryBreakdown,
    EurData,
    ReportPeriodType,
    UstVoranmeldungData,
    ZsmClientEntry,
    ZsmData,
)

logger = logging.getLogger(__name__)


class ReportService:
    """Service for generating tax reports and financial summaries.

    Combines data from repositories with tax calculators to generate
    formatted report data for USt-Voranmeldung, ZSM, EÜR, and
    Jahresübersicht.
    """

    # Month names for period labels
    MONTH_NAMES_DE = [
        "",
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ]

    MONTH_NAMES_EN = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    def __init__(
        self,
        expense_repo: ExpenseRepository | None = None,
        invoice_repo: InvoiceRepository | None = None,
        client_repo: ClientRepository | None = None,
    ):
        """Initialize report service.

        Args:
            expense_repo: Expense repository (default: new instance)
            invoice_repo: Invoice repository (default: new instance)
            client_repo: Client repository (default: new instance)
        """
        self.expense_repo = expense_repo or ExpenseRepository()
        self.invoice_repo = invoice_repo or InvoiceRepository()
        self.client_repo = client_repo or ClientRepository()

    # =========================================================================
    # Period Calculation Helpers
    # =========================================================================

    def get_period_dates(
        self,
        year: int,
        period_type: ReportPeriodType,
        period_num: int = 1,
        lang: str = "de",
    ) -> tuple[date, date, str]:
        """Calculate period start/end dates and label.

        Args:
            year: Tax year
            period_type: MONTH, QUARTER, or YEAR
            period_num: Month (1-12) or Quarter (1-4)
            lang: Language for label ("de" or "en")

        Returns:
            Tuple of (start_date, end_date, period_label)
        """
        month_names = self.MONTH_NAMES_DE if lang == "de" else self.MONTH_NAMES_EN

        if period_type == ReportPeriodType.MONTH:
            # Ensure month is valid
            month = max(1, min(12, period_num))
            start_date = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end_date = date(year, month, last_day)
            label = f"{month_names[month]} {year}"

        elif period_type == ReportPeriodType.QUARTER:
            # Ensure quarter is valid
            quarter = max(1, min(4, period_num))
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            start_date = date(year, start_month, 1)
            last_day = calendar.monthrange(year, end_month)[1]
            end_date = date(year, end_month, last_day)
            label = f"Q{quarter} {year}"

        else:  # YEAR
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
            label = str(year)

        return start_date, end_date, label

    def _calc_yoy_change(
        self, current: Decimal, previous: Decimal
    ) -> Decimal | None:
        """Calculate year-over-year percentage change."""
        if previous == Decimal("0"):
            return None
        return ((current - previous) / previous * 100).quantize(Decimal("0.1"))

    # =========================================================================
    # USt-Voranmeldung (Monthly VAT Return)
    # =========================================================================

    async def get_ust_voranmeldung(
        self,
        year: int,
        period_type: ReportPeriodType,
        period_num: int,
        lang: str = "de",
    ) -> UstVoranmeldungData:
        """Generate USt-Voranmeldung data.

        Uses UmsatzsteuerCalculator for VAT breakdown by rate.

        § 18 Abs. 1 UStG - Monthly/quarterly filing

        Args:
            year: Tax year
            period_type: MONTH, QUARTER, or YEAR
            period_num: Period number (1-12 for month, 1-4 for quarter)
            lang: Language for labels

        Returns:
            UstVoranmeldungData with full VAT breakdown
        """
        logger.debug(
            f"Generating USt-Voranmeldung for {year} {period_type.value} {period_num}"
        )

        start_date, end_date, period_label = self.get_period_dates(
            year, period_type, period_num, lang
        )

        # Get invoices and expenses for period
        invoices = await self.invoice_repo.get_by_period(start_date, end_date)
        expenses = await self.expense_repo.get_by_period(start_date, end_date)

        # Use UmsatzsteuerCalculator for breakdown
        ust_calc = UmsatzsteuerCalculator(year)
        invoice_breakdown = ust_calc.calculate_invoice_breakdown(invoices)
        expense_breakdown = ust_calc.calculate_expense_vorsteuer(expenses)

        # Calculate period liability
        period_id = (
            f"{year}-{period_num:02d}"
            if period_type == ReportPeriodType.MONTH
            else f"{year}-Q{period_num}"
        )
        result = ust_calc.calculate_period_liability(invoices, expenses, period_id)

        return UstVoranmeldungData(
            period=period_label,
            period_start=start_date,
            period_end=end_date,
            year=year,
            # Revenue by rate
            revenue_standard_net=invoice_breakdown.standard_base,
            revenue_standard_vat=invoice_breakdown.standard_vat,
            revenue_reduced_net=invoice_breakdown.reduced_base,
            revenue_reduced_vat=invoice_breakdown.reduced_vat,
            reverse_charge_net=invoice_breakdown.reverse_charge_base,
            # Vorsteuer
            vorsteuer_standard=expense_breakdown.standard_vat,
            vorsteuer_reduced=expense_breakdown.reduced_vat,
            # Totals
            total_ust_collected=result.umsatzsteuer_collected,
            total_vorsteuer=result.vorsteuer_paid,
            zahllast=result.zahllast,
            is_nullmeldung=result.is_nullmeldung,
        )

    # =========================================================================
    # Zusammenfassende Meldung (EC Sales List)
    # =========================================================================

    async def get_zsm(
        self,
        year: int,
        quarter: int,
        lang: str = "de",
    ) -> ZsmData:
        """Generate Zusammenfassende Meldung data.

        Lists all EU reverse charge invoices grouped by client VAT ID.

        § 18a UStG - EC Sales List reporting (quarterly)

        Args:
            year: Tax year
            quarter: Quarter number (1-4)
            lang: Language for labels

        Returns:
            ZsmData with EU client entries
        """
        logger.debug(f"Generating ZSM for Q{quarter} {year}")

        start_date, end_date, period_label = self.get_period_dates(
            year, ReportPeriodType.QUARTER, quarter, lang
        )

        # Get all invoices for period
        invoices = await self.invoice_repo.get_by_period(start_date, end_date)

        # Filter for reverse charge invoices (0% VAT = EU B2B)
        rc_invoices = [inv for inv in invoices if inv.vat_rate == VatRate.ZERO]

        # Group by client name (since we may not have client_id linked)
        # In practice, should be grouped by VAT ID
        client_totals: dict[str, dict] = {}
        for inv in rc_invoices:
            client_name = inv.client
            if client_name not in client_totals:
                client_totals[client_name] = {
                    "total": Decimal("0"),
                    "count": 0,
                }
            client_totals[client_name]["total"] += inv.amount_net
            client_totals[client_name]["count"] += 1

        # Look up client VAT IDs
        entries = []
        for client_name, totals in client_totals.items():
            # Try to find client by name to get VAT ID
            clients = await self.client_repo.search(client_name, limit=1)
            if clients and clients[0].vat_id:
                client = clients[0]
                entries.append(
                    ZsmClientEntry(
                        client_id=client.id,
                        client_name=client.name,
                        vat_id=client.vat_id,
                        country_code=client.country,
                        total_net=totals["total"].quantize(Decimal("0.01")),
                        invoice_count=totals["count"],
                    )
                )
            else:
                # Client without VAT ID - still include for reporting
                entries.append(
                    ZsmClientEntry(
                        client_id=0,
                        client_name=client_name,
                        vat_id="",
                        country_code="EU",
                        total_net=totals["total"].quantize(Decimal("0.01")),
                        invoice_count=totals["count"],
                    )
                )

        # Sort by total descending
        entries.sort(key=lambda e: e.total_net, reverse=True)

        total_rc = sum((e.total_net for e in entries), Decimal("0"))

        return ZsmData(
            period=period_label,
            period_start=start_date,
            period_end=end_date,
            year=year,
            quarter=quarter,
            entries=entries,
            total_reverse_charge=total_rc,
            client_count=len(entries),
        )

    # =========================================================================
    # EÜR (Einnahmen-Überschuss-Rechnung)
    # =========================================================================

    async def get_eur(self, year: int) -> EurData:
        """Generate EÜR (Income Statement) data.

        Anlage EÜR for income tax return.
        § 4 Abs. 3 EStG - Cash basis accounting

        Args:
            year: Tax year

        Returns:
            EurData with income/expense breakdown
        """
        logger.debug(f"Generating EÜR for {year}")

        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        # Get all invoices for revenue breakdown
        invoices = await self.invoice_repo.get_by_period(year_start, year_end)

        # Calculate revenue by VAT rate
        revenue_standard_net = Decimal("0")
        revenue_standard_vat = Decimal("0")
        revenue_reduced_net = Decimal("0")
        revenue_reduced_vat = Decimal("0")
        revenue_eu_net = Decimal("0")

        for inv in invoices:
            if inv.vat_rate == VatRate.STANDARD:
                revenue_standard_net += inv.amount_net
                revenue_standard_vat += inv.vat_amount
            elif inv.vat_rate == VatRate.REDUCED:
                revenue_reduced_net += inv.amount_net
                revenue_reduced_vat += inv.vat_amount
            elif inv.vat_rate == VatRate.ZERO:
                revenue_eu_net += inv.amount_net

        total_revenue = revenue_standard_net + revenue_reduced_net + revenue_eu_net

        # Get expenses by category
        expenses = await self.expense_repo.get_by_period(year_start, year_end)

        # Group by category
        category_totals: dict[ExpenseCategory, tuple[Decimal, Decimal]] = {}
        for exp in expenses:
            current = category_totals.get(exp.category, (Decimal("0"), Decimal("0")))
            category_totals[exp.category] = (
                current[0] + exp.amount_net,
                current[1] + exp.vat_amount,
            )

        # Build category breakdown list
        expense_categories = [
            EurCategoryBreakdown(
                category_key=cat.value,
                amount_net=totals[0].quantize(Decimal("0.01")),
                vorsteuer=totals[1].quantize(Decimal("0.01")),
            )
            for cat, totals in sorted(
                category_totals.items(), key=lambda x: x[1][0], reverse=True
            )
        ]

        total_ausgaben = sum((cat.amount_net for cat in expense_categories), Decimal("0"))
        total_vorsteuer = sum((cat.vorsteuer for cat in expense_categories), Decimal("0"))
        gewinn = total_revenue - total_ausgaben

        return EurData(
            year=year,
            revenue_domestic_net=revenue_standard_net.quantize(Decimal("0.01")),
            revenue_domestic_vat=revenue_standard_vat.quantize(Decimal("0.01")),
            revenue_reduced_net=revenue_reduced_net.quantize(Decimal("0.01")),
            revenue_reduced_vat=revenue_reduced_vat.quantize(Decimal("0.01")),
            revenue_eu_net=revenue_eu_net.quantize(Decimal("0.01")),
            total_einnahmen=total_revenue.quantize(Decimal("0.01")),
            expense_categories=expense_categories,
            total_ausgaben=total_ausgaben.quantize(Decimal("0.01")),
            total_vorsteuer=total_vorsteuer.quantize(Decimal("0.01")),
            gewinn=gewinn.quantize(Decimal("0.01")),
        )

    # =========================================================================
    # Jahresübersicht (Annual Overview)
    # =========================================================================

    async def get_annual_overview(self, year: int) -> AnnualOverviewData:
        """Generate Annual Overview with tax estimates.

        Comprehensive year summary with income tax calculation.

        Args:
            year: Tax year

        Returns:
            AnnualOverviewData with full financial summary
        """
        logger.debug(f"Generating Annual Overview for {year}")

        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        prev_year_start = date(year - 1, 1, 1)
        prev_year_end = date(year - 1, 12, 31)

        # Current year revenue
        revenue_net, revenue_vat, rc_total = await self.invoice_repo.get_revenue_by_period(
            year_start, year_end
        )
        total_revenue_gross = revenue_net + revenue_vat

        # Current year expenses
        expenses_net, vorsteuer = await self.expense_repo.get_total_by_period(
            year_start, year_end
        )
        total_expenses_gross = expenses_net + vorsteuer

        # Previous year for comparison
        prev_revenue_net, prev_revenue_vat, _ = await self.invoice_repo.get_revenue_by_period(
            prev_year_start, prev_year_end
        )
        prev_expenses_net, prev_vorsteuer = await self.expense_repo.get_total_by_period(
            prev_year_start, prev_year_end
        )

        # Tax calculations
        taxable_income = revenue_net - expenses_net

        # Income tax calculation
        est_calc = EinkommensteuerCalculator(year)
        est_result = est_calc.calculate(max(taxable_income, Decimal("0")))

        # VAT liability
        ust_zahllast = revenue_vat - vorsteuer

        # Total tax burden (ESt + Soli only if positive income)
        total_tax = est_result.total_tax + max(ust_zahllast, Decimal("0"))

        # Effective rate
        effective_rate = (
            (est_result.total_tax / taxable_income * 100).quantize(Decimal("0.1"))
            if taxable_income > 0
            else Decimal("0")
        )

        # Net after tax (only income tax, not VAT which is pass-through)
        net_after_tax = taxable_income - est_result.total_tax

        # Year-over-year changes
        prev_total_revenue = prev_revenue_net + prev_revenue_vat
        prev_total_expenses = prev_expenses_net + prev_vorsteuer
        yoy_revenue = self._calc_yoy_change(total_revenue_gross, prev_total_revenue)
        yoy_expense = self._calc_yoy_change(total_expenses_gross, prev_total_expenses)

        # Monthly breakdown
        monthly_revenue_list = await self.invoice_repo.get_monthly_revenue(year, None)
        monthly_revenue = {month: amount for month, amount in monthly_revenue_list}

        # Fill in missing months with zeros
        for m in range(1, 13):
            if m not in monthly_revenue:
                monthly_revenue[m] = Decimal("0")

        return AnnualOverviewData(
            year=year,
            total_revenue_gross=total_revenue_gross.quantize(Decimal("0.01")),
            total_revenue_net=revenue_net.quantize(Decimal("0.01")),
            total_expenses_gross=total_expenses_gross.quantize(Decimal("0.01")),
            total_expenses_net=expenses_net.quantize(Decimal("0.01")),
            taxable_income=taxable_income.quantize(Decimal("0.01")),
            einkommensteuer=est_result.einkommensteuer.quantize(Decimal("0.01")),
            solidaritaetszuschlag=est_result.solidaritaetszuschlag.quantize(
                Decimal("0.01")
            ),
            total_ust_collected=revenue_vat.quantize(Decimal("0.01")),
            total_vorsteuer=vorsteuer.quantize(Decimal("0.01")),
            ust_zahllast=ust_zahllast.quantize(Decimal("0.01")),
            total_tax_burden=total_tax.quantize(Decimal("0.01")),
            effective_tax_rate=effective_rate,
            net_after_tax=net_after_tax.quantize(Decimal("0.01")),
            yoy_revenue_change=yoy_revenue,
            yoy_expense_change=yoy_expense,
            monthly_revenue=monthly_revenue,
            monthly_expenses={},  # TODO: Add monthly expense aggregation if needed
        )


async def get_report_service() -> ReportService:
    """FastAPI dependency for ReportService."""
    return ReportService()
