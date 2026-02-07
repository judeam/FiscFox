"""Upload routes for PDF invoice uploads with HTMX patterns."""
import logging
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.extraction.models import get_confidence_level
from src.core.i18n import get_translator
from src.db.repository import (
    ClientRepository,
    InvoiceRepository,
    UploadedDocumentRepository,
    get_client_repo,
    get_invoice_repo,
    get_uploaded_doc_repo,
)
from src.web.middleware import limiter
from src.web.middleware.rate_limit import UPLOAD_LIMIT
from src.web.routes.settings import get_current_language
from src.web.services.upload import UploadError, UploadService

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


def get_upload_service(
    repo: UploadedDocumentRepository = Depends(get_uploaded_doc_repo),
) -> UploadService:
    """Dependency to get UploadService."""
    return UploadService(repo)


@router.get("/form", response_class=HTMLResponse)
async def get_upload_form(request: Request) -> HTMLResponse:
    """Return the upload dropzone form HTML."""
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_upload_dropzone.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
        },
    )


@router.post("/invoice", response_class=HTMLResponse)
@limiter.limit(UPLOAD_LIMIT)
async def upload_invoice(
    request: Request,
    file: UploadFile = File(...),
    upload_service: UploadService = Depends(get_upload_service),
    client_repo: ClientRepository = Depends(get_client_repo),
) -> HTMLResponse:
    """
    Handle PDF invoice upload.

    1. Validate and store the file
    2. Extract invoice data
    3. Find matching clients
    4. Return review form with extracted data and matched clients
    """
    lang = get_current_language()
    _ = get_translator(lang)

    logger.info(f"Upload request received: filename={file.filename}, content_type={file.content_type}")

    try:
        # Read file content
        file_content = await file.read()
        logger.info(f"Read {len(file_content)} bytes from uploaded file")

        # Process upload
        doc_id, result = await upload_service.process_upload(
            file_content=file_content,
            filename=file.filename or "uploaded.pdf",
            content_type=file.content_type or "application/pdf",
        )

        # Get confidence level for display
        confidence = result.data.overall_confidence if result.data else 0
        confidence_level = get_confidence_level(confidence)

        # Find matching clients
        matched_clients = []
        if result.data:
            matched_clients = await upload_service.find_matching_clients(
                result.data, client_repo
            )

        return templates.TemplateResponse(
            "partials/_extraction_review.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "doc_id": doc_id,
                "extraction": result.data,
                "confidence": confidence,
                "confidence_level": confidence_level,
                "confidence_percent": int(confidence * 100),
                "method": result.method_used.value,
                "warnings": result.warnings,
                "errors": result.errors,
                "matched_clients": matched_clients,
                "vat_rates": [
                    ("0.00", _("vat.zero")),
                    ("0.19", _("vat.standard")),
                    ("0.07", _("vat.reduced")),
                ],
            },
        )

    except UploadError as e:
        logger.warning(f"Upload failed: {e}")
        return templates.TemplateResponse(
            "partials/_upload_error.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "error": str(e),
            },
            status_code=400,
        )
    except Exception as e:
        logger.exception(f"Unexpected upload error: {e}")
        return templates.TemplateResponse(
            "partials/_upload_error.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "error": f"An unexpected error occurred: {str(e)}",
            },
            status_code=500,
        )


@router.get("/{doc_id}/review", response_class=HTMLResponse)
async def get_review_form(
    request: Request,
    doc_id: int,
    upload_service: UploadService = Depends(get_upload_service),
    client_repo: ClientRepository = Depends(get_client_repo),
) -> HTMLResponse:
    """Return the extraction review form for an existing upload."""
    lang = get_current_language()
    _ = get_translator(lang)

    doc, extraction = await upload_service.get_extraction_data(doc_id)

    if not doc:
        return templates.TemplateResponse(
            "partials/_upload_error.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "error": "Upload not found",
            },
            status_code=404,
        )

    confidence = extraction.overall_confidence if extraction else 0
    confidence_level = get_confidence_level(confidence)

    # Find matching clients
    matched_clients = []
    if extraction:
        matched_clients = await upload_service.find_matching_clients(
            extraction, client_repo
        )

    return templates.TemplateResponse(
        "partials/_extraction_review.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "doc_id": doc_id,
            "extraction": extraction,
            "confidence": confidence,
            "confidence_level": confidence_level,
            "confidence_percent": int(confidence * 100),
            "method": doc.get("extraction_method", "unknown"),
            "warnings": [],
            "errors": [],
            "matched_clients": matched_clients,
            "vat_rates": [
                ("0.00", _("vat.zero")),
                ("0.19", _("vat.standard")),
                ("0.07", _("vat.reduced")),
            ],
        },
    )


@router.post("/{doc_id}/retry", response_class=HTMLResponse)
async def retry_extraction(
    request: Request,
    doc_id: int,
    force_ocr: Annotated[bool, Form()] = False,
    upload_service: UploadService = Depends(get_upload_service),
    client_repo: ClientRepository = Depends(get_client_repo),
) -> HTMLResponse:
    """Retry extraction with different settings."""
    lang = get_current_language()
    _ = get_translator(lang)

    try:
        result = await upload_service.retry_extraction(doc_id, force_ocr=force_ocr)

        confidence = result.data.overall_confidence if result.data else 0
        confidence_level = get_confidence_level(confidence)

        # Find matching clients
        matched_clients = []
        if result.data:
            matched_clients = await upload_service.find_matching_clients(
                result.data, client_repo
            )

        return templates.TemplateResponse(
            "partials/_extraction_review.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "doc_id": doc_id,
                "extraction": result.data,
                "confidence": confidence,
                "confidence_level": confidence_level,
                "confidence_percent": int(confidence * 100),
                "method": result.method_used.value,
                "warnings": result.warnings,
                "errors": result.errors,
                "matched_clients": matched_clients,
                "vat_rates": [
                    ("0.00", _("vat.zero")),
                    ("0.19", _("vat.standard")),
                    ("0.07", _("vat.reduced")),
                ],
            },
        )

    except UploadError as e:
        return templates.TemplateResponse(
            "partials/_upload_error.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "error": str(e),
            },
            status_code=400,
        )


@router.post("/{doc_id}/confirm", response_class=HTMLResponse)
async def confirm_extraction(
    request: Request,
    doc_id: int,
    client_name: Annotated[str, Form()] = "",
    invoice_number: Annotated[str, Form()] = "",
    invoice_date: Annotated[str, Form()] = "",
    due_date: Annotated[str, Form()] = "",
    amount_gross: Annotated[str, Form()] = "",
    amount_net: Annotated[str, Form()] = "",
    vat_rate: Annotated[str, Form()] = "0.19",
    description: Annotated[str, Form()] = "",
    client_street: Annotated[str, Form()] = "",
    client_zip_code: Annotated[str, Form()] = "",
    client_city: Annotated[str, Form()] = "",
    client_country: Annotated[str, Form()] = "DE",
    client_vat_id: Annotated[str, Form()] = "",
    client_email: Annotated[str, Form()] = "",
    client_phone: Annotated[str, Form()] = "",
    existing_client_id: Annotated[int | None, Form()] = None,
    upload_service: UploadService = Depends(get_upload_service),
    invoice_repo: InvoiceRepository = Depends(get_invoice_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
) -> HTMLResponse:
    """
    Confirm extraction and create invoice.

    If existing_client_id is provided, uses that client.
    Otherwise, creates a new client with provided details.

    Returns success message with OOB swap to update invoice table.
    """
    lang = get_current_language()
    _ = get_translator(lang)

    try:
        form_data = {
            "client_name": client_name,
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "due_date": due_date,
            "amount_gross": amount_gross,
            "amount_net": amount_net,
            "vat_rate": vat_rate,
            "description": description,
            "client_street": client_street,
            "client_zip_code": client_zip_code,
            "client_city": client_city,
            "client_country": client_country,
            "client_vat_id": client_vat_id,
            "client_email": client_email,
            "client_phone": client_phone,
            "existing_client_id": existing_client_id,
        }

        invoice_id = await upload_service.confirm_and_create_invoice(
            doc_id=doc_id,
            form_data=form_data,
            invoice_repo=invoice_repo,
            client_repo=client_repo,
        )

        # Return success with OOB swap to refresh invoice table
        return templates.TemplateResponse(
            "partials/_upload_success.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "invoice_id": invoice_id,
                "invoice_number": invoice_number,
            },
        )

    except UploadError as e:
        return templates.TemplateResponse(
            "partials/_upload_error.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "error": str(e),
            },
            status_code=400,
        )
    except sqlite3.IntegrityError as e:
        error_msg = str(e)
        if "invoice_number" in error_msg:
            error_msg = _("upload.error.duplicate_invoice_number") if _ else f"Invoice number '{invoice_number}' already exists."
        else:
            error_msg = _("upload.error.database_constraint") if _ else "Database constraint violation. Please check your data."
        return templates.TemplateResponse(
            "partials/_upload_error.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "error": error_msg,
            },
            status_code=400,
        )


@router.delete("/{doc_id}", response_class=HTMLResponse)
async def cancel_upload(
    doc_id: int,
    upload_service: UploadService = Depends(get_upload_service),
) -> HTMLResponse:
    """
    Cancel upload and delete file.

    Returns empty string for HTMX swap (removes the review form).
    """
    try:
        await upload_service.delete_upload(doc_id)
        return HTMLResponse("")
    except UploadError as e:
        return HTMLResponse(f"<p class='text-red-500'>{str(e)}</p>", status_code=400)


@router.get("/pending", response_class=HTMLResponse)
async def list_pending_uploads(
    request: Request,
    upload_repo: UploadedDocumentRepository = Depends(get_uploaded_doc_repo),
) -> HTMLResponse:
    """List all pending/unconfirmed uploads."""
    lang = get_current_language()
    _ = get_translator(lang)

    pending = await upload_repo.get_unconfirmed()

    return templates.TemplateResponse(
        "partials/_upload_pending_list.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "uploads": pending,
        },
    )
