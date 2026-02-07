"""Expense CRUD routes with HTMX patterns and service layer."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import ExpenseCategory, ExpenseInput, VatRate
from src.web.routes.settings import get_current_language
from src.web.services.expense import ExpenseService, get_expense_service
from src.web.services.expense_ocr import (
    ExpenseReceiptService,
    get_expense_receipt_service,
)

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


@router.get("/form", response_class=HTMLResponse)
async def get_expense_form(request: Request) -> HTMLResponse:
    """Return the expense form HTML for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_expense_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "today": date.today().isoformat(),
            "categories": list(ExpenseCategory),
            "vat_rates": [
                ("0.19", _("vat.standard")),
                ("0.07", _("vat.reduced")),
                ("0.00", _("vat.zero")),
            ],
        },
    )


@router.post("/add", response_class=HTMLResponse)
async def add_expense(
    request: Request,
    date_field: Annotated[date, Form(alias="date")],
    vendor: Annotated[str, Form()],
    description: Annotated[str, Form()],
    amount_gross: Annotated[Decimal, Form()],
    vat_rate: Annotated[str, Form()],
    category: Annotated[str, Form()],
    expense_service: ExpenseService = Depends(get_expense_service),
) -> HTMLResponse:
    """
    Add a new expense.
    Returns the new expense card HTML for HTMX afterbegin swap.
    """
    expense_input = ExpenseInput(
        date=date_field,
        vendor=vendor,
        description=description,
        amount_gross=amount_gross.quantize(Decimal("0.01")),
        vat_rate=VatRate(vat_rate),
        category=ExpenseCategory(category),
    )
    new_expense = await expense_service.book_expense(expense_input)

    # Return just the new expense row
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_expense_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "expense": new_expense,
        },
    )


@router.get("", response_class=HTMLResponse)
async def list_expenses(
    request: Request,
    year: int | None = None,
    category: str | None = None,
    expense_service: ExpenseService = Depends(get_expense_service),
) -> HTMLResponse:
    """Return filtered expense table rows for HTMX swap."""
    cat = ExpenseCategory(category) if category else None
    expenses = await expense_service.get_expenses(year=year, category=cat)

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_expense_rows.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "expenses": expenses,
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def search_expenses(
    request: Request,
    query: str = "",
    expense_service: ExpenseService = Depends(get_expense_service),
) -> HTMLResponse:
    """Search expenses by vendor or description for HTMX swap."""
    expenses = await expense_service.get_expenses()

    # Filter by search query
    if query:
        query_lower = query.lower()
        expenses = [
            e for e in expenses
            if query_lower in e.vendor.lower()
            or (e.description and query_lower in e.description.lower())
        ]

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_expense_rows.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "expenses": expenses,
        },
    )


@router.get("/{expense_id}", response_class=HTMLResponse)
async def get_expense(
    request: Request,
    expense_id: int,
    expense_service: ExpenseService = Depends(get_expense_service),
) -> HTMLResponse:
    """Return expense card for display."""
    lang = get_current_language()
    _ = get_translator(lang)

    expense = await expense_service.get_expense(expense_id)

    if not expense:
        return HTMLResponse(f"<p>{_('expense.no_expenses')}</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/_expense_card.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "expense": expense,
        },
    )


@router.get("/{expense_id}/edit", response_class=HTMLResponse)
async def get_expense_edit_form(
    request: Request,
    expense_id: int,
    expense_service: ExpenseService = Depends(get_expense_service),
) -> HTMLResponse:
    """Return the edit form for an expense."""
    lang = get_current_language()
    _ = get_translator(lang)

    expense = await expense_service.get_expense(expense_id)

    if not expense:
        return HTMLResponse(f"<p>{_('expense.no_expenses')}</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/_expense_edit_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "expense": expense,
            "categories": list(ExpenseCategory),
            "vat_rates": [
                ("0.19", _("vat.standard")),
                ("0.07", _("vat.reduced")),
                ("0.00", _("vat.zero")),
            ],
        },
    )


@router.put("/{expense_id}", response_class=HTMLResponse)
async def update_expense(
    request: Request,
    expense_id: int,
    date_field: Annotated[date, Form(alias="date")],
    vendor: Annotated[str, Form()],
    description: Annotated[str, Form()],
    amount_gross: Annotated[Decimal, Form()],
    vat_rate: Annotated[str, Form()],
    category: Annotated[str, Form()],
    expense_service: ExpenseService = Depends(get_expense_service),
) -> HTMLResponse:
    """Update an expense. Returns updated expense row."""
    lang = get_current_language()
    _ = get_translator(lang)

    expense_input = ExpenseInput(
        date=date_field,
        vendor=vendor,
        description=description,
        amount_gross=amount_gross.quantize(Decimal("0.01")),
        vat_rate=VatRate(vat_rate),
        category=ExpenseCategory(category),
    )
    expense = await expense_service.update_expense(expense_id, expense_input)
    if not expense:
        return HTMLResponse(f"<p>{_('expense.no_expenses')}</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/_expense_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "expense": expense,
        },
    )


@router.delete("/{expense_id}", response_class=HTMLResponse)
async def delete_expense(
    expense_id: int,
    expense_service: ExpenseService = Depends(get_expense_service),
) -> HTMLResponse:
    """Delete an expense. Returns empty string for HTMX swap."""
    await expense_service.delete_expense(expense_id)
    return HTMLResponse("")


# =============================================================================
# Receipt OCR Routes
# =============================================================================


@router.get("/scan", response_class=HTMLResponse)
async def get_receipt_scan_form(request: Request) -> HTMLResponse:
    """Return the receipt scan upload form."""
    lang = get_current_language()
    _ = get_translator(lang)

    # Get OCR engine availability
    receipt_service = get_expense_receipt_service()
    engines = receipt_service.get_available_engines()

    return templates.TemplateResponse(
        "partials/_receipt_scan_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "engines": engines,
            "supported_formats": receipt_service.get_supported_formats(),
        },
    )


@router.post("/scan", response_class=HTMLResponse)
async def scan_receipt(
    request: Request,
    receipt: Annotated[UploadFile, File(description="Receipt image file")],
    use_llm: Annotated[bool, Form()] = True,
) -> HTMLResponse:
    """Scan a receipt image and extract expense data.

    Returns a pre-filled expense form with extracted data for user review.
    """
    lang = get_current_language()
    _ = get_translator(lang)

    # Validate file type
    receipt_service = get_expense_receipt_service()
    supported = receipt_service.get_supported_formats()

    filename = receipt.filename or ""
    file_ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if file_ext not in supported:
        return templates.TemplateResponse(
            "partials/_receipt_scan_error.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "error": _("expense.ocr.unsupported_format").format(
                    formats=", ".join(supported)
                ),
            },
            status_code=400,
        )

    # Read file contents
    try:
        image_bytes = await receipt.read()
    except Exception as e:
        return templates.TemplateResponse(
            "partials/_receipt_scan_error.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "error": f"{_('expense.ocr.read_error')}: {e}",
            },
            status_code=400,
        )

    # Process with OCR
    result = await receipt_service.process_receipt_image(
        image_bytes=image_bytes,
        use_llm=use_llm,
    )

    if not result.success or not result.data:
        error_msg = "; ".join(result.errors) if result.errors else _("expense.ocr.extraction_failed")
        return templates.TemplateResponse(
            "partials/_receipt_scan_error.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "error": error_msg,
                "warnings": result.warnings,
            },
            status_code=422,
        )

    # Return pre-filled form for review
    return templates.TemplateResponse(
        "partials/_receipt_scan_result.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "extraction": result.data,
            "form_data": result.data.to_form_data(),
            "warnings": result.warnings,
            "confidence": result.data.overall_confidence,
            "confidence_level": result.data.confidence_level.value,
            "processing_time_ms": result.processing_time_ms,
            "categories": list(ExpenseCategory),
            "vat_rates": [
                ("0.19", _("vat.standard")),
                ("0.07", _("vat.reduced")),
                ("0.00", _("vat.zero")),
            ],
            "today": date.today().isoformat(),
        },
    )


@router.get("/scan/status", response_class=HTMLResponse)
async def get_ocr_status(request: Request) -> HTMLResponse:
    """Get OCR engine availability status."""
    lang = get_current_language()
    _ = get_translator(lang)

    receipt_service = get_expense_receipt_service()
    engines = receipt_service.get_available_engines()

    return templates.TemplateResponse(
        "partials/_ocr_status.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "engines": engines,
        },
    )
