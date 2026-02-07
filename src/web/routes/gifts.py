"""Gift expense (Geschenke) CRUD routes with HTMX patterns."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import GIFT_LIMIT_PER_RECIPIENT, GiftExpenseInput
from src.web.routes.settings import get_current_language
from src.web.services.gift import GiftService, get_gift_service

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


@router.get("/form", response_class=HTMLResponse)
async def get_gift_form(
    request: Request,
    gift_service: GiftService = Depends(get_gift_service),
) -> HTMLResponse:
    """Return the gift expense form HTML for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    # Get unique recipients for autocomplete
    recipients = await gift_service.get_unique_recipients()

    return templates.TemplateResponse(
        "partials/_gift_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "today": date.today().isoformat(),
            "recipients": recipients,
            "limit": GIFT_LIMIT_PER_RECIPIENT,
        },
    )


@router.post("/add", response_class=HTMLResponse)
async def add_gift_expense(
    request: Request,
    date_field: Annotated[date, Form(alias="date")],
    recipient_name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    amount_net: Annotated[Decimal, Form()],
    recipient_company: Annotated[str | None, Form()] = None,
    occasion: Annotated[str | None, Form()] = None,
    gift_service: GiftService = Depends(get_gift_service),
) -> HTMLResponse:
    """Add a new gift expense. Returns the new row HTML for HTMX swap."""
    gift_input = GiftExpenseInput(
        date=date_field,
        recipient_name=recipient_name,
        recipient_company=recipient_company,
        description=description,
        amount_net=amount_net,
        occasion=occasion,
    )

    new_gift, warning = await gift_service.create_gift_expense(gift_input)

    lang = get_current_language()
    _ = get_translator(lang)

    response = templates.TemplateResponse(
        "partials/_gift_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "gift": new_gift,
            "warning": warning,
        },
    )

    # Add warning header if approaching or exceeding limit
    if warning:
        response.headers["HX-Trigger"] = "giftLimitWarning"

    return response


@router.get("", response_class=HTMLResponse)
async def list_gift_expenses(
    request: Request,
    year: int | None = None,
    recipient: str | None = None,
    gift_service: GiftService = Depends(get_gift_service),
) -> HTMLResponse:
    """Return filtered gift expense list for HTMX swap."""
    gifts = await gift_service.get_gift_expenses(
        year=year,
        recipient_name=recipient,
    )

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_gift_list.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "gifts": gifts,
        },
    )


@router.get("/{gift_id}", response_class=HTMLResponse)
async def get_gift_expense(
    request: Request,
    gift_id: int,
    gift_service: GiftService = Depends(get_gift_service),
) -> HTMLResponse:
    """Return gift expense row for display."""
    lang = get_current_language()
    _ = get_translator(lang)

    gift = await gift_service.get_gift_expense(gift_id)

    if not gift:
        return HTMLResponse(
            f"<tr><td colspan='6'>{_('gift.not_found')}</td></tr>",
            status_code=404,
        )

    return templates.TemplateResponse(
        "partials/_gift_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "gift": gift,
        },
    )


@router.get("/recipient/{recipient_name}/status", response_class=HTMLResponse)
async def get_recipient_status(
    request: Request,
    recipient_name: str,
    year: int | None = None,
    gift_service: GiftService = Depends(get_gift_service),
) -> HTMLResponse:
    """Get gift limit status for a recipient. Used for live form feedback."""
    lang = get_current_language()
    _ = get_translator(lang)

    if year is None:
        year = date.today().year

    status = await gift_service.get_recipient_status(recipient_name, year)

    return templates.TemplateResponse(
        "partials/_gift_recipient_status.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "status": status,
        },
    )


@router.delete("/{gift_id}", response_class=HTMLResponse)
async def delete_gift_expense(
    gift_id: int,
    gift_service: GiftService = Depends(get_gift_service),
) -> HTMLResponse:
    """Delete a gift expense. Returns empty string for HTMX swap."""
    await gift_service.delete_gift_expense(gift_id)
    return HTMLResponse("")


@router.get("/summary/{year}", response_class=HTMLResponse)
async def get_gift_summary(
    request: Request,
    year: int,
    gift_service: GiftService = Depends(get_gift_service),
) -> HTMLResponse:
    """Return annual gift expense summary for dashboard."""
    lang = get_current_language()
    _ = get_translator(lang)

    summaries = await gift_service.get_recipient_summaries(year)
    at_risk = await gift_service.get_at_risk_recipients(year)

    # Calculate totals
    total_gifts = sum(s.total_gifts_net for s in summaries)
    total_deductible = sum(s.deductible_amount for s in summaries)
    total_non_deductible = sum(s.non_deductible_amount for s in summaries)

    return templates.TemplateResponse(
        "partials/_gift_summary.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "summaries": summaries,
            "at_risk": at_risk,
            "total_gifts": total_gifts,
            "total_deductible": total_deductible,
            "total_non_deductible": total_non_deductible,
            "limit": GIFT_LIMIT_PER_RECIPIENT,
        },
    )


@router.get("/at-risk/{year}", response_class=HTMLResponse)
async def get_at_risk_recipients(
    request: Request,
    year: int,
    gift_service: GiftService = Depends(get_gift_service),
) -> HTMLResponse:
    """Return recipients at risk of exceeding gift limit. Dashboard widget."""
    lang = get_current_language()
    _ = get_translator(lang)

    at_risk = await gift_service.get_at_risk_recipients(year)

    return templates.TemplateResponse(
        "partials/_gift_at_risk.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "at_risk": at_risk,
            "limit": GIFT_LIMIT_PER_RECIPIENT,
        },
    )
