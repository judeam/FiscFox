"""Business meal (Bewirtung) CRUD routes with HTMX patterns."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import BEWIRTUNG_DEDUCTION_RATE, INTERNAL_EVENT_CAP_PER_PERSON, BusinessMealInput
from src.web.routes.settings import get_current_language
from src.web.services.bewirtung import BewirtungService, get_bewirtung_service

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


@router.get("/form", response_class=HTMLResponse)
async def get_bewirtung_form(
    request: Request,
) -> HTMLResponse:
    """Return the business meal form HTML for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_bewirtung_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "today": date.today().isoformat(),
            "deduction_rate": BEWIRTUNG_DEDUCTION_RATE,
            "cap_per_person": INTERNAL_EVENT_CAP_PER_PERSON,
        },
    )


@router.post("/add", response_class=HTMLResponse)
async def add_business_meal(
    request: Request,
    date_field: Annotated[date, Form(alias="date")],
    restaurant_name: Annotated[str, Form()],
    business_purpose: Annotated[str, Form()],
    attendees: Annotated[str, Form()],
    attendee_count: Annotated[int, Form()],
    total_amount: Annotated[Decimal, Form()],
    tip_amount: Annotated[Decimal, Form()] = Decimal("0"),
    is_internal: Annotated[bool, Form()] = False,
    bewirtung_service: BewirtungService = Depends(get_bewirtung_service),
) -> HTMLResponse:
    """Add a new business meal expense. Returns the new row HTML for HTMX swap."""
    meal_input = BusinessMealInput(
        date=date_field,
        restaurant_name=restaurant_name,
        business_purpose=business_purpose,
        attendees=attendees,
        attendee_count=attendee_count,
        total_amount=total_amount,
        tip_amount=tip_amount,
        is_internal=is_internal,
    )

    new_meal = await bewirtung_service.create_business_meal(meal_input)

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_bewirtung_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "meal": new_meal,
        },
    )


@router.get("", response_class=HTMLResponse)
async def list_business_meals(
    request: Request,
    year: int | None = None,
    is_internal: bool | None = None,
    bewirtung_service: BewirtungService = Depends(get_bewirtung_service),
) -> HTMLResponse:
    """Return filtered business meal list for HTMX swap."""
    meals = await bewirtung_service.get_business_meals(
        year=year,
        is_internal=is_internal,
    )

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_bewirtung_list.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "meals": meals,
        },
    )


@router.get("/{meal_id}", response_class=HTMLResponse)
async def get_business_meal(
    request: Request,
    meal_id: int,
    bewirtung_service: BewirtungService = Depends(get_bewirtung_service),
) -> HTMLResponse:
    """Return business meal row for display."""
    lang = get_current_language()
    _ = get_translator(lang)

    meal = await bewirtung_service.get_business_meal(meal_id)

    if not meal:
        return HTMLResponse(
            f"<tr><td colspan='7'>{_('bewirtung.not_found')}</td></tr>",
            status_code=404,
        )

    return templates.TemplateResponse(
        "partials/_bewirtung_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "meal": meal,
        },
    )


@router.post("/preview", response_class=HTMLResponse)
async def preview_deduction(
    request: Request,
    total_amount: Annotated[Decimal, Form()],
    attendee_count: Annotated[int, Form()],
    is_internal: Annotated[bool, Form()] = False,
    bewirtung_service: BewirtungService = Depends(get_bewirtung_service),
) -> HTMLResponse:
    """Live preview of deduction calculation."""
    lang = get_current_language()
    _ = get_translator(lang)

    preview = bewirtung_service.calculate_deduction_preview(
        total_amount=total_amount,
        attendee_count=attendee_count,
        is_internal=is_internal,
    )

    return templates.TemplateResponse(
        "partials/_bewirtung_preview.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "preview": preview,
        },
    )


@router.delete("/{meal_id}", response_class=HTMLResponse)
async def delete_business_meal(
    meal_id: int,
    bewirtung_service: BewirtungService = Depends(get_bewirtung_service),
) -> HTMLResponse:
    """Delete a business meal expense. Returns empty string for HTMX swap."""
    await bewirtung_service.delete_business_meal(meal_id)
    return HTMLResponse("")


@router.get("/summary/{year}", response_class=HTMLResponse)
async def get_bewirtung_summary(
    request: Request,
    year: int,
    bewirtung_service: BewirtungService = Depends(get_bewirtung_service),
) -> HTMLResponse:
    """Return annual business meal summary for dashboard."""
    lang = get_current_language()
    _ = get_translator(lang)

    totals = await bewirtung_service.get_annual_totals(year)
    monthly = await bewirtung_service.get_monthly_summary(year)

    return templates.TemplateResponse(
        "partials/_bewirtung_summary.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "totals": totals,
            "monthly": monthly,
            "deduction_rate": BEWIRTUNG_DEDUCTION_RATE,
        },
    )
