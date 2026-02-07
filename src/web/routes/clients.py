"""Client CRUD routes with HTMX patterns."""
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.core.i18n import get_translator
from src.core.models import ClientInput
from src.web.routes.settings import get_current_language
from src.web.services.client import ClientService, get_client_service

router = APIRouter()
templates = Jinja2Templates(directory="src/web/templates")


# =============================================================================
# Client List and CRUD
# =============================================================================


@router.get("", response_class=HTMLResponse)
async def list_clients(
    request: Request,
    client_service: ClientService = Depends(get_client_service),
) -> HTMLResponse:
    """Return client table rows for HTMX swap."""
    clients = await client_service.get_all_clients()

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_client_table.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "clients": clients,
        },
    )


@router.get("/form", response_class=HTMLResponse)
async def get_client_form(request: Request) -> HTMLResponse:
    """Return the client form HTML for HTMX swap."""
    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_client_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
        },
    )


@router.get("/dropdown", response_class=HTMLResponse)
async def get_clients_dropdown(
    request: Request,
    client_service: ClientService = Depends(get_client_service),
) -> HTMLResponse:
    """Return client dropdown options for invoice form."""
    clients = await client_service.get_clients_for_dropdown()

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_client_dropdown.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "clients": clients,
        },
    )


@router.post("/add", response_class=HTMLResponse)
async def add_client(
    request: Request,
    name: Annotated[str, Form()],
    street: Annotated[str, Form()] = "",
    address_details: Annotated[str, Form()] = "",
    zip_code: Annotated[str, Form()] = "",
    city: Annotated[str, Form()] = "",
    country: Annotated[str, Form()] = "DE",
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    vat_id: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    inline: Annotated[bool, Form()] = False,
    client_service: ClientService = Depends(get_client_service),
) -> HTMLResponse:
    """Add a new client.

    If inline=True (from invoice form), returns a success message
    that triggers dropdown refresh.
    Otherwise returns the new client row HTML.
    """
    client_input = ClientInput(
        name=name,
        street=street,
        address_details=address_details,
        zip_code=zip_code,
        city=city,
        country=country.upper()[:2] if country else "DE",
        email=email,
        phone=phone,
        vat_id=vat_id,
        notes=notes,
    )
    new_client = await client_service.create_client(client_input)

    lang = get_current_language()
    _ = get_translator(lang)

    # If created inline from invoice form, return success message
    # The form's JS will handle refreshing the dropdown
    if inline:
        return templates.TemplateResponse(
            "partials/_client_created_success.html",
            {
                "request": request,
                "_": _,
                "lang": lang,
                "client": new_client,
            },
        )

    return templates.TemplateResponse(
        "partials/_client_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "client": new_client,
        },
    )


@router.get("/{client_id}", response_class=HTMLResponse)
async def get_client_details(
    request: Request,
    client_id: int,
    client_service: ClientService = Depends(get_client_service),
) -> HTMLResponse:
    """Return client details card/modal."""
    lang = get_current_language()
    _ = get_translator(lang)

    client = await client_service.get_client(client_id)
    if not client:
        return HTMLResponse(f"<p>{_('client.not_found')}</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/_client_details.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "client": client,
        },
    )


@router.get("/{client_id}/edit", response_class=HTMLResponse)
async def get_edit_client_form(
    request: Request,
    client_id: int,
    client_service: ClientService = Depends(get_client_service),
) -> HTMLResponse:
    """Return the edit client form HTML."""
    lang = get_current_language()
    _ = get_translator(lang)

    client = await client_service.get_client(client_id)
    if not client:
        return HTMLResponse(f"<p>{_('client.not_found')}</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/_client_edit_form.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "client": client,
        },
    )


@router.put("/{client_id}", response_class=HTMLResponse)
async def update_client(
    request: Request,
    client_id: int,
    name: Annotated[str, Form()],
    street: Annotated[str, Form()] = "",
    address_details: Annotated[str, Form()] = "",
    zip_code: Annotated[str, Form()] = "",
    city: Annotated[str, Form()] = "",
    country: Annotated[str, Form()] = "DE",
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    vat_id: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    client_service: ClientService = Depends(get_client_service),
) -> HTMLResponse:
    """Update a client. Returns updated row HTML."""
    lang = get_current_language()
    _ = get_translator(lang)

    client_input = ClientInput(
        name=name,
        street=street,
        address_details=address_details,
        zip_code=zip_code,
        city=city,
        country=country.upper()[:2] if country else "DE",
        email=email,
        phone=phone,
        vat_id=vat_id,
        notes=notes,
    )
    updated_client = await client_service.update_client(client_id, client_input)

    if not updated_client:
        return HTMLResponse(f"<p>{_('client.not_found')}</p>", status_code=404)

    return templates.TemplateResponse(
        "partials/_client_row.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "client": updated_client,
        },
    )


@router.delete("/{client_id}", response_class=HTMLResponse)
async def delete_client(
    client_id: int,
    client_service: ClientService = Depends(get_client_service),
) -> HTMLResponse:
    """Delete a client. Returns empty string for HTMX swap."""
    await client_service.delete_client(client_id)
    return HTMLResponse("")


@router.get("/search/{query}", response_class=HTMLResponse)
async def search_clients(
    request: Request,
    query: str,
    client_service: ClientService = Depends(get_client_service),
) -> HTMLResponse:
    """Search clients by name/city/email. Returns matching rows."""
    clients = await client_service.search_clients(query)

    lang = get_current_language()
    _ = get_translator(lang)

    return templates.TemplateResponse(
        "partials/_client_search_results.html",
        {
            "request": request,
            "_": _,
            "lang": lang,
            "clients": clients,
        },
    )
