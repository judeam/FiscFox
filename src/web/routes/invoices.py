"""Invoice CRUD routes with HTMX patterns and service layer."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import (
    DEFAULT_SENDER,
    InvoiceInput,
    InvoiceItem,
    InvoiceStatus,
    VatRate,
)
from src.db.repository import UploadedDocumentRepository
from src.web.routes.settings import get_current_language, load_settings, save_settings
from src.web.services.client import ClientService, get_client_service
from src.web.services.invoice import InvoiceService, get_invoice_service


def get_uploaded_doc_repo() -> UploadedDocumentRepository:
    """FastAPI dependency for UploadedDocumentRepository."""
    return UploadedDocumentRepository()


router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


@router.get("", response_class=HTMLResponse)
async def list_invoices(
    request: Request,
    status: str | None = Query(default="all"),
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Return filtered invoice table rows for HTMX swap."""
    if status == "all":
        filtered = await invoice_service.get_invoices()
    else:
        filtered = await invoice_service.get_invoices(status=InvoiceStatus(status))

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_invoice_table.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "invoices": filtered,
        },
    )


@router.get("/form", response_class=HTMLResponse)
async def get_invoice_form(
    request: Request,
    invoice_service: InvoiceService = Depends(get_invoice_service),
    client_service: ClientService = Depends(get_client_service),
) -> HTMLResponse:
    """Return the invoice form HTML for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    # Get next invoice number
    next_number = await invoice_service.invoice_repo.get_next_invoice_number(
        date.today().year
    )

    # Get clients for dropdown
    clients = await client_service.get_clients_for_dropdown()

    return templates.TemplateResponse(
        "partials/_invoice_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "today": date.today().isoformat(),
            "next_invoice_number": next_number,
            "clients": clients,
            "vat_rates": [
                ("0.00", _("vat.zero")),
                ("0.19", _("vat.standard")),
                ("0.07", _("vat.reduced")),
            ],
        },
    )


@router.post("/add", response_class=HTMLResponse)
async def add_invoice(
    request: Request,
    client: Annotated[str, Form()],
    invoice_number: Annotated[str, Form()],
    date_field: Annotated[date, Form(alias="date")],
    due_date: Annotated[date | None, Form()] = None,
    amount: Annotated[Decimal, Form()] = Decimal("0"),
    vat_rate: Annotated[str, Form()] = "0.00",
    description: Annotated[str, Form()] = "",
    client_id: Annotated[int | None, Form()] = None,
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Add a new invoice. Returns the new invoice row HTML."""
    invoice_input = InvoiceInput(
        client=client,
        invoice_number=invoice_number,
        date=date_field,
        due_date=due_date,
        amount=amount.quantize(Decimal("0.01")),
        vat_rate=VatRate(vat_rate),
        description=description,
    )
    new_invoice = await invoice_service.create_invoice(invoice_input, client_id=client_id)

    # Auto-detect EU clients: If invoice uses 0% VAT (reverse charge),
    # automatically enable "has_eu_clients" setting for ZSM reporting
    if vat_rate == "0.00":
        user_settings = load_settings()
        if not user_settings.has_eu_clients:
            user_settings.has_eu_clients = True
            save_settings(user_settings)

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_invoice_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "invoice": new_invoice,
        },
    )


@router.post("/{invoice_id}/mark-paid", response_class=HTMLResponse)
async def mark_invoice_paid(
    request: Request,
    invoice_id: int,
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Mark an invoice as paid. Returns updated row HTML."""
    lang = get_current_language()
    _ = get_translator(lang)

    invoice = await invoice_service.mark_paid(invoice_id)
    if not invoice:
        return HTMLResponse(
            f"<tr><td colspan='4'>{_('invoice.no_invoices')}</td></tr>",
            status_code=404
        )

    return templates.TemplateResponse(
        "partials/_invoice_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "invoice": invoice,
        },
    )


@router.get("/{invoice_id}", response_class=HTMLResponse)
async def get_invoice_details(
    request: Request,
    invoice_id: int,
    invoice_service: InvoiceService = Depends(get_invoice_service),
    upload_repo: UploadedDocumentRepository = Depends(get_uploaded_doc_repo),
) -> HTMLResponse:
    """Return invoice details modal/card."""
    lang = get_current_language()
    _ = get_translator(lang)

    invoice = await invoice_service.get_invoice(invoice_id)

    if not invoice:
        return HTMLResponse(f"<p>{_('invoice.no_invoices')}</p>", status_code=404)

    # Get uploaded document if exists (for PDF viewing and line items)
    line_items = []
    pdf_path = None

    uploaded_doc = await upload_repo.get_by_invoice_id(invoice_id)
    if uploaded_doc:
        pdf_path = uploaded_doc.get("file_path")
        # Parse line items from extracted_data JSON
        extracted_data_str = uploaded_doc.get("extracted_data")
        if extracted_data_str:
            try:
                extracted_data = json.loads(extracted_data_str)
                line_items = extracted_data.get("line_items", [])
            except (json.JSONDecodeError, TypeError):
                pass

    return templates.TemplateResponse(
        "partials/_invoice_details.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "invoice": invoice,
            "pdf_path": pdf_path,
            "line_items": line_items,
        },
    )


@router.delete("/{invoice_id}", response_class=HTMLResponse)
async def delete_invoice(
    invoice_id: int,
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Delete an invoice. Returns empty string for HTMX swap."""
    await invoice_service.delete_invoice(invoice_id)
    return HTMLResponse("")


@router.get("/{invoice_id}/edit", response_class=HTMLResponse)
async def get_edit_invoice_form(
    request: Request,
    invoice_id: int,
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Return the invoice edit form HTML for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    invoice = await invoice_service.get_invoice(invoice_id)
    if not invoice:
        return HTMLResponse(f"<p>{_('invoice.no_invoices')}</p>", status_code=404)

    # Check if invoice is paid - paid invoices cannot be edited
    if invoice.status == InvoiceStatus.PAID:
        return HTMLResponse(
            f"""<div class="bg-sage/10 border border-sage/30 rounded-lg p-4 text-sm text-sage">
                <div class="flex items-center gap-2">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                    </svg>
                    <span class="font-medium">{_('invoice.paid_cannot_edit') if _ else 'Bezahlte Rechnungen können nicht bearbeitet werden.'}</span>
                </div>
            </div>""",
            status_code=403
        )

    # Check if invoice has PDF - if so, it's locked and cannot be edited
    if invoice.pdf_path:
        return HTMLResponse(
            f"""<div class="bg-amber/10 border border-amber/30 rounded-lg p-4 text-sm text-amber-dark dark:text-amber">
                <div class="flex items-center gap-2">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
                    </svg>
                    <span class="font-medium">{_('invoice.locked_cannot_edit') if _ else 'Diese Rechnung ist gesperrt und kann nicht bearbeitet werden.'}</span>
                </div>
                <p class="mt-2 text-xs opacity-80">{_('invoice.locked_reason') if _ else 'Rechnungen mit PDF-Export oder PDF-Import sind finalisiert.'}</p>
            </div>""",
            status_code=403
        )

    return templates.TemplateResponse(
        "partials/_invoice_edit_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "invoice": invoice,
            "vat_rates": [
                ("0.00", _("vat.zero")),
                ("0.19", _("vat.standard")),
                ("0.07", _("vat.reduced")),
            ],
        },
    )


@router.put("/{invoice_id}/update", response_class=HTMLResponse)
async def update_invoice(
    request: Request,
    invoice_id: int,
    client: Annotated[str, Form()],
    invoice_number: Annotated[str, Form()],
    date_field: Annotated[date, Form(alias="date")],
    due_date: Annotated[date | None, Form()] = None,
    amount: Annotated[Decimal, Form()] = Decimal("0"),
    vat_rate: Annotated[str, Form()] = "0.00",
    description: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "pending",
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Update an existing invoice. Returns the updated invoice row HTML."""
    lang = get_current_language()
    _ = get_translator(lang)

    # Check if invoice exists and can be edited
    invoice = await invoice_service.get_invoice(invoice_id)
    if not invoice:
        return HTMLResponse(
            _('invoice.no_invoices') if _ else 'Rechnung nicht gefunden.',
            status_code=404
        )

    # Check if invoice is paid - paid invoices cannot be updated
    if invoice.status == InvoiceStatus.PAID:
        return HTMLResponse(
            _('invoice.paid_cannot_edit') if _ else 'Bezahlte Rechnungen können nicht bearbeitet werden.',
            status_code=403
        )

    # Check if invoice has PDF - if so, it's locked and cannot be updated
    if invoice.pdf_path:
        return HTMLResponse(
            _('invoice.locked_cannot_edit') if _ else 'Diese Rechnung ist gesperrt.',
            status_code=403
        )

    # Update the invoice
    updated_invoice = await invoice_service.update_invoice(
        invoice_id=invoice_id,
        client=client,
        invoice_number=invoice_number,
        date=date_field,
        due_date=due_date,
        amount=amount.quantize(Decimal("0.01")),
        vat_rate=VatRate(vat_rate),
        description=description,
        status=InvoiceStatus(status),
    )

    if not updated_invoice:
        return HTMLResponse(f"<p>{_('invoice.no_invoices')}</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/_invoice_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "invoice": updated_invoice,
        },
    )


@router.get("/{invoice_id}/pdf", response_model=None)
async def get_invoice_pdf(
    invoice_id: int,
    invoice_service: InvoiceService = Depends(get_invoice_service),
    upload_repo: UploadedDocumentRepository = Depends(get_uploaded_doc_repo),
) -> FileResponse | HTMLResponse:
    """Serve the PDF file for an invoice."""
    # Verify invoice exists
    invoice = await invoice_service.get_invoice(invoice_id)
    if not invoice:
        return HTMLResponse("Invoice not found", status_code=404)

    # Get uploaded document
    uploaded_doc = await upload_repo.get_by_invoice_id(invoice_id)
    if not uploaded_doc:
        return HTMLResponse("No PDF attached to this invoice", status_code=404)

    pdf_path = Path(uploaded_doc.get("file_path", ""))
    if not pdf_path.exists():
        return HTMLResponse("PDF file not found", status_code=404)

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=uploaded_doc.get("filename", f"invoice-{invoice_id}.pdf"),
    )


@router.get("/{invoice_id}/pdf/download", response_model=None)
async def download_invoice_pdf(
    request: Request,
    invoice_id: int,
    invoice_service: InvoiceService = Depends(get_invoice_service),
    upload_repo: UploadedDocumentRepository = Depends(get_uploaded_doc_repo),
) -> FileResponse | HTMLResponse:
    """Download the PDF file for an invoice, or redirect to preview if none exists."""
    from fastapi.responses import RedirectResponse

    # Verify invoice exists
    invoice = await invoice_service.get_invoice(invoice_id)
    if not invoice:
        return HTMLResponse("Invoice not found", status_code=404)

    # Get uploaded document
    uploaded_doc = await upload_repo.get_by_invoice_id(invoice_id)

    # If no PDF exists, redirect to preview modal for PDF generation
    if not uploaded_doc:
        # Return HTML that triggers the preview modal via HTMX
        lang = get_current_language()
        _ = get_translator(lang)
        return templates.TemplateResponse(
            "partials/_invoice_preview_modal.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "invoice": invoice,
                "templates": ["modern", "classic", "minimal"],
                "selected_template": "modern",
            },
        )

    pdf_path = Path(uploaded_doc.get("file_path", ""))
    if not pdf_path.exists():
        # PDF record exists but file is missing - show preview modal
        lang = get_current_language()
        _ = get_translator(lang)
        return templates.TemplateResponse(
            "partials/_invoice_preview_modal.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "invoice": invoice,
                "templates": ["modern", "classic", "minimal"],
                "selected_template": "modern",
            },
        )

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=uploaded_doc.get("filename", f"invoice-{invoice_id}.pdf"),
    )


@router.get("/summary", response_class=HTMLResponse)
async def get_invoice_summary(
    request: Request,
    year: int | None = None,
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Return invoice summary statistics."""
    summary = await invoice_service.get_revenue_summary(year)

    return templates.TemplateResponse(
        "partials/_invoice_summary.html",
        {
            "request": request,
            "summary": summary,
        },
    )


# =============================================================================
# Invoice Template Preview Routes
# =============================================================================

AVAILABLE_TEMPLATES = {
    "dark": {
        "name": "Dark",
        "description": "Sophisticated dark theme with gold accents",
        "template": "partials/_invoice_template_dark.html",
    },
    "professional": {
        "name": "Professional",
        "description": "Zervant-style clean business invoice",
        "template": "partials/_invoice_template_professional.html",
    },
    "modern": {
        "name": "Modern",
        "description": "Minimal design with accent colors",
        "template": "partials/_invoice_template_modern.html",
    },
    "classic": {
        "name": "Classic",
        "description": "Traditional German business letter",
        "template": "partials/_invoice_template_classic.html",
    },
}


@router.get("/templates", response_class=HTMLResponse)
async def get_template_selector(request: Request) -> HTMLResponse:
    """Return the template selector modal/panel."""
    return templates.TemplateResponse(
        "partials/_invoice_template_selector.html",
        {
            "request": request,
            "templates": AVAILABLE_TEMPLATES,
        },
    )


@router.get("/{invoice_id}/preview", response_class=HTMLResponse)
async def preview_invoice(
    request: Request,
    invoice_id: int,
    template: str = Query(default="dark"),
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """
    Preview an invoice with a specific template.
    Returns the rendered invoice HTML for print/PDF generation.
    """
    invoice = await invoice_service.get_invoice(invoice_id)

    if not invoice:
        return HTMLResponse("<p>Rechnung nicht gefunden</p>", status_code=404)

    # Validate template
    if template not in AVAILABLE_TEMPLATES:
        template = "professional"

    # Create invoice items from description (mock for demo)
    items = [
        InvoiceItem(
            description=invoice.description,
            quantity=Decimal("1"),
            unit="Pauschal",
            unit_price=invoice.amount_net,
            service_date=invoice.date,
        )
    ]

    # Parse client address (simple split for demo)
    client_address = []
    if invoice.client:
        # Could be enhanced to parse structured address
        client_address = ["Client Address Line 1", "12345 Client City"]

    # Get sender info from user settings (or fallback to default)
    user_settings = load_settings()
    if user_settings.business_name:
        sender = user_settings.to_sender_info()
    else:
        sender = DEFAULT_SENDER

    return templates.TemplateResponse(
        AVAILABLE_TEMPLATES[template]["template"],
        {
            "request": request,
            "invoice": invoice,
            "sender": sender,
            "items": items,
            "client_address": client_address,
        },
    )


@router.get("/preview-modal/{invoice_id}", response_class=HTMLResponse)
async def get_preview_modal(
    request: Request,
    invoice_id: int,
    invoice_service: InvoiceService = Depends(get_invoice_service),
) -> HTMLResponse:
    """Return the preview modal with template selector and preview area."""
    invoice = await invoice_service.get_invoice(invoice_id)

    if not invoice:
        return HTMLResponse("<p>Rechnung nicht gefunden</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/_invoice_preview_modal.html",
        {
            "request": request,
            "invoice": invoice,
            "templates": AVAILABLE_TEMPLATES,
            "selected_template": "dark",
        },
    )
