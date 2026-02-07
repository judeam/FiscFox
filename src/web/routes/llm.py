"""LLM routes with SSE streaming for FiscFox AI assistant.

Provides endpoints for:
- Chat interface with streaming responses
- Tax law Q&A (RAG)
- Text-to-SQL queries
- AfA suggestions
- ML result explanations
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from src.core.i18n import get_translator, t
from src.llm.config import get_llm_settings
from src.llm.exceptions import (
    LLMError,
    RetrievalError,
    SQLExecutionError,
    SQLValidationError,
)
from src.llm.router import IntentType, get_semantic_router
from src.llm.service import LLMService, get_llm_service
from src.web.routes.settings import get_current_language

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm", tags=["llm"])
templates = Jinja2Templates(directory="src/web/templates")


# =============================================================================
# Request/Response Models
# =============================================================================


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None)
    stream: bool = Field(default=True)


class ChatResponse(BaseModel):
    """Non-streaming chat response."""

    message: str
    intent: str
    confidence: float
    sources: list[dict[str, Any]] = Field(default_factory=list)


class SQLQueryRequest(BaseModel):
    """SQL query request model."""

    question: str = Field(..., min_length=1, max_length=500)


class AfASuggestionRequest(BaseModel):
    """AfA suggestion request model."""

    description: str = Field(..., min_length=1, max_length=500)
    amount: str = Field(..., pattern=r"^\d+([.,]\d{1,2})?$")
    category: str | None = Field(default=None)


# =============================================================================
# Dependencies
# =============================================================================


async def get_llm_or_error() -> LLMService:
    """Get LLM service or raise if not available."""
    settings = get_llm_settings()
    if not settings.enabled:
        raise HTTPException(
            status_code=503,
            detail="LLM features are disabled",
        )

    service = get_llm_service()

    # Load model if not already loaded (lazy loading)
    if not service.is_ready:
        try:
            await service.ensure_loaded()
        except Exception as e:
            logger.error(f"Failed to load LLM model: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"LLM model failed to load: {e}",
            )

    return service


# =============================================================================
# Chat Endpoints
# =============================================================================


@router.post("/chat", response_class=HTMLResponse)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    llm_service: LLMService = Depends(get_llm_or_error),
) -> HTMLResponse:
    """Process chat message and return HTML response.

    For HTMX integration - returns rendered message partial.
    """
    router_instance = get_semantic_router()

    # Route the query
    routing_result = router_instance.route(chat_request.message)

    try:
        # Process based on intent
        response_text = await _process_intent(
            llm_service,
            chat_request.message,
            routing_result.intent,
            routing_result.entities,
            routing_result.suggested_params,
        )

        # Render response as HTML partial
        lang = get_current_language()
        _ = get_translator(lang)

        return templates.TemplateResponse(
            "partials/_ai_message.html",
            {
                "request": request,
                "message": response_text,
                "intent": routing_result.intent.value,
                "confidence": routing_result.confidence,
                "is_user": False,
                "_": _,
            },
        )

    except LLMError as e:
        logger.error(f"LLM error: {e}")
        return templates.TemplateResponse(
            "partials/_ai_message.html",
            {
                "request": request,
                "message": t("ai.error.generic", lang).replace("{error}", e.message),
                "is_error": True,
                "is_user": False,
                "_": _,
            },
        )


@router.get("/stream")
async def stream_chat(
    request: Request,
    message: str,
    llm_service: LLMService = Depends(get_llm_or_error),
) -> EventSourceResponse:
    """Stream chat response via SSE.

    For real-time token streaming with HTMX SSE extension.
    """
    router_instance = get_semantic_router()
    routing_result = router_instance.route(message)

    async def event_generator():
        """Generate SSE events."""
        try:
            # Send intent info first
            yield {
                "event": "intent",
                "data": json.dumps({
                    "intent": routing_result.intent.value,
                    "confidence": routing_result.confidence,
                }),
            }

            # Stream response tokens
            async for token in _stream_intent_response(
                llm_service,
                message,
                routing_result.intent,
                routing_result.entities,
                routing_result.suggested_params,
            ):
                yield {
                    "event": "token",
                    "data": token,
                }

            # Send completion event
            yield {
                "event": "done",
                "data": "",
            }

        except LLMError as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": e.message}),
            }

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())


# =============================================================================
# SQL Query Endpoint
# =============================================================================


@router.post("/sql", response_class=HTMLResponse)
async def sql_query(
    request: Request,
    query_request: SQLQueryRequest,
    llm_service: LLMService = Depends(get_llm_or_error),
) -> HTMLResponse:
    """Execute natural language SQL query.

    Returns rendered results table.
    """
    try:
        import os

        # Import here to avoid circular imports
        from src.llm.agents import get_text2sql_agent

        # Get database path from settings
        db_path = os.environ.get("DATABASE_PATH", "data/FiscFox.db")

        agent = get_text2sql_agent(llm_service, db_path)
        result = await agent.query(query_request.question)

        lang = get_current_language()
        _ = get_translator(lang)

        return templates.TemplateResponse(
            "partials/_ai_sql_result.html",
            {
                "request": request,
                "query": result.query.sql,
                "explanation": result.query.explanation,
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "execution_time_ms": result.execution_time_ms,
                "formatted_answer": result.formatted_answer,
                "_": _,
            },
        )

    except SQLValidationError as e:
        lang = get_current_language()
        _ = get_translator(lang)
        return templates.TemplateResponse(
            "partials/_ai_message.html",
            {
                "request": request,
                "message": t("ai.error.sql_validation", lang).replace("{error}", e.message),
                "is_error": True,
                "is_user": False,
                "_": _,
            },
        )

    except SQLExecutionError as e:
        lang = get_current_language()
        _ = get_translator(lang)
        return templates.TemplateResponse(
            "partials/_ai_message.html",
            {
                "request": request,
                "message": t("ai.error.sql_execution", lang).replace("{error}", e.message),
                "is_error": True,
                "is_user": False,
                "_": _,
            },
        )


# =============================================================================
# AfA Suggestion Endpoint
# =============================================================================


@router.post("/afa-suggest", response_class=HTMLResponse)
async def afa_suggest(
    request: Request,
    afa_request: AfASuggestionRequest,
    llm_service: LLMService = Depends(get_llm_or_error),
) -> HTMLResponse:
    """Get AfA (depreciation) suggestion for an asset.

    Returns rendered suggestion card.
    """
    from decimal import Decimal

    try:
        lang = get_current_language()
        _ = get_translator(lang)

        # Parse amount
        amount = Decimal(afa_request.amount.replace(",", "."))

        # Determine depreciation method based on amount
        # GWG: <= 800 EUR, Pool: 250-1000 EUR, Linear: > 1000 EUR
        if amount <= Decimal("250"):
            method = "sofort"
            useful_life = 0
            explanation = t("ai.afa.explain.sofort", lang)
            tax_reference = "§ 6 Abs. 2 EStG"
        elif amount <= Decimal("800"):
            method = "gwg"
            useful_life = 1
            explanation = t("ai.afa.explain.gwg", lang)
            tax_reference = "§ 6 Abs. 2 EStG"
        elif amount <= Decimal("1000"):
            method = "pool"
            useful_life = 5
            explanation = t("ai.afa.explain.pool", lang)
            tax_reference = "§ 6 Abs. 2a EStG"
        else:
            method = "linear"
            # Estimate useful life based on category
            useful_life = _estimate_useful_life(afa_request.description, afa_request.category)
            explanation = t("ai.afa.explain.linear", lang).replace("{years}", str(useful_life))
            tax_reference = "§ 7 Abs. 1 EStG"

        # Check for digital assets (special 1-year depreciation)
        if _is_digital_asset(afa_request.description):
            method = "digital"
            useful_life = 1
            explanation = t("ai.afa.explain.digital", lang)
            tax_reference = "BMF vom 26.02.2021"

        return templates.TemplateResponse(
            "partials/_ai_afa_suggestion.html",
            {
                "request": request,
                "description": afa_request.description,
                "amount": f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                "method": method,
                "useful_life": useful_life,
                "explanation": explanation,
                "tax_reference": tax_reference,
                "annual_depreciation": f"{(amount / useful_life if useful_life > 0 else amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                "_": _,
            },
        )

    except Exception as e:
        logger.error(f"AfA suggestion error: {e}")
        lang = get_current_language()
        _ = get_translator(lang)
        return templates.TemplateResponse(
            "partials/_ai_message.html",
            {
                "request": request,
                "message": t("ai.error.afa_calculation", lang).replace("{error}", str(e)),
                "is_error": True,
                "is_user": False,
                "_": _,
            },
        )


# =============================================================================
# Status Endpoint
# =============================================================================


@router.get("/status")
async def llm_status() -> dict[str, Any]:
    """Get LLM service status.

    Status values:
    - disabled: LLM features are turned off
    - idle: LLM enabled but model not loaded (will load on first request)
    - loading: Model is actively being loaded
    - ready: Model loaded and ready for inference
    - error: Error state
    """
    settings = get_llm_settings()

    if not settings.enabled:
        return {
            "enabled": False,
            "status": "disabled",
        }

    try:
        service = get_llm_service()
        manager = service.manager

        # Determine proper status
        if service.is_ready:
            status = "ready"
        elif manager.is_loading:
            status = "loading"
        else:
            status = "idle"  # Not loaded yet, will lazy-load on first request

        return {
            "enabled": True,
            "status": status,
            **service.get_status(),
        }
    except Exception as e:
        return {
            "enabled": True,
            "status": "error",
            "error": str(e),
        }


# =============================================================================
# Helper Functions
# =============================================================================


async def _process_intent(
    llm_service: LLMService,
    message: str,
    intent: IntentType,
    entities: Any,
    params: dict[str, Any],
) -> str:
    """Process message based on detected intent.

    Args:
        llm_service: LLM service
        message: User message
        intent: Detected intent
        entities: Extracted entities
        params: Suggested parameters

    Returns:
        Response text
    """
    import os
    db_path = os.environ.get("DATABASE_PATH", "data/FiscFox.db")

    if intent == IntentType.TAX_LAW:
        from src.llm.agents import get_tax_rag_agent
        from src.llm.agents.tax_rag import TaxRAGConfig

        try:
            agent = get_tax_rag_agent(llm_service, db_path)
            config = TaxRAGConfig(
                boost_categories=params.get("boost_categories", []),
            )
            result = await agent.answer(message, config, entities)

            # Format response with sources
            response = result.answer
            if result.sources:
                response += "\n\n**Quellen:**\n"
                for i, src in enumerate(result.sources[:3], 1):
                    response += f"[{i}] {src.citation}\n"

            return response

        except RetrievalError:
            # Fall back to general LLM if RAG fails
            pass

    elif intent == IntentType.FINANCIAL_QUERY:
        from src.llm.agents import get_text2sql_agent

        try:
            agent = get_text2sql_agent(llm_service, db_path)
            result = await agent.query(message, entities=entities)
            return result.formatted_answer
        except (SQLValidationError, SQLExecutionError) as e:
            lang = get_current_language()
            return t("ai.error.sql_generic", lang).replace("{error}", e.message)

    # Default: use base LLM
    lang = get_current_language()
    if lang == "en":
        system_prompt = """You are a helpful assistant for German freelancers and self-employed professionals.
You help with questions about bookkeeping, taxes, and finances.
Answer in English, precisely and in a friendly manner.
For complex tax questions, refer to a tax advisor."""
    else:
        system_prompt = """Du bist ein hilfreicher Assistent für deutsche Freelancer und Selbstständige.
Du hilfst bei Fragen zu Buchhaltung, Steuern und Finanzen.
Antworte auf Deutsch, präzise und freundlich.
Verweise bei komplexen steuerlichen Fragen auf einen Steuerberater."""

    response = await llm_service.generate(
        prompt=message,
        system_prompt=system_prompt,
        max_tokens=1000,
    )
    return response.content


async def _stream_intent_response(
    llm_service: LLMService,
    message: str,
    intent: IntentType,
    entities: Any,
    params: dict[str, Any],
):
    """Stream response based on intent.

    Yields tokens as they're generated.
    """
    import os
    db_path = os.environ.get("DATABASE_PATH", "data/FiscFox.db")

    if intent == IntentType.TAX_LAW:
        from src.llm.agents import get_tax_rag_agent
        from src.llm.agents.tax_rag import TaxRAGConfig

        try:
            agent = get_tax_rag_agent(llm_service, db_path)
            config = TaxRAGConfig(
                boost_categories=params.get("boost_categories", []),
            )
            async for token in agent.answer_stream(message, config, entities):
                yield token
            return
        except (RetrievalError, Exception):
            pass

    elif intent == IntentType.FINANCIAL_QUERY:
        # Text-to-SQL doesn't support streaming, so yield complete response
        from src.llm.agents import get_text2sql_agent

        try:
            agent = get_text2sql_agent(llm_service, db_path)
            result = await agent.query(message, entities=entities)

            # Yield formatted answer
            yield result.formatted_answer

            # Yield table summary if there are results
            if result.rows:
                yield f"\n\n({result.row_count} "
                lang = get_current_language()
                if result.row_count == 1:
                    yield t("ai.sql.row", lang)
                else:
                    yield t("ai.sql.rows", lang)
                yield ")"
            return
        except (SQLValidationError, SQLExecutionError) as e:
            lang = get_current_language()
            yield t("ai.error.sql_generic", lang).replace("{error}", e.message)
            return
        except Exception as e:
            logger.error(f"Text-to-SQL streaming error: {e}")
            lang = get_current_language()
            # Check for timeout
            if "timeout" in str(e).lower():
                yield t("ai.error.timeout", lang)
            else:
                yield t("ai.error.sql_generic", lang).replace("{error}", str(e))
            return

    # Default streaming
    lang = get_current_language()
    if lang == "en":
        system_prompt = """You are a helpful assistant for German freelancers.
Answer in English, precisely and in a friendly manner."""
    else:
        system_prompt = """Du bist ein hilfreicher Assistent für deutsche Freelancer.
Antworte auf Deutsch, präzise und freundlich."""

    async for token in llm_service.generate_stream(
        prompt=message,
        system_prompt=system_prompt,
        max_tokens=1000,
    ):
        yield token


def _estimate_useful_life(description: str, category: str | None) -> int:
    """Estimate useful life based on asset description."""
    description_lower = description.lower()

    # Standard useful lives per AfA-Tabelle
    if any(kw in description_lower for kw in ["laptop", "computer", "pc", "rechner"]):
        return 3
    elif any(kw in description_lower for kw in ["monitor", "bildschirm", "display"]):
        return 3
    elif any(kw in description_lower for kw in ["drucker", "printer", "scanner"]):
        return 3
    elif any(kw in description_lower for kw in ["handy", "smartphone", "telefon"]):
        return 5
    elif any(kw in description_lower for kw in ["möbel", "schreibtisch", "stuhl", "regal"]):
        return 13
    elif any(kw in description_lower for kw in ["kamera", "objektiv", "photo"]):
        return 7
    elif any(kw in description_lower for kw in ["software", "lizenz"]):
        return 3
    elif category == "hardware":
        return 3
    elif category == "software":
        return 3
    else:
        return 5  # Default


def _is_digital_asset(description: str) -> bool:
    """Check if asset qualifies as digital (BMF 2021 rules)."""
    description_lower = description.lower()

    digital_keywords = [
        "computer", "laptop", "notebook", "pc", "rechner",
        "monitor", "bildschirm", "display",
        "drucker", "printer", "scanner",
        "software", "lizenz",
        "tablet", "ipad",
        "server", "nas", "festplatte", "ssd",
        "router", "switch", "netzwerk",
    ]

    return any(kw in description_lower for kw in digital_keywords)
