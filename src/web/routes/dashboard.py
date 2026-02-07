"""Dashboard routes with service layer integration."""
import logging
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.db.seed_data import (
    get_mock_dashboard_stats,
    get_mock_expenses,
    get_mock_income_prediction,
    get_mock_invoices,
    get_mock_quarterly_payments,
    get_mock_tax_deadlines,
)
from src.web.routes.settings import get_current_language, get_tax_year, load_settings
from src.web.services.dashboard import DashboardService, get_dashboard_service
from src.web.services.expense import ExpenseService, get_expense_service
from src.web.services.invoice import InvoiceService, get_invoice_service

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    expense_service: ExpenseService = Depends(get_expense_service),
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Render main dashboard with all widgets.

    Uses service layer for data aggregation and tax calculations.
    Falls back to mock data when database is not initialized.
    """
    today = date.today()
    current_year = get_tax_year()  # Use selected tax year from settings

    try:
        stats = await dashboard_service.get_dashboard_stats(current_year)
        expenses = await expense_service.get_recent_expenses(limit=8)
        invoices = await invoice_service.get_recent_invoices(limit=5)
        all_deadlines = await dashboard_service.get_upcoming_deadlines(year=current_year, lookahead_days=90)
        # Filter out einkommensteuer prepayments - they're shown in the Quarterly Payments widget
        deadlines = [d for d in all_deadlines if d.type != "einkommensteuer"]
        quarterly_payments = await dashboard_service.get_quarterly_payments(current_year)
        chart_data = await dashboard_service.get_income_prediction(year=current_year)
        tax_estimate = await dashboard_service.get_tax_estimate(current_year)

        # Tax optimization widgets
        afa_summary = await dashboard_service.get_afa_summary(current_year)
        travel_summary = await dashboard_service.get_travel_summary(current_year)
        gift_warnings = await dashboard_service.get_gift_warnings(current_year)
        homeoffice_summary = await dashboard_service.get_homeoffice_summary(current_year)
    except (OSError, ValueError) as e:
        # Fallback to mock data on database/service error
        logger.warning(f"Database error, using mock data: {e}")
        stats = get_mock_dashboard_stats()
        expenses = get_mock_expenses()
        invoices = get_mock_invoices()
        deadlines = get_mock_tax_deadlines()
        quarterly_payments = get_mock_quarterly_payments()
        chart_data = get_mock_income_prediction()
        tax_estimate = None

        # Empty tax optimization widgets on error
        afa_summary = {"total_depreciation": 0, "active_asset_count": 0, "expiring_count": 0}
        travel_summary = {"per_diem_total": 0, "km_total": 0, "total_deduction": 0, "trip_count": 0}
        gift_warnings = {"at_risk_count": 0, "over_limit_count": 0, "recipient_count": 0}
        homeoffice_summary = {"days_used": 0, "max_days": 210, "deduction_amount": 0, "percentage": 0}

    # Calculate total and paid quarterly payments
    total_quarterly = sum(p.amount for p in quarterly_payments)
    paid_quarterly = sum(p.amount for p in quarterly_payments if p.paid)

    # Calculate remaining income tax due with annual return
    from decimal import Decimal
    if tax_estimate:
        remaining_income_tax = max(tax_estimate.einkommensteuer - paid_quarterly, Decimal("0"))
    else:
        remaining_income_tax = Decimal("0")

    # Get i18n context and user settings
    settings = load_settings()
    lang = settings.language
    _ = get_translator(lang)

    # Extract first name from business_name (e.g., "Max Mustermann Consulting" -> "Max")
    user_name = settings.business_name.split()[0] if settings.business_name else "Freelancer"

    return templates.TemplateResponse(
        "pages/dashboard.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "user_name": user_name,
            "current_year": current_year,
            "today": today,
            "stats": stats,
            "expenses": expenses,
            "invoices": invoices,
            "deadlines": deadlines,
            "quarterly_payments": quarterly_payments,
            "total_quarterly": total_quarterly,
            "paid_quarterly": paid_quarterly,
            "tax_estimate": tax_estimate,
            "remaining_income_tax": remaining_income_tax,
            "chart_data": chart_data,
            "chart_labels": chart_data["labels"],
            "actual_income": chart_data["actual"],
            "predicted_income": chart_data["predicted"],
            "upper_bound": chart_data.get("upper_bound", []),
            "lower_bound": chart_data.get("lower_bound", []),
            "chart_has_data": chart_data.get("has_data", False),
            # Tax optimization widgets
            "afa_summary": afa_summary,
            "travel_summary": travel_summary,
            "gift_warnings": gift_warnings,
            "homeoffice_summary": homeoffice_summary,
        },
    )


@router.get("/api/stats", response_class=HTMLResponse)
async def get_stats_widget(
    request: Request,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> HTMLResponse:
    """Return updated stats cards for HTMX refresh."""
    stats = await dashboard_service.get_dashboard_stats()

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_stats_cards.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "stats": stats,
        },
    )


@router.get("/api/deadlines", response_class=HTMLResponse)
async def get_deadlines_widget(
    request: Request,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> HTMLResponse:
    """Return updated deadlines widget for HTMX refresh."""
    current_year = get_tax_year()
    deadlines = await dashboard_service.get_upcoming_deadlines(year=current_year)

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_deadlines_widget.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "deadlines": deadlines,
        },
    )


@router.get("/api/tax-estimate")
async def get_tax_estimate(
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    year: int | None = None,
) -> dict:
    """Get comprehensive tax estimate (JSON for charts/widgets)."""
    estimate = await dashboard_service.get_tax_estimate(year)
    return estimate.model_dump()


@router.post("/api/quarterly/{year}/{quarter}/toggle", response_class=HTMLResponse)
async def toggle_quarterly_payment(
    request: Request,
    year: int,
    quarter: int,
    compact: bool = False,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> HTMLResponse:
    """Toggle quarterly payment paid status and return updated row + OOB annual tax summary."""
    # Toggle the payment status
    await dashboard_service.toggle_quarterly_payment(year, quarter)

    # Get updated payments to return the row
    quarterly_payments = await dashboard_service.get_quarterly_payments(year)
    payment = next((p for p in quarterly_payments if p.quarter == quarter), None)

    if not payment:
        return HTMLResponse("Payment not found", status_code=404)

    # Calculate totals
    total_quarterly = sum(p.amount for p in quarterly_payments)
    paid_quarterly = sum(p.amount for p in quarterly_payments if p.paid)

    # Get tax estimate for remaining calculation
    tax_estimate = await dashboard_service.get_tax_estimate(year)
    remaining_income_tax = max(tax_estimate.einkommensteuer - paid_quarterly, 0)

    lang = get_current_language()
    _ = get_translator(lang)

    # Render the row (compact for dashboard, table row for taxes page)
    row_template = "partials/_quarterly_row_compact.html" if compact else "partials/_quarterly_row.html"
    row_response = templates.TemplateResponse(
        row_template,
        {
            "request": request,
            "_": _,
            "lang": lang,
            "payment": payment,
            "current_year": year,
            "total_quarterly": total_quarterly,
        },
    )

    # Render the OOB annual tax summary
    annual_summary_response = templates.TemplateResponse(
        "partials/_annual_tax_summary_oob.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "tax_estimate": tax_estimate,
            "paid_quarterly": paid_quarterly,
            "remaining_income_tax": remaining_income_tax,
            "current_year": year,
        },
    )

    # Render the OOB remaining tax stats card
    stats_card_response = templates.TemplateResponse(
        "partials/_remaining_tax_stats_oob.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "paid_quarterly": paid_quarterly,
            "remaining_income_tax": remaining_income_tax,
        },
    )

    # Combine all responses
    combined_html = (
        row_response.body.decode()
        + annual_summary_response.body.decode()
        + stats_card_response.body.decode()
    )
    return HTMLResponse(content=combined_html)


@router.post("/api/deadline/{deadline_id}/toggle", response_class=HTMLResponse)
async def toggle_deadline_status(
    request: Request,
    deadline_id: str,
    compact: bool = False,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> HTMLResponse:
    """Toggle tax deadline completion status and return updated row."""
    # Toggle the deadline status
    await dashboard_service.toggle_deadline_completion(deadline_id)

    # Get current year from the deadline_id (format: type_year_period)
    parts = deadline_id.split("_")
    year = int(parts[1]) if len(parts) >= 2 else get_tax_year()

    # Get updated deadlines
    deadlines = await dashboard_service.get_upcoming_deadlines(year=year, lookahead_days=365)

    # Find the updated deadline
    deadline = next((d for d in deadlines if d.deadline_id == deadline_id), None)

    if not deadline:
        return HTMLResponse("Deadline not found", status_code=404)

    lang = get_current_language()
    _ = get_translator(lang)

    # Use compact template for dashboard, full template for taxes page
    row_template = "partials/_deadline_row_compact.html" if compact else "partials/_deadline_row.html"

    return templates.TemplateResponse(
        row_template,
        {
            "request": request,
            "_": _,
            "lang": lang,
            "deadline": deadline,
        },
    )
