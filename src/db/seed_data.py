"""Realistic German freelance mock data for development.

Contains sample data for a German software freelancer including:
- Expenses from typical vendors (Hetzner, JetBrains, Deutsche Bahn, etc.)
- Client invoices from major German companies
- Tax deadlines for USt-Voranmeldung and Einkommensteuer-Vorauszahlung
- Quarterly payment schedule
"""
from datetime import date, timedelta
from decimal import Decimal

from src.core.models import (
    DashboardStats,
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceStatus,
    QuarterlyPayment,
    TaxDeadline,
    VatRate,
)


def get_mock_expenses() -> list[Expense]:
    """Sample expenses for a German software freelancer."""
    today = date.today()
    return [
        Expense(
            id=1,
            date=today - timedelta(days=2),
            vendor="Hetzner Online GmbH",
            description="Cloud Server CX31 - Monatlich",
            amount_gross=Decimal("17.85"),
            vat_rate=VatRate.STANDARD,
            category=ExpenseCategory.SOFTWARE
        ),
        Expense(
            id=2,
            date=today - timedelta(days=5),
            vendor="JetBrains s.r.o.",
            description="PyCharm Professional - Jahreslizenz",
            amount_gross=Decimal("249.00"),
            vat_rate=VatRate.STANDARD,
            category=ExpenseCategory.SOFTWARE
        ),
        Expense(
            id=3,
            date=today - timedelta(days=8),
            vendor="Deutsche Bahn",
            description="ICE Frankfurt → Berlin, Kundentermin Zalando",
            amount_gross=Decimal("89.90"),
            vat_rate=VatRate.REDUCED,
            category=ExpenseCategory.REISE
        ),
        Expense(
            id=4,
            date=today - timedelta(days=12),
            vendor="Apple Germany",
            description="MacBook Pro M3 14\" - Betriebsausstattung",
            amount_gross=Decimal("2499.00"),
            vat_rate=VatRate.STANDARD,
            category=ExpenseCategory.HARDWARE
        ),
        Expense(
            id=5,
            date=today - timedelta(days=15),
            vendor="Telekom Deutschland",
            description="MagentaMobil Business L - Monatlich",
            amount_gross=Decimal("59.95"),
            vat_rate=VatRate.STANDARD,
            category=ExpenseCategory.KOMMUNIKATION
        ),
        Expense(
            id=6,
            date=today - timedelta(days=18),
            vendor="VIKING Direkt GmbH",
            description="Büromaterial: Notizbücher, Stifte, Ordner",
            amount_gross=Decimal("47.23"),
            vat_rate=VatRate.STANDARD,
            category=ExpenseCategory.BUERO
        ),
        Expense(
            id=7,
            date=today - timedelta(days=22),
            vendor="Udemy Business",
            description="Kubernetes Masterclass - Online-Kurs",
            amount_gross=Decimal("119.99"),
            vat_rate=VatRate.ZERO,  # Bildungsleistung
            category=ExpenseCategory.FORTBILDUNG
        ),
        Expense(
            id=8,
            date=today - timedelta(days=25),
            vendor="Allianz Versicherung",
            description="Berufshaftpflicht IT-Freelancer - Quartal",
            amount_gross=Decimal("187.50"),
            vat_rate=VatRate.ZERO,  # Versicherung
            category=ExpenseCategory.VERSICHERUNG
        ),
    ]


def get_mock_invoices() -> list[Invoice]:
    """Sample client invoices from international companies (0% VAT - Reverse Charge)."""
    today = date.today()
    year = today.year
    return [
        Invoice(
            id=1,
            client="Stripe Inc.",
            invoice_number=f"{year}-001",
            date=today - timedelta(days=45),
            due_date=today - timedelta(days=15),
            amount=Decimal("9500.00"),
            vat_rate=VatRate.ZERO,  # Reverse Charge - US client
            description="Payment API Integration - React Dashboard",
            status=InvoiceStatus.PAID,
            paid_date=today - timedelta(days=10)
        ),
        Invoice(
            id=2,
            client="Spotify AB",
            invoice_number=f"{year}-002",
            date=today - timedelta(days=30),
            due_date=today - timedelta(days=5),
            amount=Decimal("12000.00"),
            vat_rate=VatRate.ZERO,  # Reverse Charge - Sweden
            description="Backend Microservices - Audio Processing Pipeline",
            status=InvoiceStatus.OVERDUE
        ),
        Invoice(
            id=3,
            client="Automattic Inc.",
            invoice_number=f"{year}-003",
            date=today - timedelta(days=15),
            due_date=today + timedelta(days=15),
            amount=Decimal("7500.00"),
            vat_rate=VatRate.ZERO,  # Reverse Charge - US client
            description="WordPress Plugin Development - Custom Blocks",
            status=InvoiceStatus.PENDING
        ),
        Invoice(
            id=4,
            client="Klarna Bank AB",
            invoice_number=f"{year}-004",
            date=today - timedelta(days=7),
            due_date=today + timedelta(days=23),
            amount=Decimal("8500.00"),
            vat_rate=VatRate.ZERO,  # Reverse Charge - Sweden
            description="Checkout Flow Optimization - A/B Testing",
            status=InvoiceStatus.PENDING
        ),
        Invoice(
            id=5,
            client="Notion Labs Inc.",
            invoice_number=f"{year}-005",
            date=today - timedelta(days=3),
            due_date=today + timedelta(days=27),
            amount=Decimal("5500.00"),
            vat_rate=VatRate.ZERO,  # Reverse Charge - US client
            description="API Integration Consulting - 2 Wochen",
            status=InvoiceStatus.PENDING
        ),
    ]


def get_mock_tax_deadlines(year: int | None = None) -> list[TaxDeadline]:
    """Upcoming German tax deadlines (international clients = Nullmeldung USt).

    Args:
        year: Tax year (default: current year)
    """
    today = date.today()
    year = year or today.year

    month_names = [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]

    deadlines = []

    # Generate USt-Voranmeldung for each month (due 10th of following month)
    for month in range(1, 13):
        if month == 12:
            due_date = date(year + 1, 1, 10)
        else:
            due_date = date(year, month + 1, 10)

        deadlines.append(TaxDeadline(
            name=f"USt-Voranmeldung {month_names[month-1]}",
            type="umsatzsteuer",
            description="Nullmeldung - nur Reverse Charge Umsätze",
            date=due_date,
            days_until=0,
            amount=Decimal("0.00")
        ))

    # ESt-Vorauszahlung quarters (due March, June, September, December 10th)
    est_quarters = [(1, 3), (2, 6), (3, 9), (4, 12)]
    for quarter, month in est_quarters:
        deadlines.append(TaxDeadline(
            name=f"Einkommensteuer-Vorauszahlung Q{quarter}",
            type="einkommensteuer",
            description="Quartalszahlung gemäß Vorauszahlungsbescheid",
            date=date(year, month, 10),
            days_until=0,
            amount=Decimal("3500.00")
        ))

    # Zusammenfassende Meldung for each month (due 25th of following month)
    for month in range(1, 13):
        if month == 12:
            due_date = date(year + 1, 1, 25)
        else:
            due_date = date(year, month + 1, 25)

        deadlines.append(TaxDeadline(
            name=f"Zusammenfassende Meldung {month_names[month-1]}",
            type="umsatzsteuer",
            description="ZM für innergemeinschaftliche Leistungen (Reverse Charge)",
            date=due_date,
            days_until=0,
            amount=None
        ))

    # Calculate days_until dynamically
    for d in deadlines:
        d.days_until = (d.date - today).days

    # Sort by date and filter to upcoming (next 90 days)
    upcoming = sorted(
        [d for d in deadlines if 0 <= d.days_until <= 90],
        key=lambda x: x.date
    )
    return upcoming[:5]


def get_mock_quarterly_payments(year: int | None = None) -> list[QuarterlyPayment]:
    """Quarterly tax prepayments (§ 37 EStG).

    Args:
        year: Tax year (default: current year)
    """
    today = date.today()
    year = year or today.year

    # ESt quarterly due dates (March, June, September, December on the 10th)
    quarters = [
        (1, 3, 10),   # Q1: Due March 10
        (2, 6, 10),   # Q2: Due June 10
        (3, 9, 10),   # Q3: Due September 10
        (4, 12, 10),  # Q4: Due December 10
    ]

    payments = []
    for quarter, month, day in quarters:
        due_date = date(year, month, day)
        is_past = due_date < today

        payments.append(QuarterlyPayment(
            quarter=quarter,
            year=year,
            due_date=due_date,
            amount=Decimal("3500.00"),
            paid=is_past,
            days_until=None if is_past else (due_date - today).days,
        ))

    return payments


def get_mock_dashboard_stats() -> DashboardStats:
    """Dashboard summary statistics for international clients (0% VAT)."""
    return DashboardStats(
        total_revenue=Decimal("43000.00"),   # Sum of invoices (international)
        total_expenses=Decimal("3270.42"),    # Sum of expenses
        vat_collected=Decimal("0.00"),        # 0€ - All Reverse Charge
        estimated_tax=Decimal("12500.00"),    # ~30% estimated income tax
        revenue_change=Decimal("15.2"),       # +15.2% vs last month
        expense_change=Decimal("-8.3"),       # -8.3% vs last month (good!)
        tax_rate=Decimal("29.1"),             # Effective tax rate
        next_ust_date="10.02.2026"            # USt still due (Nullmeldung)
    )


def get_mock_income_prediction() -> dict:
    """Income prediction data for D3 chart (international clients)."""
    return {
        "labels": ["Aug", "Sep", "Okt", "Nov", "Dez", "Jan", "Feb", "Mär", "Apr", "Mai"],
        "actual": [8500, 9800, 8200, 12000, 10500, 9500, None, None, None, None],
        "predicted": [8500, 9800, 8200, 12000, 10500, 9500, 10200, 11500, 10800, 12000]
    }
