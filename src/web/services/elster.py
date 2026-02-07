"""ELSTER export service for generating UStVA XML files.

Orchestrates the full ELSTER XML export workflow:
1. Load user settings and validate for ELSTER requirements
2. Fetch VAT data for the requested period
3. Map to ELSTER Kennzahlen
4. Generate XML in ISO-8859-15 encoding

Legal References:
- § 18 UStG: USt-Voranmeldung filing obligation
- § 14 Abs. 4 AO: Steuernummer format
"""

import logging
from datetime import date

from src.core.elster import (
    UstvaXmlGenerator,
    build_kennzahlen,
    get_period_type,
    period_to_display,
)
from src.core.elster.exceptions import IncompleteSettingsError
from src.core.models import UserSettings
from src.core.tax.umsatzsteuer import UmsatzsteuerCalculator
from src.db.repository import ExpenseRepository, InvoiceRepository
from src.web.models.reports import ReportPeriodType
from src.web.routes.settings import load_settings_async

logger = logging.getLogger(__name__)


class ElsterExportService:
    """Service for ELSTER UStVA XML export.

    Generates XML files for upload to Mein ELSTER portal.

    Usage:
        service = ElsterExportService()
        xml_bytes, filename = await service.export_ustva_xml(2026, "01/2026")
    """

    def __init__(
        self,
        expense_repo: ExpenseRepository | None = None,
        invoice_repo: InvoiceRepository | None = None,
    ):
        """Initialize ELSTER export service.

        Args:
            expense_repo: Expense repository (default: new instance)
            invoice_repo: Invoice repository (default: new instance)
        """
        self.expense_repo = expense_repo or ExpenseRepository()
        self.invoice_repo = invoice_repo or InvoiceRepository()

    async def export_ustva_xml(
        self,
        year: int,
        period: str,
    ) -> tuple[bytes, str]:
        """Export UStVA as ELSTER XML.

        Args:
            year: Tax year (e.g., 2026)
            period: ELSTER period (e.g., "01/2026" for January, "41/2026" for Q1)

        Returns:
            Tuple of (xml_bytes, suggested_filename)

        Raises:
            IncompleteSettingsError: If user settings are incomplete
            InvalidSteuernummerError: If tax number is invalid
            InvalidPeriodError: If period format is invalid
        """
        logger.info(f"Exporting UStVA XML for period {period}")

        # 1. Load and validate user settings
        settings = await self._load_settings()
        self._validate_settings_for_elster(settings)

        # 2. Get period dates
        period_type = get_period_type(period)
        period_num_str = period.split("/")[0]
        period_num = int(period_num_str)

        # Convert ELSTER period format to internal format
        if period_type == "monthly":
            report_period_type = ReportPeriodType.MONTH
            report_period_num = period_num
        else:
            # Quarterly: 41-44 → 1-4
            report_period_type = ReportPeriodType.QUARTER
            report_period_num = period_num - 40

        start_date, end_date = self._get_period_dates(
            year, report_period_type, report_period_num
        )

        # 3. Fetch VAT data for period
        invoices = await self.invoice_repo.get_by_period(start_date, end_date)
        expenses = await self.expense_repo.get_by_period(start_date, end_date)

        logger.debug(
            f"Found {len(invoices)} invoices and {len(expenses)} expenses "
            f"for period {start_date} - {end_date}"
        )

        # 4. Calculate VAT breakdown
        ust_calc = UmsatzsteuerCalculator(year)
        invoice_breakdown = ust_calc.calculate_invoice_breakdown(invoices)
        expense_breakdown = ust_calc.calculate_expense_vorsteuer(expenses)

        # Calculate Zahllast
        period_id = f"{year}-{period_num:02d}"
        result = ust_calc.calculate_period_liability(invoices, expenses, period_id)

        # 5. Build Kennzahlen
        kennzahlen = build_kennzahlen(
            invoice_breakdown=invoice_breakdown,
            expense_breakdown=expense_breakdown,
            zahllast=result.zahllast,
        )

        logger.debug(
            f"Kennzahlen: KZ81={kennzahlen.kz81}, KZ86={kennzahlen.kz86}, "
            f"KZ66={kennzahlen.kz66}, KZ83={kennzahlen.kz83}"
        )

        # 6. Generate XML
        generator = UstvaXmlGenerator(
            settings=settings,
            year=year,
            period=period,
            kennzahlen=kennzahlen,
        )

        xml_bytes = generator.generate()
        filename = generator.suggested_filename

        logger.info(
            f"Generated ELSTER XML: {filename} ({len(xml_bytes)} bytes)"
        )

        return xml_bytes, filename

    async def _load_settings(self) -> UserSettings:
        """Load user settings from database.

        Returns:
            UserSettings model

        Raises:
            IncompleteSettingsError: If settings are incomplete for ELSTER
        """
        return await load_settings_async()

    def _validate_settings_for_elster(self, settings: UserSettings) -> None:
        """Validate settings have required fields for ELSTER.

        Args:
            settings: UserSettings to validate

        Raises:
            IncompleteSettingsError: If required fields are missing
        """
        missing_fields: list[str] = []

        if not settings.business_name:
            missing_fields.append("business_name")
        if not settings.tax_number:
            missing_fields.append("tax_number")
        if not settings.street:
            missing_fields.append("street")
        if not settings.zip_code:
            missing_fields.append("zip_code")
        if not settings.city:
            missing_fields.append("city")

        if missing_fields:
            raise IncompleteSettingsError(missing_fields)

    def _get_period_dates(
        self,
        year: int,
        period_type: ReportPeriodType,
        period_num: int,
    ) -> tuple[date, date]:
        """Calculate period start and end dates.

        Args:
            year: Tax year
            period_type: MONTH or QUARTER
            period_num: Period number (1-12 for month, 1-4 for quarter)

        Returns:
            Tuple of (start_date, end_date)
        """
        import calendar

        if period_type == ReportPeriodType.MONTH:
            month = max(1, min(12, period_num))
            start_date = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end_date = date(year, month, last_day)

        elif period_type == ReportPeriodType.QUARTER:
            quarter = max(1, min(4, period_num))
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            start_date = date(year, start_month, 1)
            last_day = calendar.monthrange(year, end_month)[1]
            end_date = date(year, end_month, last_day)

        else:  # YEAR
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)

        return start_date, end_date

    async def get_available_periods(self, year: int) -> list[dict]:
        """Get available periods for ELSTER export.

        Returns periods that have data (invoices or expenses).

        Args:
            year: Tax year

        Returns:
            List of period dicts with 'value' and 'label' keys
        """
        periods = []

        # Check each month
        for month in range(1, 13):
            start_date = date(year, month, 1)
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            end_date = date(year, month, last_day)

            # Check if there's any data
            invoices = await self.invoice_repo.get_by_period(start_date, end_date)
            expenses = await self.expense_repo.get_by_period(start_date, end_date)

            if invoices or expenses:
                period = f"{month:02d}/{year}"
                periods.append({
                    "value": period,
                    "label": period_to_display(period, "de"),
                    "has_data": True,
                })

        return periods
