"""Page routes for full-page views (Ausgaben, Rechnungen, Kunden, Steuern, Berichte).

These routes serve full HTML pages extending base.html.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import CoverageType, ExpenseCategory, InsuranceType
from src.web.models.reports import ReportPeriodType
from src.web.routes.settings import get_current_language, get_tax_year, load_settings
from src.web.services.client import ClientService, get_client_service
from src.web.services.dashboard import DashboardService, get_dashboard_service
from src.web.services.expense import ExpenseService, get_expense_service
from src.web.services.health_insurance import (
    HealthInsuranceService,
    get_health_insurance_service,
)
from src.web.services.invoice import InvoiceService, get_invoice_service
from src.web.services.report import ReportService, get_report_service

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


# =============================================================================
# Expenses Page (/ausgaben)
# =============================================================================


@router.get("/ausgaben", response_class=HTMLResponse)
async def expenses_page(
    request: Request,
    expense_service: ExpenseService = Depends(get_expense_service),
) -> HTMLResponse:
    """Render full expenses management page."""
    today = date.today()
    current_year = get_tax_year()  # Use selected tax year from settings

    expenses = await expense_service.get_expenses(year=current_year)
    category_breakdown_raw = await expense_service.get_category_breakdown(current_year)
    monthly_expenses_raw = await expense_service.get_monthly_totals(current_year)
    # Convert to JSON-serializable format
    category_breakdown = {k.value: float(v) for k, v in category_breakdown_raw.items()}
    monthly_expenses = {k: float(v[0]) for k, v in monthly_expenses_raw.items()}

    # Filter expenses for current year
    year_expenses = [e for e in expenses if e.date.year == current_year]

    # Calculate stats
    total_gross = sum(e.amount_gross for e in year_expenses)
    total_net = sum(e.amount_net for e in year_expenses)
    total_vat = sum(e.vat_amount for e in year_expenses)
    this_month_expenses = [e for e in year_expenses if e.date.month == today.month]
    this_month = len(this_month_expenses)
    this_month_total = sum(e.amount_gross for e in this_month_expenses)

    # Calculate top vendors
    vendor_totals: dict[str, Decimal] = {}
    for exp in year_expenses:
        vendor_totals[exp.vendor] = vendor_totals.get(exp.vendor, Decimal("0")) + exp.amount_gross

    top_vendors = [
        {"name": name, "total": total}
        for name, total in sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    # Get i18n context
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "pages/expenses.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "current_year": current_year,
            "today": today,
            "expenses": year_expenses,
            "categories": list(ExpenseCategory),
            "stats": {
                "total_gross": total_gross,
                "total_net": total_net,
                "total_vat": total_vat,
                "count": len(year_expenses),
                "this_month": this_month,
                "this_month_total": this_month_total,
            },
            "category_breakdown": category_breakdown,
            "monthly_expenses": monthly_expenses,
            "top_vendors": top_vendors,
        },
    )


# =============================================================================
# Invoices Page (/rechnungen)
# =============================================================================


@router.get("/rechnungen", response_class=HTMLResponse)
async def invoices_page(
    request: Request,
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Render full invoices management page."""
    today = date.today()
    current_year = get_tax_year()  # Use selected tax year from settings

    invoices = await invoice_service.get_invoices()
    client_revenue_raw = await invoice_service.get_client_summary(current_year)
    monthly_revenue_raw = await invoice_service.get_monthly_revenue(current_year)
    # Convert to JSON-serializable format
    client_revenue = {k: float(v) for k, v in client_revenue_raw.items()}
    monthly_revenue = {k: float(v) for k, v in monthly_revenue_raw.items()}

    # Filter invoices for current year (for stats only)
    year_invoices = [i for i in invoices if i.date.year == current_year]

    # Calculate stats (current year only)
    total_revenue = sum(i.amount for i in year_invoices)
    outstanding = sum(i.amount for i in year_invoices if i.status.value == "pending")
    overdue_amount = sum(i.amount for i in year_invoices if i.status.value == "overdue")

    pending_count = len([i for i in year_invoices if i.status.value == "pending"])
    paid_count = len([i for i in year_invoices if i.status.value == "paid"])
    overdue_count = len([i for i in year_invoices if i.status.value == "overdue"])

    this_month = sum(
        i.amount for i in year_invoices if i.date.month == today.month
    )
    this_month_count = len(
        [i for i in year_invoices if i.date.month == today.month]
    )

    # VAT summary
    reverse_charge = sum(
        float(i.amount_net) for i in year_invoices if i.vat_rate.value == "0.00"
    )
    standard = sum(
        float(i.amount_net) for i in year_invoices if i.vat_rate.value == "0.19"
    )
    reduced = sum(
        float(i.amount_net) for i in year_invoices if i.vat_rate.value == "0.07"
    )
    total_vat = sum(float(i.vat_amount) for i in year_invoices)

    # Get i18n context
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "pages/invoices.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "current_year": current_year,
            "invoices": invoices,  # Show all invoices, not just current year
            "stats": {
                "total_revenue": total_revenue,
                "outstanding": outstanding,
                "overdue_amount": overdue_amount,
                "invoice_count": len(year_invoices),
                "pending_count": pending_count,
                "paid_count": paid_count,
                "overdue_count": overdue_count,
                "this_month": this_month,
                "this_month_count": this_month_count,
            },
            "client_revenue": client_revenue,
            "monthly_revenue": monthly_revenue,
            "vat_summary": {
                "reverse_charge": reverse_charge,
                "standard": standard,
                "reduced": reduced,
                "total_vat": total_vat,
            },
        },
    )


# =============================================================================
# Clients Page (/kunden)
# =============================================================================


@router.get("/kunden", response_class=HTMLResponse)
async def clients_page(
    request: Request,
    year: int | None = Query(default=None, description="Filter by year"),
    client_service: ClientService = Depends(get_client_service),
) -> HTMLResponse:
    """Render full clients management page with Scheinselbständigkeit detection.

    Shows all clients with their invoice statistics and income distribution.
    Displays warnings when income concentration from a single client exceeds
    the 83% threshold per German tax authority guidelines (§ 7 SGB IV).
    """
    current_year = year or get_tax_year()  # Use selected tax year from settings

    distribution = await client_service.get_income_distribution(year=current_year)

    # Calculate summary stats
    total_clients = len(distribution.client_breakdown)
    total_invoiced = sum(c.total_invoiced for c in distribution.client_breakdown)
    total_paid = sum(c.total_paid for c in distribution.client_breakdown)
    total_outstanding = sum(c.outstanding for c in distribution.client_breakdown)

    # Top clients for card display (sorted by income %)
    top_clients = distribution.client_breakdown[:5]

    # Available years for filter (current year +/- 2)
    available_years = list(range(current_year - 2, current_year + 2))

    # Get i18n context
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "pages/clients.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "current_year": current_year,
            "selected_year": current_year,
            "available_years": available_years,
            "distribution": distribution,
            "clients": distribution.client_breakdown,
            "top_clients": top_clients,
            "stats": {
                "total_clients": total_clients,
                "clients_at_risk": distribution.clients_at_risk,
                "total_invoiced": total_invoiced,
                "total_paid": total_paid,
                "total_outstanding": total_outstanding,
                "max_concentration": distribution.max_concentration,
                "scheinselbstaendig_warning": distribution.scheinselbstaendig_warning,
            },
        },
    )


# =============================================================================
# Tax Overview Page (/steuern)
# =============================================================================


@router.get("/steuern", response_class=HTMLResponse)
async def taxes_page(
    request: Request,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    expense_service: ExpenseService = Depends(get_expense_service),
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Render full tax overview page."""
    today = date.today()
    current_year = get_tax_year()  # Use selected tax year from settings
    settings = load_settings()

    tax_estimate = await dashboard_service.get_tax_estimate(current_year)
    deadlines = await dashboard_service.get_upcoming_deadlines(year=current_year, lookahead_days=90)
    quarterly_payments = await dashboard_service.get_quarterly_payments(current_year)

    # Calculate total quarterly payments
    total_quarterly = sum(p.amount for p in quarterly_payments)
    paid_quarterly = sum(p.amount for p in quarterly_payments if p.paid)

    # Calculate remaining income tax due with annual return
    # This is the difference between estimated ESt and what's been paid as prepayments
    remaining_income_tax = max(tax_estimate.einkommensteuer - paid_quarterly, Decimal("0"))

    # Find next deadline
    next_deadline = None
    for d in deadlines:
        if d.days_until >= 0:
            next_deadline = d
            break

    # Calculate current USt period based on settings (monthly or quarterly)
    ust_frequency = settings.ust_frequency  # "monthly" or "quarterly"

    if ust_frequency == "quarterly":
        # Quarterly: Q1 = Jan-Mar, Q2 = Apr-Jun, Q3 = Jul-Sep, Q4 = Oct-Dec
        quarter = (today.month - 1) // 3 + 1
        quarter_start_month = (quarter - 1) * 3 + 1
        period_start = date(today.year, quarter_start_month, 1)
        if quarter == 4:
            period_end = date(today.year, 12, 31)
        else:
            period_end = date(today.year, quarter_start_month + 3, 1) - timedelta(days=1)
        current_period = f"Q{quarter} {today.year}"
    else:
        # Monthly (default)
        period_start = date(today.year, today.month, 1)
        # End of month
        if today.month == 12:
            period_end = date(today.year, 12, 31)
        else:
            period_end = date(today.year, today.month + 1, 1) - timedelta(days=1)
        current_period = today.strftime("%B %Y")

    # Calculate real USt summary for current period
    # Get invoices for period - sum VAT collected
    period_invoices = await invoice_service.get_invoices_by_period(period_start, period_end)
    ust_collected = sum(inv.vat_amount for inv in period_invoices)

    # Get expenses for period - sum Vorsteuer (input VAT)
    period_expenses = await expense_service.get_expenses_by_period(period_start, period_end)
    vorsteuer = sum(exp.vat_amount for exp in period_expenses)

    # Calculate Zahllast (tax liability = collected - vorsteuer)
    zahllast = ust_collected - vorsteuer

    ust_summary = {
        "collected": ust_collected,
        "vorsteuer": vorsteuer,
        "zahllast": zahllast,
    }

    # EÜR preview
    eur_preview = {
        "einnahmen": tax_estimate.estimated_income,
        "ausgaben": tax_estimate.estimated_expenses,
        "gewinn": tax_estimate.taxable_income,
    }

    # Get i18n context
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "pages/taxes.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "current_year": current_year,
            "today": today,
            "tax_estimate": tax_estimate,
            "deadlines": deadlines,
            "quarterly_payments": quarterly_payments,
            "total_quarterly": total_quarterly,
            "paid_quarterly": paid_quarterly,
            "remaining_income_tax": remaining_income_tax,
            "next_deadline": next_deadline,
            "current_period": current_period,
            "ust_summary": ust_summary,
            "eur_preview": eur_preview,
        },
    )


# =============================================================================
# Reports Page (/berichte)
# =============================================================================


@router.get("/berichte", response_class=HTMLResponse)
async def reports_page(
    request: Request,
    year: int | None = Query(default=None),
    period_type: str = Query(default="quarter"),
    period_num: int | None = Query(default=None),
    report_service: ReportService = Depends(get_report_service),
) -> HTMLResponse:
    """Render reports and exports page with real aggregated data."""
    current_year = year or get_tax_year()
    lang = get_current_language()
    _ = get_translator(lang)

    # Determine current period number if not specified
    today = date.today()
    if period_num is None:
        if period_type == "month":
            period_num = today.month
        elif period_type == "quarter":
            period_num = (today.month - 1) // 3 + 1
        else:
            period_num = 1

    # Get data for each report type using ReportService
    ust_data = await report_service.get_ust_voranmeldung(
        current_year, ReportPeriodType(period_type), period_num, lang
    )
    zsm_data = await report_service.get_zsm(
        current_year, (period_num - 1) // 3 + 1 if period_type == "month" else period_num, lang
    )
    eur_data = await report_service.get_eur(current_year)
    annual_data = await report_service.get_annual_overview(current_year)

    # Recent exports (mock for now - would be from database)
    recent_exports = [
        {
            "name": _("report.ust_voranmeldung") if _ else "USt-Voranmeldung",
            "period": f"{_('report.december') if _ else 'Dezember'} {current_year - 1}",
            "created": datetime(current_year, 1, 5, 14, 30),
            "format": "PDF",
        },
        {
            "name": _("report.eur") if _ else "EÜR",
            "period": f"Q4 {current_year - 1}",
            "created": datetime(current_year, 1, 3, 10, 15),
            "format": "CSV",
        },
        {
            "name": _("report.zsm") if _ else "Zusammenfassende Meldung",
            "period": f"Q4 {current_year - 1}",
            "created": datetime(current_year, 1, 2, 9, 0),
            "format": "PDF",
        },
    ]

    return templates.TemplateResponse(
        "pages/reports.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "current_year": current_year,
            "period_type": period_type,
            "period_num": period_num,
            "ust_data": ust_data,
            "zsm_data": zsm_data,
            "eur_data": eur_data,
            "annual_data": annual_data,
            "recent_exports": recent_exports,
        },
    )


# =============================================================================
# Report Preview Endpoints (HTMX partials)
# =============================================================================


@router.get("/berichte/ust-voranmeldung/preview", response_class=HTMLResponse)
async def ust_preview(
    request: Request,
    year: int | None = Query(default=None),
    period_type: str = Query(default="month"),
    period_num: int | None = Query(default=None),
    report_service: ReportService = Depends(get_report_service),
) -> HTMLResponse:
    """Return USt-Voranmeldung preview HTML with real data."""
    current_year = year or get_tax_year()
    lang = get_current_language()
    _ = get_translator(lang)

    # Default to current month if not specified
    if period_num is None:
        period_num = date.today().month

    data = await report_service.get_ust_voranmeldung(
        current_year, ReportPeriodType(period_type), period_num, lang
    )

    return templates.TemplateResponse(
        "partials/_ust_preview.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "data": data,
        },
    )


@router.get("/berichte/zsm/preview", response_class=HTMLResponse)
async def zsm_preview(
    request: Request,
    year: int | None = Query(default=None),
    period_type: str = Query(default="quarter"),
    period_num: int | None = Query(default=None),
    report_service: ReportService = Depends(get_report_service),
) -> HTMLResponse:
    """Return Zusammenfassende Meldung preview HTML with real data."""
    current_year = year or get_tax_year()
    lang = get_current_language()
    _ = get_translator(lang)

    # ZSM is quarterly - convert period_num to quarter
    if period_num is None:
        quarter = (date.today().month - 1) // 3 + 1
    elif period_type == "month":
        # If month selected, use the quarter containing that month
        quarter = (period_num - 1) // 3 + 1
    else:
        quarter = period_num

    data = await report_service.get_zsm(current_year, quarter, lang)

    return templates.TemplateResponse(
        "partials/_zsm_preview.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "data": data,
        },
    )


@router.get("/berichte/eur/preview", response_class=HTMLResponse)
async def eur_preview(
    request: Request,
    year: int | None = Query(default=None),
    report_service: ReportService = Depends(get_report_service),
) -> HTMLResponse:
    """Return EÜR preview HTML with real data."""
    current_year = year or get_tax_year()
    lang = get_current_language()
    _ = get_translator(lang)

    data = await report_service.get_eur(current_year)

    return templates.TemplateResponse(
        "partials/_eur_preview.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "data": data,
        },
    )


@router.get("/berichte/jahresuebersicht/preview", response_class=HTMLResponse)
async def annual_preview(
    request: Request,
    year: int | None = Query(default=None),
    report_service: ReportService = Depends(get_report_service),
) -> HTMLResponse:
    """Return Jahresübersicht preview HTML with real data."""
    current_year = year or get_tax_year()
    lang = get_current_language()
    _ = get_translator(lang)

    data = await report_service.get_annual_overview(current_year)

    return templates.TemplateResponse(
        "partials/_annual_preview.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "data": data,
        },
    )


# =============================================================================
# Health Insurance Page (/krankenversicherung)
# =============================================================================


@router.get("/krankenversicherung", response_class=HTMLResponse)
async def health_insurance_page(
    request: Request,
    health_insurance_service: HealthInsuranceService = Depends(
        get_health_insurance_service
    ),
) -> HTMLResponse:
    """Render full health insurance management page.

    Shows health insurance payments with tax deduction calculations
    per § 10 EStG (Vorsorgeaufwendungen/Sonderausgaben).
    """
    today = date.today()
    current_year = get_tax_year()

    # Get all payments for current year
    payments = await health_insurance_service.get_health_insurances(year=current_year)

    # Get summary and deduction details
    summary = await health_insurance_service.get_summary(current_year)
    deduction = await health_insurance_service.get_deduction(current_year)

    # Get all providers for the form
    providers = await health_insurance_service.get_providers()

    # Get coverage breakdown for chart
    coverage_breakdown = await health_insurance_service.get_coverage_breakdown(
        current_year
    )
    # Convert to JSON-serializable format
    coverage_data = {
        k.value: float(v["total_paid"]) for k, v in coverage_breakdown.items()
    }

    # Calculate this month's payments
    this_month_payments = [p for p in payments if p.date.month == today.month]
    this_month_total = sum(p.amount for p in this_month_payments)

    # Get i18n context
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "pages/health_insurance.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "current_year": current_year,
            "today": today,
            "payments": payments,
            "summary": summary,
            "deduction": deduction,
            "providers": providers,
            "coverage_data": coverage_data,
            "stats": {
                "total_paid": summary.total_paid,
                "total_deductible": summary.total_deductible,
                "wahlleistungen_total": summary.wahlleistungen_total,
                "wahlleistungen_deductible": summary.wahlleistungen_deductible,
                "remaining_limit": summary.remaining_limit,
                "payment_count": summary.payment_count,
                "this_month_total": this_month_total,
                "this_month_count": len(this_month_payments),
            },
        },
    )
