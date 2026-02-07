"""Travel expense (Reisekosten) CRUD routes with HTMX patterns."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import TravelExpenseInput
from src.web.routes.settings import get_current_language
from src.web.services.travel import TravelService, get_travel_service

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


@router.get("/form", response_class=HTMLResponse)
async def get_travel_form(
    request: Request,
    travel_service: TravelService = Depends(get_travel_service),
) -> HTMLResponse:
    """Return the travel expense form HTML for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    countries = travel_service.get_supported_countries()

    return templates.TemplateResponse(
        "partials/_travel_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "today": date.today().isoformat(),
            "countries": countries,
        },
    )


@router.post("/add", response_class=HTMLResponse)
async def add_travel_expense(
    request: Request,
    date_field: Annotated[date, Form(alias="date")],
    destination: Annotated[str, Form()],
    purpose: Annotated[str, Form()],
    departure_time: Annotated[str, Form()],
    return_time: Annotated[str, Form()],
    absence_hours: Annotated[Decimal, Form()],
    km_driven: Annotated[Decimal, Form()] = Decimal("0"),
    country_code: Annotated[str, Form()] = "DE",
    is_overnight: Annotated[bool, Form()] = False,
    is_travel_day: Annotated[bool, Form()] = False,
    breakfast_provided: Annotated[bool, Form()] = False,
    lunch_provided: Annotated[bool, Form()] = False,
    dinner_provided: Annotated[bool, Form()] = False,
    travel_service: TravelService = Depends(get_travel_service),
) -> HTMLResponse:
    """Add a new travel expense. Returns the new row HTML for HTMX swap."""
    travel_input = TravelExpenseInput(
        date=date_field,
        destination=destination,
        purpose=purpose,
        departure_time=departure_time,
        return_time=return_time,
        absence_hours=absence_hours,
        is_overnight=is_overnight,
        is_travel_day=is_travel_day,
        km_driven=km_driven,
        country_code=country_code,
        breakfast_provided=breakfast_provided,
        lunch_provided=lunch_provided,
        dinner_provided=dinner_provided,
    )

    new_travel = await travel_service.create_travel_expense(travel_input)

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_travel_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "travel": new_travel,
        },
    )


@router.get("", response_class=HTMLResponse)
async def list_travel_expenses(
    request: Request,
    year: int | None = None,
    travel_service: TravelService = Depends(get_travel_service),
) -> HTMLResponse:
    """Return filtered travel expense list for HTMX swap."""
    travels = await travel_service.get_travel_expenses(year=year)

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_travel_list.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "travels": travels,
        },
    )


@router.get("/{travel_id}", response_class=HTMLResponse)
async def get_travel_expense(
    request: Request,
    travel_id: int,
    travel_service: TravelService = Depends(get_travel_service),
) -> HTMLResponse:
    """Return travel expense row for display."""
    lang = get_current_language()
    _ = get_translator(lang)

    travel = await travel_service.get_travel_expense(travel_id)

    if not travel:
        return HTMLResponse(
            f"<tr><td colspan='7'>{_('travel.not_found')}</td></tr>",
            status_code=404,
        )

    return templates.TemplateResponse(
        "partials/_travel_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "travel": travel,
        },
    )


@router.post("/preview/per-diem", response_class=HTMLResponse)
async def preview_per_diem(
    request: Request,
    absence_hours: Annotated[Decimal, Form()],
    country_code: Annotated[str, Form()] = "DE",
    is_overnight: Annotated[bool, Form()] = False,
    is_travel_day: Annotated[bool, Form()] = False,
    breakfast_provided: Annotated[bool, Form()] = False,
    lunch_provided: Annotated[bool, Form()] = False,
    dinner_provided: Annotated[bool, Form()] = False,
    travel_service: TravelService = Depends(get_travel_service),
) -> HTMLResponse:
    """Live preview of per diem calculation."""
    lang = get_current_language()
    _ = get_translator(lang)

    preview = travel_service.calculate_per_diem_preview(
        absence_hours=absence_hours,
        country_code=country_code,
        is_travel_day=is_travel_day,
        is_overnight=is_overnight,
        breakfast_provided=breakfast_provided,
        lunch_provided=lunch_provided,
        dinner_provided=dinner_provided,
    )

    return templates.TemplateResponse(
        "partials/_per_diem_preview.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "preview": preview,
        },
    )


@router.post("/preview/km", response_class=HTMLResponse)
async def preview_km(
    request: Request,
    km_driven: Annotated[Decimal, Form()],
    travel_service: TravelService = Depends(get_travel_service),
) -> HTMLResponse:
    """Live preview of km allowance calculation."""
    lang = get_current_language()
    _ = get_translator(lang)

    preview = travel_service.calculate_km_preview(km_driven)

    return templates.TemplateResponse(
        "partials/_km_preview.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "preview": preview,
        },
    )


@router.delete("/{travel_id}", response_class=HTMLResponse)
async def delete_travel_expense(
    travel_id: int,
    travel_service: TravelService = Depends(get_travel_service),
) -> HTMLResponse:
    """Delete a travel expense. Returns empty string for HTMX swap."""
    await travel_service.delete_travel_expense(travel_id)
    return HTMLResponse("")


@router.get("/summary/{year}", response_class=HTMLResponse)
async def get_annual_summary(
    request: Request,
    year: int,
    travel_service: TravelService = Depends(get_travel_service),
) -> HTMLResponse:
    """Return annual travel expense summary for dashboard."""
    lang = get_current_language()
    _ = get_translator(lang)

    totals = await travel_service.get_annual_totals(year)
    monthly = await travel_service.get_monthly_summary(year)

    return templates.TemplateResponse(
        "partials/_travel_summary.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "totals": totals,
            "monthly": monthly,
        },
    )
