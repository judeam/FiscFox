"""Home office (Homeoffice) CRUD routes with HTMX patterns."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import (
    HOME_OFFICE_ANNUAL_CAP,
    HOME_OFFICE_DAILY_RATE,
    HOME_OFFICE_MAX_DAYS,
    HomeOfficeDayInput,
    HomeOfficeSettingsInput,
)
from src.web.routes.settings import get_current_language
from src.web.services.homeoffice import HomeOfficeService, get_homeoffice_service

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


@router.get("/settings/{year}", response_class=HTMLResponse)
async def get_settings_form(
    request: Request,
    year: int,
    homeoffice_service: HomeOfficeService = Depends(get_homeoffice_service),
) -> HTMLResponse:
    """Return the home office settings form for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    settings = await homeoffice_service.get_settings(year)

    return templates.TemplateResponse(
        "partials/_homeoffice_settings.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "settings": settings,
            "daily_rate": HOME_OFFICE_DAILY_RATE,
            "max_days": HOME_OFFICE_MAX_DAYS,
            "annual_cap": HOME_OFFICE_ANNUAL_CAP,
        },
    )


@router.post("/settings/{year}", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    year: int,
    method: Annotated[str, Form()],
    room_sqm: Annotated[Decimal | None, Form()] = None,
    total_sqm: Annotated[Decimal | None, Form()] = None,
    monthly_costs: Annotated[Decimal | None, Form()] = None,
    homeoffice_service: HomeOfficeService = Depends(get_homeoffice_service),
) -> HTMLResponse:
    """Save home office settings for a year."""
    lang = get_current_language()
    _ = get_translator(lang)

    settings_input = HomeOfficeSettingsInput(
        year=year,
        method=method,
        room_sqm=room_sqm,
        total_sqm=total_sqm,
        monthly_costs=monthly_costs,
    )

    settings = await homeoffice_service.save_settings(settings_input)

    return templates.TemplateResponse(
        "partials/_homeoffice_settings.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "settings": settings,
            "daily_rate": HOME_OFFICE_DAILY_RATE,
            "max_days": HOME_OFFICE_MAX_DAYS,
            "annual_cap": HOME_OFFICE_ANNUAL_CAP,
            "saved": True,
        },
    )


@router.get("/days/{year}", response_class=HTMLResponse)
async def list_home_office_days(
    request: Request,
    year: int,
    month: int | None = None,
    homeoffice_service: HomeOfficeService = Depends(get_homeoffice_service),
) -> HTMLResponse:
    """Return home office days list for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    days = await homeoffice_service.get_home_office_days(year=year, month=month)
    summary = await homeoffice_service.get_annual_summary(year)

    return templates.TemplateResponse(
        "partials/_homeoffice_days.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "month": month,
            "days": days,
            "summary": summary,
        },
    )


@router.get("/form/{year}", response_class=HTMLResponse)
async def get_day_form(
    request: Request,
    year: int,
    homeoffice_service: HomeOfficeService = Depends(get_homeoffice_service),
) -> HTMLResponse:
    """Return the home office day form for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    summary = await homeoffice_service.get_annual_summary(year)

    return templates.TemplateResponse(
        "partials/_homeoffice_day_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "today": date.today().isoformat(),
            "summary": summary,
        },
    )


@router.post("/days/add", response_class=HTMLResponse)
async def add_home_office_day(
    request: Request,
    date_field: Annotated[date, Form(alias="date")],
    notes: Annotated[str | None, Form()] = None,
    homeoffice_service: HomeOfficeService = Depends(get_homeoffice_service),
) -> HTMLResponse:
    """Add a home office day. Returns the new row HTML for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    day_input = HomeOfficeDayInput(
        date=date_field,
        notes=notes,
    )

    new_day, warning = await homeoffice_service.add_home_office_day(day_input)

    response = templates.TemplateResponse(
        "partials/_homeoffice_day_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "day": new_day,
            "warning": warning,
        },
    )

    # Add warning header if at limit
    if warning:
        response.headers["HX-Trigger"] = "homeOfficeLimitWarning"

    return response


@router.delete("/days/{day_id}", response_class=HTMLResponse)
async def delete_home_office_day(
    day_id: int,
    homeoffice_service: HomeOfficeService = Depends(get_homeoffice_service),
) -> HTMLResponse:
    """Delete a home office day. Returns empty string for HTMX swap."""
    await homeoffice_service.delete_home_office_day(day_id)
    return HTMLResponse("")


@router.get("/summary/{year}", response_class=HTMLResponse)
async def get_summary(
    request: Request,
    year: int,
    homeoffice_service: HomeOfficeService = Depends(get_homeoffice_service),
) -> HTMLResponse:
    """Return annual home office summary for dashboard."""
    lang = get_current_language()
    _ = get_translator(lang)

    summary = await homeoffice_service.get_annual_summary(year)
    monthly = await homeoffice_service.get_monthly_breakdown(year)

    return templates.TemplateResponse(
        "partials/_homeoffice_summary.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "summary": summary,
            "monthly": monthly,
        },
    )


@router.get("/calendar/{year}/{month}", response_class=HTMLResponse)
async def get_calendar(
    request: Request,
    year: int,
    month: int,
    homeoffice_service: HomeOfficeService = Depends(get_homeoffice_service),
) -> HTMLResponse:
    """Return calendar view for a month. Visual home office day picker."""
    lang = get_current_language()
    _ = get_translator(lang)

    days = await homeoffice_service.get_home_office_days(year=year, month=month)
    recorded_dates = {d.date for d in days}

    return templates.TemplateResponse(
        "partials/_homeoffice_calendar.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "month": month,
            "recorded_dates": recorded_dates,
        },
    )
