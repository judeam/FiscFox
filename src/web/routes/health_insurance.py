"""Health insurance CRUD routes with HTMX patterns and service layer.

Routes for managing Krankenversicherung payments following German tax law § 10 EStG.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import CoverageType, HealthInsuranceInput, InsuranceType
from src.web.routes.settings import get_current_language
from src.web.services.health_insurance import (
    HealthInsuranceService,
    get_health_insurance_service,
)

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


@router.get("/form", response_class=HTMLResponse)
async def get_health_insurance_form(
    request: Request,
    health_insurance_service: HealthInsuranceService = Depends(get_health_insurance_service),
) -> HTMLResponse:
    """Return the health insurance payment form HTML for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    # Get all providers for the dropdown
    providers = await health_insurance_service.get_providers()

    return templates.TemplateResponse(
        "partials/_health_insurance_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "today": date.today().isoformat(),
            "providers": providers,
            "insurance_types": list(InsuranceType),
            "coverage_types": list(CoverageType),
        },
    )


@router.post("/add", response_class=HTMLResponse)
async def add_health_insurance(
    request: Request,
    date_field: Annotated[date, Form(alias="date")],
    provider_id: Annotated[int, Form()],
    insurance_type: Annotated[str, Form()],
    coverage_type: Annotated[str, Form()],
    amount: Annotated[Decimal, Form()],
    has_krankengeld: Annotated[bool, Form()] = False,
    policy_number: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    health_insurance_service: HealthInsuranceService = Depends(get_health_insurance_service),
) -> HTMLResponse:
    """Add a new health insurance payment.

    Returns the new payment row HTML for HTMX afterbegin swap.
    """
    health_insurance_input = HealthInsuranceInput(
        date=date_field,
        provider_id=provider_id,
        insurance_type=InsuranceType(insurance_type),
        coverage_type=CoverageType(coverage_type),
        amount=amount.quantize(Decimal("0.01")),
        has_krankengeld=has_krankengeld,
        policy_number=policy_number,
        notes=notes,
    )
    new_payment = await health_insurance_service.create_health_insurance(health_insurance_input)

    # Return just the new payment row
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_health_insurance_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "payment": new_payment,
        },
    )


@router.get("/list", response_class=HTMLResponse)
async def list_health_insurance(
    request: Request,
    year: int | None = None,
    insurance_type: str | None = None,
    coverage_type: str | None = None,
    health_insurance_service: HealthInsuranceService = Depends(get_health_insurance_service),
) -> HTMLResponse:
    """Return filtered health insurance table rows for HTMX swap."""
    ins_type = InsuranceType(insurance_type) if insurance_type else None
    cov_type = CoverageType(coverage_type) if coverage_type else None

    payments = await health_insurance_service.get_health_insurances(
        year=year,
        insurance_type=ins_type,
        coverage_type=cov_type,
    )

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_health_insurance_rows.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "payments": payments,
        },
    )


@router.get("/providers", response_class=HTMLResponse)
async def get_providers(
    request: Request,
    insurance_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    health_insurance_service: HealthInsuranceService = Depends(get_health_insurance_service),
) -> HTMLResponse:
    """Return provider options for searchable dropdown.

    Filters by insurance type (GKV/PKV) and search query.
    """
    ins_type = InsuranceType(insurance_type) if insurance_type else None
    providers = await health_insurance_service.get_providers(insurance_type=ins_type)

    # Filter by search query if provided
    if q:
        q_lower = q.lower()
        providers = [
            p for p in providers if q_lower in p.name.lower() or (p.short_name and q_lower in p.short_name.lower())
        ]

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_health_insurance_providers.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "providers": providers,
        },
    )


@router.get("/summary/{year}", response_class=HTMLResponse)
async def get_summary(
    request: Request,
    year: int,
    health_insurance_service: HealthInsuranceService = Depends(get_health_insurance_service),
) -> HTMLResponse:
    """Return annual health insurance summary for HTMX swap."""
    summary = await health_insurance_service.get_summary(year)
    deduction = await health_insurance_service.get_deduction(year)

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_health_insurance_summary.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "summary": summary,
            "deduction": deduction,
            "year": year,
        },
    )


@router.get("/{payment_id}", response_class=HTMLResponse)
async def get_health_insurance(
    request: Request,
    payment_id: int,
    health_insurance_service: HealthInsuranceService = Depends(get_health_insurance_service),
) -> HTMLResponse:
    """Return health insurance payment for display."""
    lang = get_current_language()
    _ = get_translator(lang)

    payment = await health_insurance_service.get_health_insurance(payment_id)

    if not payment:
        return HTMLResponse(f"<p>{_('health_insurance.no_payments')}</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/_health_insurance_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "payment": payment,
        },
    )


@router.delete("/{payment_id}", response_class=HTMLResponse)
async def delete_health_insurance(
    payment_id: int,
    health_insurance_service: HealthInsuranceService = Depends(get_health_insurance_service),
) -> HTMLResponse:
    """Delete a health insurance payment. Returns empty string for HTMX swap."""
    await health_insurance_service.delete_health_insurance(payment_id)
    return HTMLResponse("")
