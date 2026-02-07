"""Tax RAG Agent for German tax law Q&A.

Combines RAG retrieval with LLM generation for accurate,
citation-backed answers to German tax law questions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from src.core.i18n import t
from src.llm.retrieval import (
    HybridRetriever,
    RetrievalConfig,
    RetrievalResponse,
    SearchMode,
    get_hybrid_retriever,
)
from src.llm.router import ExtractedEntities

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from src.llm.service import LLMService

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class TaxAnswerSource(BaseModel):
    """Source citation for tax answer."""

    citation: str = Field(..., description="Legal citation (e.g., § 7 Abs. 1 EStG)")
    title: str = Field(default="", description="Section title")
    relevance: float = Field(default=0.0, description="Relevance score 0-1")
    excerpt: str = Field(default="", description="Relevant excerpt")


class TaxAnswer(BaseModel):
    """Structured tax law answer."""

    answer: str = Field(..., description="Main answer text")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")
    sources: list[TaxAnswerSource] = Field(default_factory=list, description="Supporting sources")
    disclaimer: str = Field(
        default="Diese Auskunft ersetzt keine professionelle steuerliche Beratung.",
        description="Legal disclaimer",
    )

    # Metadata
    query_understood: bool = Field(default=True, description="Whether query was understood")
    needs_clarification: str | None = Field(default=None, description="Clarification needed")


@dataclass
class TaxRAGConfig:
    """Configuration for Tax RAG Agent."""

    # Retrieval settings
    retrieval_limit: int = 10
    min_confidence: float = 0.3
    include_parent_context: bool = True

    # Generation settings
    max_tokens: int = 1500
    temperature: float = 0.1
    include_sources: bool = True
    require_citations: bool = True

    # Category boosting
    boost_categories: list[str] = field(default_factory=list)
    category_boost_factor: float = 1.5

    # Language setting
    lang: str = "de"


# =============================================================================
# System Prompts
# =============================================================================

SYSTEM_PROMPT_DE = """Du bist ein Experte für deutsches Steuerrecht und hilfst Freiberuflern bei steuerlichen Fragen.

WICHTIGE REGELN:
1. Antworte NUR basierend auf den bereitgestellten Quellen
2. Zitiere IMMER die relevanten Paragraphen (z.B. § 7 Abs. 1 EStG)
3. Wenn die Quellen keine Antwort enthalten, sage das ehrlich
4. Gib KEINE Steuerberatung - verweise auf Steuerberater für konkrete Fälle
5. Antworte auf Deutsch in klarer, verständlicher Sprache

FORMAT:
- Beginne mit einer direkten Antwort
- Erkläre dann die rechtliche Grundlage
- Nenne die relevanten Quellen am Ende

KONTEXT (Relevante Gesetzestexte):
{context}

Beantworte die Frage des Nutzers basierend auf diesem Kontext."""

SYSTEM_PROMPT_EN = """You are an expert in German tax law helping freelancers with tax questions.

IMPORTANT RULES:
1. Answer ONLY based on the provided sources
2. ALWAYS cite relevant paragraphs (e.g., § 7 Abs. 1 EStG)
3. If sources don't contain an answer, say so honestly
4. Do NOT provide tax advice - refer to tax consultants for specific cases
5. Answer in German in clear, understandable language

FORMAT:
- Start with a direct answer
- Then explain the legal basis
- List relevant sources at the end

CONTEXT (Relevant legal texts):
{context}

Answer the user's question based on this context."""


def get_no_context_response(lang: str = "de") -> str:
    """Get the no-context response in the appropriate language."""
    return f"""{t("ai.rag.no_context", lang)}

{t("ai.rag.no_context_reasons", lang)}
- {t("ai.rag.no_context_reason1", lang)}
- {t("ai.rag.no_context_reason2", lang)}

{t("ai.rag.recommendations", lang)}
- {t("ai.rag.recommend_advisor", lang)}
- {t("ai.rag.recommend_law", lang)}
- {t("ai.rag.recommend_office", lang)}"""


# Keep old constant for backward compatibility
NO_CONTEXT_RESPONSE = get_no_context_response("de")


# =============================================================================
# Tax RAG Agent
# =============================================================================


class TaxRAGAgent:
    """Agent for German tax law Q&A with RAG.

    Combines:
    - Hybrid retrieval (vector + keyword) for relevant tax law passages
    - LLM generation for natural language answers
    - Citation tracking for source attribution
    """

    def __init__(
        self,
        llm_service: LLMService,
        retriever: HybridRetriever | None = None,
        db_path: str | None = None,
    ):
        """Initialize Tax RAG Agent.

        Args:
            llm_service: LLM service for generation
            retriever: Hybrid retriever (creates new if None)
            db_path: Database path (required if retriever is None)
        """
        self._llm = llm_service
        self._retriever = retriever or (
            get_hybrid_retriever(db_path) if db_path else None
        )

    async def answer(
        self,
        question: str,
        config: TaxRAGConfig | None = None,
        entities: ExtractedEntities | None = None,
    ) -> TaxAnswer:
        """Generate answer to tax law question.

        Args:
            question: User's tax question
            config: Agent configuration
            entities: Pre-extracted entities from router

        Returns:
            TaxAnswer with answer, confidence, and sources
        """
        config = config or TaxRAGConfig()
        start_time = datetime.now()

        # Build retrieval config from agent config
        retrieval_config = RetrievalConfig(
            search_mode=SearchMode.HYBRID,
            final_limit=config.retrieval_limit,
            include_parent=config.include_parent_context,
            boost_categories=config.boost_categories,
            category_boost=config.category_boost_factor,
            min_score=config.min_confidence * 0.5,  # Lower threshold for retrieval
        )

        # Apply entity-based filtering
        if entities and entities.law_types:
            retrieval_config.source_types = [lt.lower() for lt in entities.law_types]

        # Retrieve relevant context
        if self._retriever is None:
            logger.error("Retriever not initialized")
            return TaxAnswer(
                answer=NO_CONTEXT_RESPONSE,
                confidence=0.0,
                query_understood=False,
            )

        retrieval_response = await self._retriever.search(question, retrieval_config)

        # Check if we have sufficient context
        if not retrieval_response.results or retrieval_response.top_score < config.min_confidence:
            logger.info(f"Insufficient context for question: {question[:50]}...")
            return TaxAnswer(
                answer=get_no_context_response(config.lang),
                confidence=retrieval_response.top_score,
                query_understood=True,
                needs_clarification=t("ai.rag.no_sources", config.lang),
            )

        # Build sources list
        sources = [
            TaxAnswerSource(
                citation=r.citation,
                title=r.title,
                relevance=r.rrf_score,
                excerpt=r.content[:200] + "..." if len(r.content) > 200 else r.content,
            )
            for r in retrieval_response.results
        ]

        # Generate answer with LLM (select prompt based on language)
        if config.lang == "en":
            system_prompt = SYSTEM_PROMPT_EN.format(context=retrieval_response.combined_context)
        else:
            system_prompt = SYSTEM_PROMPT_DE.format(context=retrieval_response.combined_context)

        try:
            response = await self._llm.generate(
                prompt=question,
                system_prompt=system_prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                use_cache=True,
            )
            answer_text = response.content

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return TaxAnswer(
                answer=t("ai.rag.generation_error", config.lang).replace("{error}", str(e)),
                confidence=0.0,
                sources=sources,
            )

        # Calculate confidence based on retrieval quality and response
        confidence = self._calculate_confidence(retrieval_response, answer_text)

        # Log query for analytics
        try:
            await self._retriever.log_query(
                question,
                "tax_law",
                retrieval_response,
                answer_text,
            )
        except Exception as e:
            logger.warning(f"Failed to log query: {e}")

        return TaxAnswer(
            answer=answer_text,
            confidence=confidence,
            sources=sources if config.include_sources else [],
        )

    async def answer_stream(
        self,
        question: str,
        config: TaxRAGConfig | None = None,
        entities: ExtractedEntities | None = None,
    ) -> AsyncIterator[str]:
        """Generate streaming answer to tax law question.

        Args:
            question: User's tax question
            config: Agent configuration
            entities: Pre-extracted entities

        Yields:
            Answer tokens as they're generated
        """
        config = config or TaxRAGConfig()

        # Build retrieval config
        retrieval_config = RetrievalConfig(
            search_mode=SearchMode.HYBRID,
            final_limit=config.retrieval_limit,
            include_parent=config.include_parent_context,
            boost_categories=config.boost_categories,
            category_boost=config.category_boost_factor,
        )

        if entities and entities.law_types:
            retrieval_config.source_types = [lt.lower() for lt in entities.law_types]

        # Retrieve context
        if self._retriever is None:
            yield get_no_context_response(config.lang)
            return

        retrieval_response = await self._retriever.search(question, retrieval_config)

        if not retrieval_response.results or retrieval_response.top_score < config.min_confidence:
            yield get_no_context_response(config.lang)
            return

        # Build system prompt (select based on language)
        if config.lang == "en":
            system_prompt = SYSTEM_PROMPT_EN.format(context=retrieval_response.combined_context)
        else:
            system_prompt = SYSTEM_PROMPT_DE.format(context=retrieval_response.combined_context)

        # Stream response
        try:
            async for token in self._llm.generate_stream(
                prompt=question,
                system_prompt=system_prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            ):
                yield token

            # Append sources if configured
            if config.include_sources and retrieval_response.results:
                sources_label = t("ai.rag.sources", config.lang)
                yield f"\n\n---\n**{sources_label}:**\n"
                for i, result in enumerate(retrieval_response.results[:3], 1):
                    yield f"[{i}] {result.citation}\n"

        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            error_msg = t("ai.error.generic", config.lang).replace("{error}", str(e))
            yield f"\n\n[{error_msg}]"

    def _calculate_confidence(
        self,
        retrieval: RetrievalResponse,
        answer: str,
    ) -> float:
        """Calculate confidence score for answer.

        Args:
            retrieval: Retrieval response
            answer: Generated answer text

        Returns:
            Confidence score 0-1
        """
        # Base confidence from retrieval quality
        retrieval_confidence = min(1.0, retrieval.top_score * 2)

        # Check for citations in answer (boosts confidence)
        citation_count = answer.count("§")
        citation_bonus = min(0.2, citation_count * 0.05)

        # Check for uncertainty markers (reduces confidence)
        uncertainty_markers = [
            "möglicherweise", "eventuell", "nicht sicher", "unklar",
            "keine relevanten", "nicht gefunden", "kann nicht",
        ]
        uncertainty_penalty = sum(0.1 for m in uncertainty_markers if m in answer.lower())

        # Combine scores
        confidence = retrieval_confidence + citation_bonus - uncertainty_penalty
        return max(0.0, min(1.0, confidence))

    async def get_related_sections(
        self,
        category: str,
        limit: int = 5,
    ) -> list[TaxAnswerSource]:
        """Get tax law sections related to an expense category.

        Args:
            category: Expense category
            limit: Maximum sections

        Returns:
            List of relevant sources
        """
        if self._retriever is None:
            return []

        chunks = await self._retriever.get_category_relevant_chunks(category, limit)

        return [
            TaxAnswerSource(
                citation=c.citation,
                title=c.title,
                relevance=c.rrf_score,
                excerpt=c.content[:200] + "..." if len(c.content) > 200 else c.content,
            )
            for c in chunks
        ]

    def get_status(self) -> dict[str, Any]:
        """Get agent status.

        Returns:
            Status dict
        """
        return {
            "ready": self._retriever is not None and self._llm.is_ready,
            "retriever_available": self._retriever is not None,
            "llm_ready": self._llm.is_ready,
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_tax_rag_agent: TaxRAGAgent | None = None


def get_tax_rag_agent(
    llm_service: LLMService | None = None,
    db_path: str | None = None,
) -> TaxRAGAgent:
    """Get or create the Tax RAG Agent singleton.

    Args:
        llm_service: LLM service (required on first call)
        db_path: Database path (required on first call)

    Returns:
        TaxRAGAgent singleton instance
    """
    global _tax_rag_agent
    if _tax_rag_agent is None:
        if llm_service is None:
            raise ValueError("llm_service required for first agent initialization")
        _tax_rag_agent = TaxRAGAgent(llm_service, db_path=db_path)
    return _tax_rag_agent
