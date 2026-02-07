"""German Tax Deadline Calculator.

Generates dynamic tax filing deadlines including:
- USt-Voranmeldung (monthly/quarterly/annual)
- Einkommensteuer-Vorauszahlung (quarterly)
- Zusammenfassende Meldung (EU services)
- Annual tax return

All dates follow German tax calendar rules.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from src.core.models import QuarterlyPayment, TaxDeadline
from src.core.tax.umsatzsteuer import UstFrequency


class DeadlineType(StrEnum):
    """Types of tax deadlines."""
    UMSATZSTEUER = "umsatzsteuer"
    EINKOMMENSTEUER = "einkommensteuer"
    GEWERBESTEUER = "gewerbesteuer"
    ZM = "zusammenfassende_meldung"
    ANNUAL_RETURN = "steuererklaerung"


@dataclass
class DeadlineConfig:
    """Configuration for deadline generation."""
    ust_frequency: UstFrequency = UstFrequency.MONTHLY
    quarterly_payment_amount: Decimal = Decimal("0")
    is_freiberufler: bool = True  # Exempt from Gewerbesteuer
    has_eu_clients: bool = False  # Requires Zusammenfassende Meldung


class DeadlineCalculator:
    """Calculator for German tax filing deadlines.

    Generates upcoming deadlines based on current date and configuration.

    Usage:
        calc = DeadlineCalculator()
        deadlines = calc.get_upcoming_deadlines(
            year=2026,
            config=DeadlineConfig(ust_frequency=UstFrequency.MONTHLY)
        )
    """

    # USt-Voranmeldung due on 10th of following month
    UST_DUE_DAY = 10

    # Zusammenfassende Meldung due on 25th of following month
    ZM_DUE_DAY = 25

    # ESt quarterly due dates (March, June, September, December)
    EST_QUARTERS = [
        (1, 3, 10),   # Q1: Due March 10
        (2, 6, 10),   # Q2: Due June 10
        (3, 9, 10),   # Q3: Due September 10
        (4, 12, 10),  # Q4: Due December 10
    ]

    def __init__(self, reference_date: date | None = None):
        """Initialize calculator.

        Args:
            reference_date: Date to calculate from (default: today)
        """
        self.reference_date = reference_date or date.today()

    def get_upcoming_deadlines(
        self,
        year: int,
        config: DeadlineConfig,
        lookahead_days: int = 90,
    ) -> list[TaxDeadline]:
        """Get all upcoming tax deadlines within lookahead period.

        Args:
            year: Tax year
            config: Deadline configuration
            lookahead_days: How many days ahead to look

        Returns:
            List of upcoming TaxDeadline objects, sorted by date
        """
        deadlines: list[TaxDeadline] = []
        end_date = self.reference_date + timedelta(days=lookahead_days)

        # USt-Voranmeldung deadlines
        deadlines.extend(
            self._get_ust_deadlines(year, config.ust_frequency, end_date)
        )

        # ESt-Vorauszahlung deadlines
        deadlines.extend(
            self._get_est_deadlines(year, config.quarterly_payment_amount, end_date)
        )

        # Zusammenfassende Meldung (if has EU clients)
        if config.has_eu_clients:
            deadlines.extend(
                self._get_zm_deadlines(year, config.ust_frequency, end_date)
            )

        # Gewerbesteuer (only if not Freiberufler)
        if not config.is_freiberufler:
            deadlines.extend(
                self._get_gew_deadlines(year, end_date)
            )

        # Filter to only upcoming and sort
        upcoming = [
            d for d in deadlines
            if d.date >= self.reference_date and d.date <= end_date
        ]

        # Update days_until
        for d in upcoming:
            d.days_until = (d.date - self.reference_date).days

        return sorted(upcoming, key=lambda x: x.date)

    def _get_ust_deadlines(
        self,
        year: int,
        frequency: UstFrequency,
        end_date: date,
    ) -> list[TaxDeadline]:
        """Generate USt-Voranmeldung deadlines.

        Monthly: Due 10th of following month
        Quarterly: Due 10th of month following quarter end
        Annual: Due with annual tax return

        Args:
            year: Tax year
            frequency: Filing frequency
            end_date: Latest deadline to include

        Returns:
            List of USt deadlines
        """
        deadlines = []

        if frequency == UstFrequency.MONTHLY:
            # Monthly deadlines
            for month in range(1, 13):
                # Due on 10th of following month
                if month == 12:
                    due = date(year + 1, 1, self.UST_DUE_DAY)
                else:
                    due = date(year, month + 1, self.UST_DUE_DAY)

                if due > end_date:
                    break

                month_names = [
                    "Januar", "Februar", "März", "April", "Mai", "Juni",
                    "Juli", "August", "September", "Oktober", "November", "Dezember"
                ]

                deadlines.append(TaxDeadline(
                    name=f"USt-Voranmeldung {month_names[month-1]}",
                    type=DeadlineType.UMSATZSTEUER,
                    description=f"Umsatzsteuer-Voranmeldung für {month_names[month-1]} {year}",
                    date=due,
                    days_until=0,
                    amount=Decimal("0"),  # Calculated separately
                    deadline_id=f"ust_{year}_{month:02d}",
                ))

        elif frequency == UstFrequency.QUARTERLY:
            # Quarterly deadlines
            quarter_due_months = [
                (1, 4),   # Q1: Due April 10
                (2, 7),   # Q2: Due July 10
                (3, 10),  # Q3: Due October 10
                (4, 1),   # Q4: Due January 10 (next year)
            ]

            for quarter, due_month in quarter_due_months:
                if quarter == 4:
                    due = date(year + 1, due_month, self.UST_DUE_DAY)
                else:
                    due = date(year, due_month, self.UST_DUE_DAY)

                if due > end_date:
                    break

                deadlines.append(TaxDeadline(
                    name=f"USt-Voranmeldung Q{quarter}",
                    type=DeadlineType.UMSATZSTEUER,
                    description=f"Umsatzsteuer-Voranmeldung für Q{quarter}/{year}",
                    date=due,
                    days_until=0,
                    amount=Decimal("0"),
                    deadline_id=f"ust_{year}_q{quarter}",
                ))

        # Annual frequency: no Voranmeldung deadlines

        return deadlines

    def _get_est_deadlines(
        self,
        year: int,
        amount: Decimal,
        end_date: date,
    ) -> list[TaxDeadline]:
        """Generate Einkommensteuer-Vorauszahlung deadlines.

        § 37 EStG: Due on 10. März, 10. Juni, 10. September, 10. Dezember

        Args:
            year: Tax year
            amount: Quarterly payment amount
            end_date: Latest deadline to include

        Returns:
            List of ESt deadlines
        """
        deadlines = []
        quarter_names = ["Q1", "Q2", "Q3", "Q4"]

        for quarter, month, day in self.EST_QUARTERS:
            due = date(year, month, day)

            if due > end_date:
                break

            deadlines.append(TaxDeadline(
                name=f"Einkommensteuer-Vorauszahlung {quarter_names[quarter-1]}",
                type=DeadlineType.EINKOMMENSTEUER,
                description=f"Quartalszahlung {quarter_names[quarter-1]} gemäß Vorauszahlungsbescheid",
                date=due,
                days_until=0,
                amount=amount if amount > 0 else None,
                deadline_id=f"est_{year}_q{quarter}",
            ))

        return deadlines

    def _get_zm_deadlines(
        self,
        year: int,
        frequency: UstFrequency,
        end_date: date,
    ) -> list[TaxDeadline]:
        """Generate Zusammenfassende Meldung deadlines.

        Due on 25th of following month for EU B2B services.
        Frequency matches USt-Voranmeldung frequency.

        Args:
            year: Tax year
            frequency: Filing frequency (matches USt)
            end_date: Latest deadline to include

        Returns:
            List of ZM deadlines
        """
        deadlines = []

        if frequency == UstFrequency.MONTHLY:
            for month in range(1, 13):
                if month == 12:
                    due = date(year + 1, 1, self.ZM_DUE_DAY)
                else:
                    due = date(year, month + 1, self.ZM_DUE_DAY)

                if due > end_date:
                    break

                month_names = [
                    "Januar", "Februar", "März", "April", "Mai", "Juni",
                    "Juli", "August", "September", "Oktober", "November", "Dezember"
                ]

                deadlines.append(TaxDeadline(
                    name=f"Zusammenfassende Meldung {month_names[month-1]}",
                    type=DeadlineType.ZM,
                    description=f"ZM für innergemeinschaftliche Leistungen {month_names[month-1]}",
                    date=due,
                    days_until=0,
                    amount=None,  # Reporting only
                    deadline_id=f"zm_{year}_{month:02d}",
                ))

        elif frequency == UstFrequency.QUARTERLY:
            quarter_due_months = [(1, 4), (2, 7), (3, 10), (4, 1)]

            for quarter, due_month in quarter_due_months:
                if quarter == 4:
                    due = date(year + 1, due_month, self.ZM_DUE_DAY)
                else:
                    due = date(year, due_month, self.ZM_DUE_DAY)

                if due > end_date:
                    break

                deadlines.append(TaxDeadline(
                    name=f"Zusammenfassende Meldung Q{quarter}",
                    type=DeadlineType.ZM,
                    description=f"ZM für innergemeinschaftliche Leistungen Q{quarter}",
                    date=due,
                    days_until=0,
                    amount=None,
                    deadline_id=f"zm_{year}_q{quarter}",
                ))

        return deadlines

    def _get_gew_deadlines(
        self,
        year: int,
        end_date: date,
    ) -> list[TaxDeadline]:
        """Generate Gewerbesteuer-Vorauszahlung deadlines.

        Due quarterly: 15. Februar, 15. Mai, 15. August, 15. November

        Note: Freiberufler (§ 18 EStG) are exempt!

        Args:
            year: Tax year
            end_date: Latest deadline to include

        Returns:
            List of Gewerbesteuer deadlines
        """
        deadlines = []
        gew_dates = [
            (1, 2, 15),   # Q1: February 15
            (2, 5, 15),   # Q2: May 15
            (3, 8, 15),   # Q3: August 15
            (4, 11, 15),  # Q4: November 15
        ]

        for quarter, month, day in gew_dates:
            due = date(year, month, day)

            if due > end_date:
                break

            deadlines.append(TaxDeadline(
                name=f"Gewerbesteuer-Vorauszahlung Q{quarter}",
                type=DeadlineType.GEWERBESTEUER,
                description=f"Vierteljährliche Gewerbesteuerzahlung Q{quarter}",
                date=due,
                days_until=0,
                amount=None,  # Depends on Hebesatz and profit
                deadline_id=f"gew_{year}_q{quarter}",
            ))

        return deadlines

    def get_quarterly_payments(
        self,
        year: int,
        amount_per_quarter: Decimal,
    ) -> list[QuarterlyPayment]:
        """Generate quarterly payment schedule for Einkommensteuer.

        § 37 EStG - Quarterly prepayments

        Args:
            year: Tax year
            amount_per_quarter: Amount per quarter

        Returns:
            List of QuarterlyPayment objects
        """
        payments = []

        for quarter, month, day in self.EST_QUARTERS:
            due = date(year, month, day)
            is_past = due < self.reference_date

            payments.append(QuarterlyPayment(
                quarter=quarter,
                year=year,
                due_date=due,
                amount=amount_per_quarter,
                paid=is_past,  # Assume past payments are paid
                days_until=None if is_past else (due - self.reference_date).days,
            ))

        return payments

    def get_next_deadline(
        self,
        year: int,
        config: DeadlineConfig,
    ) -> TaxDeadline | None:
        """Get the next upcoming deadline.

        Args:
            year: Tax year
            config: Deadline configuration

        Returns:
            Next TaxDeadline or None if no upcoming deadlines
        """
        deadlines = self.get_upcoming_deadlines(year, config, lookahead_days=365)
        return deadlines[0] if deadlines else None

    def get_annual_return_deadline(
        self,
        year: int,
        has_steuerberater: bool = False,
    ) -> TaxDeadline:
        """Get annual tax return (Steuererklärung) deadline.

        Without Steuerberater: 31. Juli of following year
        With Steuerberater: End of February (28/29) of year after following year

        Args:
            year: Tax year for the return
            has_steuerberater: Has tax advisor preparing return

        Returns:
            TaxDeadline for annual return
        """
        if has_steuerberater:
            # Deadline extended to end of Feb, year+2
            # Check for leap year
            target_year = year + 2
            is_leap = (target_year % 4 == 0 and
                      (target_year % 100 != 0 or target_year % 400 == 0))
            due = date(target_year, 2, 29 if is_leap else 28)
            description = f"Steuererklärung {year} (mit Steuerberater)"
        else:
            due = date(year + 1, 7, 31)
            description = f"Steuererklärung {year}"

        return TaxDeadline(
            name=f"Steuererklärung {year}",
            type=DeadlineType.ANNUAL_RETURN,
            description=description,
            date=due,
            days_until=(due - self.reference_date).days,
            amount=None,
        )


def get_upcoming_deadlines(
    year: int = 2026,
    ust_frequency: UstFrequency = UstFrequency.MONTHLY,
    quarterly_amount: Decimal = Decimal("0"),
    has_eu_clients: bool = True,
    is_freiberufler: bool = True,
    lookahead_days: int = 90,
) -> list[TaxDeadline]:
    """Convenience function for getting upcoming deadlines.

    Args:
        year: Tax year
        ust_frequency: USt filing frequency
        quarterly_amount: ESt quarterly payment amount
        has_eu_clients: Whether ZM is required
        is_freiberufler: Whether exempt from Gewerbesteuer
        lookahead_days: How many days ahead to look

    Returns:
        List of upcoming TaxDeadline objects
    """
    calc = DeadlineCalculator()
    config = DeadlineConfig(
        ust_frequency=ust_frequency,
        quarterly_payment_amount=quarterly_amount,
        is_freiberufler=is_freiberufler,
        has_eu_clients=has_eu_clients,
    )
    return calc.get_upcoming_deadlines(year, config, lookahead_days)
