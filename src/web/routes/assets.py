"""Asset (Anlagevermögen) CRUD routes with HTMX patterns."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import AssetCategory, AssetInput, DepreciationMethod, VatRate
from src.web.routes.settings import get_current_language
from src.web.services.asset import AssetService, get_asset_service

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


@router.get("/form", response_class=HTMLResponse)
async def get_asset_form(request: Request) -> HTMLResponse:
    """Return the asset form HTML for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_asset_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "today": date.today().isoformat(),
            "categories": list(AssetCategory),
            "depreciation_methods": list(DepreciationMethod),
            "vat_rates": [
                ("0.19", _("vat.standard")),
                ("0.07", _("vat.reduced")),
                ("0.00", _("vat.zero")),
            ],
        },
    )


@router.post("/add", response_class=HTMLResponse)
async def add_asset(
    request: Request,
    name: Annotated[str, Form()],
    purchase_date: Annotated[date, Form()],
    acquisition_cost: Annotated[Decimal, Form()],
    vat_rate: Annotated[str, Form()],
    category: Annotated[str, Form()],
    useful_life_years: Annotated[int, Form()] = 0,
    depreciation_method: Annotated[str, Form()] = "",
    private_use_percent: Annotated[Decimal, Form()] = Decimal("0"),
    description: Annotated[str, Form()] = "",
    asset_service: AssetService = Depends(get_asset_service),
) -> HTMLResponse:
    """Add a new asset. Returns the new asset row HTML for HTMX swap."""
    # Calculate VAT amount from gross cost
    vat = VatRate(vat_rate)
    rate = Decimal(vat.value)
    net_cost = (acquisition_cost / (1 + rate)).quantize(Decimal("0.01"))
    vat_amount = (acquisition_cost - net_cost).quantize(Decimal("0.01"))

    asset_input = AssetInput(
        name=name,
        purchase_date=purchase_date,
        acquisition_cost=net_cost,
        vat_amount=vat_amount,
        vat_rate=vat,
        category=AssetCategory(category),
        useful_life_years=useful_life_years if useful_life_years > 0 else None,
        depreciation_method=(
            DepreciationMethod(depreciation_method) if depreciation_method else None
        ),
        private_use_percent=private_use_percent,
        description=description if description else None,
    )

    new_asset = await asset_service.create_asset(asset_input)

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_asset_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "asset": new_asset,
        },
    )


@router.get("", response_class=HTMLResponse)
async def list_assets(
    request: Request,
    year: int | None = None,
    category: str | None = None,
    active_only: bool = True,
    asset_service: AssetService = Depends(get_asset_service),
) -> HTMLResponse:
    """Return filtered asset list for HTMX swap."""
    cat = AssetCategory(category) if category else None
    assets = await asset_service.get_assets(
        year=year,
        category=cat,
        active_only=active_only,
    )

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_asset_list.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "assets": assets,
        },
    )


@router.get("/{asset_id}", response_class=HTMLResponse)
async def get_asset(
    request: Request,
    asset_id: int,
    asset_service: AssetService = Depends(get_asset_service),
) -> HTMLResponse:
    """Return asset row for display."""
    lang = get_current_language()
    _ = get_translator(lang)

    asset = await asset_service.get_asset(asset_id)

    if not asset:
        return HTMLResponse(f"<tr><td colspan='6'>{_('asset.not_found')}</td></tr>", status_code=404)

    return templates.TemplateResponse(
        "partials/_asset_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "asset": asset,
        },
    )


@router.get("/{asset_id}/schedule", response_class=HTMLResponse)
async def get_depreciation_schedule(
    request: Request,
    asset_id: int,
    asset_service: AssetService = Depends(get_asset_service),
) -> HTMLResponse:
    """Return depreciation schedule for an asset."""
    lang = get_current_language()
    _ = get_translator(lang)

    asset = await asset_service.get_asset(asset_id)
    if not asset:
        return HTMLResponse(f"<p>{_('asset.not_found')}</p>", status_code=404)

    schedule = await asset_service.get_depreciation_schedule(asset_id)

    return templates.TemplateResponse(
        "partials/_depreciation_schedule.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "asset": asset,
            "schedule": schedule,
        },
    )


@router.post("/suggest", response_class=HTMLResponse)
async def suggest_depreciation(
    request: Request,
    acquisition_cost: Annotated[Decimal, Form()],
    category: Annotated[str, Form()],
    purchase_date: Annotated[date, Form()],
    asset_service: AssetService = Depends(get_asset_service),
) -> HTMLResponse:
    """Return depreciation method suggestion based on asset details."""
    lang = get_current_language()
    _ = get_translator(lang)

    suggestion = await asset_service.get_depreciation_suggestion(
        cost=acquisition_cost,
        category=AssetCategory(category),
        purchase_date=purchase_date,
    )

    return templates.TemplateResponse(
        "partials/_depreciation_suggestion.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "suggestion": suggestion,
        },
    )


@router.post("/{asset_id}/dispose", response_class=HTMLResponse)
async def dispose_asset(
    request: Request,
    asset_id: int,
    disposed_date: Annotated[date, Form()],
    disposal_amount: Annotated[Decimal, Form()],
    asset_service: AssetService = Depends(get_asset_service),
) -> HTMLResponse:
    """Record asset disposal. Returns updated asset row."""
    lang = get_current_language()
    _ = get_translator(lang)

    asset = await asset_service.dispose_asset(
        asset_id=asset_id,
        disposed_date=disposed_date,
        disposal_amount=disposal_amount.quantize(Decimal("0.01")),
    )

    if not asset:
        return HTMLResponse(f"<tr><td colspan='6'>{_('asset.not_found')}</td></tr>", status_code=404)

    return templates.TemplateResponse(
        "partials/_asset_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "asset": asset,
        },
    )


@router.delete("/{asset_id}", response_class=HTMLResponse)
async def delete_asset(
    asset_id: int,
    asset_service: AssetService = Depends(get_asset_service),
) -> HTMLResponse:
    """Delete an asset. Returns empty string for HTMX swap."""
    await asset_service.delete_asset(asset_id)
    return HTMLResponse("")


@router.get("/summary/{year}", response_class=HTMLResponse)
async def get_annual_summary(
    request: Request,
    year: int,
    asset_service: AssetService = Depends(get_asset_service),
) -> HTMLResponse:
    """Return annual depreciation summary for dashboard."""
    lang = get_current_language()
    _ = get_translator(lang)

    total_depreciation = await asset_service.get_annual_depreciation(year)
    category_breakdown = await asset_service.get_category_breakdown(year)
    expiring = await asset_service.get_assets_expiring_this_year(year)

    return templates.TemplateResponse(
        "partials/_asset_summary.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "year": year,
            "total_depreciation": total_depreciation,
            "category_breakdown": category_breakdown,
            "expiring_assets": expiring,
        },
    )
