"""Hybrid retrieval system for German tax law RAG.

Combines vector similarity search (sqlite-vec) with keyword search (FTS5)
using Reciprocal Rank Fusion (RRF) for optimal retrieval.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import aiosqlite
import numpy as np

from src.llm.embeddings import EMBEDDING_DIM, EmbeddingService, get_embedding_service
from src.llm.exceptions import RetrievalError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# RRF constant k (standard value from literature)
RRF_K = 60

# Default limits
DEFAULT_VECTOR_LIMIT = 20
DEFAULT_FTS_LIMIT = 20
DEFAULT_FINAL_LIMIT = 10


class SearchMode(StrEnum):
    """Search mode for retrieval."""

    HYBRID = "hybrid"  # Vector + FTS5 with RRF fusion
    VECTOR_ONLY = "vector"  # Vector similarity only
    KEYWORD_ONLY = "keyword"  # FTS5 keyword only


@dataclass
class RetrievalResult:
    """Single retrieval result with metadata."""

    chunk_id: int
    content: str
    citation: str
    title: str

    # Scores
    rrf_score: float
    vector_rank: int | None = None
    fts_rank: int | None = None

    # Parent context
    parent_chunk_id: int | None = None
    parent_content: str | None = None
    parent_citation: str | None = None

    # Source metadata
    source_id: int | None = None
    source_type: str | None = None
    effective_date: str | None = None

    # Token count for context management
    token_count: int | None = None


@dataclass
class RetrievalResponse:
    """Complete retrieval response."""

    query: str
    results: list[RetrievalResult]
    search_mode: SearchMode
    total_candidates: int

    # Timing
    retrieval_time_ms: float

    # Quality metrics
    top_score: float = 0.0
    avg_score: float = 0.0

    # Context for LLM
    combined_context: str = ""
    total_tokens: int = 0


@dataclass
class RetrievalConfig:
    """Configuration for retrieval operations."""

    # Search parameters
    search_mode: SearchMode = SearchMode.HYBRID
    vector_limit: int = DEFAULT_VECTOR_LIMIT
    fts_limit: int = DEFAULT_FTS_LIMIT
    final_limit: int = DEFAULT_FINAL_LIMIT

    # RRF weights (1.0 = equal weight)
    vector_weight: float = 1.0
    fts_weight: float = 1.0

    # Context options
    include_parent: bool = True
    max_context_tokens: int = 4000

    # Category boosting
    category_boost: float = 1.5  # Boost factor for category-relevant results
    boost_categories: list[str] = field(default_factory=list)

    # Filtering
    source_types: list[str] | None = None  # Filter to specific source types
    min_score: float = 0.0  # Minimum RRF score threshold


class HybridRetriever:
    """Hybrid retrieval with RRF fusion.

    Combines:
    - sqlite-vec for vector similarity search (semantic matching)
    - FTS5 for keyword search (BM25 ranking)
    - Reciprocal Rank Fusion for combining results

    Features:
    - Parent chunk retrieval for full context
    - Category-aware boosting
    - Token counting for context management
    - Query history logging
    """

    def __init__(
        self,
        db_path: str,
        embedding_service: EmbeddingService | None = None,
    ):
        """Initialize hybrid retriever.

        Args:
            db_path: Path to SQLite database with RAG tables
            embedding_service: Embedding service (creates new if None)
        """
        self._db_path = db_path
        self._embedding_service = embedding_service or get_embedding_service()

    async def search(
        self,
        query: str,
        config: RetrievalConfig | None = None,
    ) -> RetrievalResponse:
        """Perform hybrid search with RRF fusion.

        Args:
            query: Search query text
            config: Retrieval configuration

        Returns:
            RetrievalResponse with ranked results

        Raises:
            RetrievalError: If search fails
        """
        config = config or RetrievalConfig()
        start_time = datetime.now()

        try:
            # Generate query embedding
            query_embedding = await self._embedding_service.embed_query(query)

            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row

                # Perform searches based on mode
                if config.search_mode == SearchMode.VECTOR_ONLY:
                    vector_results = await self._vector_search(
                        db, query_embedding, config.vector_limit
                    )
                    fts_results = []
                elif config.search_mode == SearchMode.KEYWORD_ONLY:
                    vector_results = []
                    fts_results = await self._fts_search(db, query, config.fts_limit)
                else:  # HYBRID
                    # Run both searches concurrently
                    vector_results, fts_results = await asyncio.gather(
                        self._vector_search(db, query_embedding, config.vector_limit),
                        self._fts_search(db, query, config.fts_limit),
                    )

                # Apply RRF fusion
                fused_results = self._rrf_fusion(
                    vector_results,
                    fts_results,
                    config.vector_weight,
                    config.fts_weight,
                )

                # Apply category boosting if configured
                if config.boost_categories:
                    fused_results = await self._apply_category_boost(
                        db, fused_results, config.boost_categories, config.category_boost
                    )

                # Filter by minimum score
                if config.min_score > 0:
                    fused_results = [
                        r for r in fused_results if r["rrf_score"] >= config.min_score
                    ]

                # Apply final limit
                fused_results = fused_results[: config.final_limit]

                # Fetch full chunk data and parent context
                results = await self._fetch_results(
                    db, fused_results, config.include_parent
                )

                # Filter by source types if specified
                if config.source_types:
                    results = [
                        r for r in results if r.source_type in config.source_types
                    ]

        except Exception as e:
            raise RetrievalError(str(e), query) from e

        # Calculate timing
        retrieval_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Calculate quality metrics
        top_score = results[0].rrf_score if results else 0.0
        avg_score = (
            sum(r.rrf_score for r in results) / len(results) if results else 0.0
        )

        # Build combined context for LLM
        combined_context, total_tokens = self._build_context(
            results, config.max_context_tokens
        )

        return RetrievalResponse(
            query=query,
            results=results,
            search_mode=config.search_mode,
            total_candidates=len(vector_results) + len(fts_results),
            retrieval_time_ms=retrieval_time_ms,
            top_score=top_score,
            avg_score=avg_score,
            combined_context=combined_context,
            total_tokens=total_tokens,
        )

    async def _vector_search(
        self,
        db: aiosqlite.Connection,
        query_embedding: np.ndarray,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Perform vector similarity search.

        Args:
            db: Database connection
            query_embedding: Query embedding vector
            limit: Maximum results

        Returns:
            List of {chunk_id, rank, distance}
        """
        # Serialize embedding to bytes for sqlite-vec
        embedding_bytes = self._serialize_embedding(query_embedding)

        # sqlite-vec query using vec_distance_L2
        query = """
            SELECT
                chunk_id,
                vec_distance_L2(embedding, ?) as distance
            FROM tax_law_vectors
            ORDER BY distance ASC
            LIMIT ?
        """

        results = []
        try:
            async with db.execute(query, (embedding_bytes, limit)) as cursor:
                rank = 1
                async for row in cursor:
                    results.append(
                        {
                            "chunk_id": row["chunk_id"],
                            "rank": rank,
                            "distance": row["distance"],
                        }
                    )
                    rank += 1
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            # Return empty results - hybrid search can still use FTS

        return results

    async def _fts_search(
        self,
        db: aiosqlite.Connection,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Perform FTS5 keyword search.

        Args:
            db: Database connection
            query: Search query text
            limit: Maximum results

        Returns:
            List of {chunk_id, rank, bm25_score}
        """
        # Escape special FTS5 characters and prepare query
        fts_query = self._prepare_fts_query(query)

        # FTS5 query with BM25 ranking
        query_sql = """
            SELECT
                m.chunk_id,
                bm25(tax_law_fts) as bm25_score
            FROM tax_law_fts f
            JOIN tax_law_fts_map m ON f.rowid = m.fts_rowid
            WHERE tax_law_fts MATCH ?
            ORDER BY bm25_score
            LIMIT ?
        """

        results = []
        try:
            async with db.execute(query_sql, (fts_query, limit)) as cursor:
                rank = 1
                async for row in cursor:
                    results.append(
                        {
                            "chunk_id": row["chunk_id"],
                            "rank": rank,
                            "bm25_score": row["bm25_score"],
                        }
                    )
                    rank += 1
        except Exception as e:
            logger.warning(f"FTS search failed: {e}")
            # Return empty results - hybrid search can still use vector

        return results

    def _rrf_fusion(
        self,
        vector_results: list[dict[str, Any]],
        fts_results: list[dict[str, Any]],
        vector_weight: float = 1.0,
        fts_weight: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Fuse results using Reciprocal Rank Fusion.

        RRF Score = sum(weight / (k + rank)) for each result set

        Args:
            vector_results: Results from vector search
            fts_results: Results from FTS search
            vector_weight: Weight for vector results
            fts_weight: Weight for FTS results

        Returns:
            Fused results sorted by RRF score
        """
        # Build chunk_id -> scores mapping
        scores: dict[int, dict[str, Any]] = {}

        # Add vector results
        for r in vector_results:
            chunk_id = r["chunk_id"]
            if chunk_id not in scores:
                scores[chunk_id] = {
                    "chunk_id": chunk_id,
                    "rrf_score": 0.0,
                    "vector_rank": None,
                    "fts_rank": None,
                }
            scores[chunk_id]["vector_rank"] = r["rank"]
            scores[chunk_id]["rrf_score"] += vector_weight / (RRF_K + r["rank"])

        # Add FTS results
        for r in fts_results:
            chunk_id = r["chunk_id"]
            if chunk_id not in scores:
                scores[chunk_id] = {
                    "chunk_id": chunk_id,
                    "rrf_score": 0.0,
                    "vector_rank": None,
                    "fts_rank": None,
                }
            scores[chunk_id]["fts_rank"] = r["rank"]
            scores[chunk_id]["rrf_score"] += fts_weight / (RRF_K + r["rank"])

        # Sort by RRF score descending
        fused = list(scores.values())
        fused.sort(key=lambda x: x["rrf_score"], reverse=True)

        return fused

    async def _apply_category_boost(
        self,
        db: aiosqlite.Connection,
        results: list[dict[str, Any]],
        categories: list[str],
        boost_factor: float,
    ) -> list[dict[str, Any]]:
        """Apply score boost to category-relevant results.

        Args:
            db: Database connection
            results: Current results
            categories: Categories to boost
            boost_factor: Multiplication factor for boost

        Returns:
            Results with boosted scores
        """
        if not categories or not results:
            return results

        # Get chunk IDs that match the categories
        placeholders = ", ".join("?" for _ in categories)
        chunk_ids = [r["chunk_id"] for r in results]
        chunk_placeholders = ", ".join("?" for _ in chunk_ids)

        query = f"""
            SELECT DISTINCT chunk_id
            FROM tax_law_references
            WHERE category IN ({placeholders})
            AND chunk_id IN ({chunk_placeholders})
        """

        boosted_chunks = set()
        async with db.execute(query, (*categories, *chunk_ids)) as cursor:
            async for row in cursor:
                boosted_chunks.add(row[0])

        # Apply boost
        for result in results:
            if result["chunk_id"] in boosted_chunks:
                result["rrf_score"] *= boost_factor

        # Re-sort after boosting
        results.sort(key=lambda x: x["rrf_score"], reverse=True)

        return results

    async def _fetch_results(
        self,
        db: aiosqlite.Connection,
        fused_results: list[dict[str, Any]],
        include_parent: bool,
    ) -> list[RetrievalResult]:
        """Fetch full data for results including parent context.

        Args:
            db: Database connection
            fused_results: Fused RRF results
            include_parent: Whether to include parent chunk content

        Returns:
            List of RetrievalResult with full data
        """
        if not fused_results:
            return []

        chunk_ids = [r["chunk_id"] for r in fused_results]
        placeholders = ", ".join("?" for _ in chunk_ids)

        # Fetch child chunks with source info
        query = f"""
            SELECT
                c.id as chunk_id,
                c.content,
                c.citation,
                c.parent_chunk_id,
                c.token_count,
                p.content as parent_content,
                p.citation as parent_citation,
                p.title,
                s.id as source_id,
                s.source_type,
                p.effective_date
            FROM tax_law_child_chunks c
            JOIN tax_law_parent_chunks p ON c.parent_chunk_id = p.id
            JOIN tax_law_sources s ON c.source_id = s.id
            WHERE c.id IN ({placeholders})
        """

        # Build lookup from query results
        chunk_data: dict[int, dict[str, Any]] = {}
        async with db.execute(query, chunk_ids) as cursor:
            async for row in cursor:
                chunk_data[row["chunk_id"]] = dict(row)

        # Build results in RRF order
        results = []
        for fused in fused_results:
            chunk_id = fused["chunk_id"]
            if chunk_id not in chunk_data:
                continue

            data = chunk_data[chunk_id]

            result = RetrievalResult(
                chunk_id=chunk_id,
                content=data["content"],
                citation=data["citation"],
                title=data["title"],
                rrf_score=fused["rrf_score"],
                vector_rank=fused.get("vector_rank"),
                fts_rank=fused.get("fts_rank"),
                parent_chunk_id=data["parent_chunk_id"],
                parent_content=data["parent_content"] if include_parent else None,
                parent_citation=data["parent_citation"],
                source_id=data["source_id"],
                source_type=data["source_type"],
                effective_date=data["effective_date"],
                token_count=data["token_count"],
            )
            results.append(result)

        return results

    def _build_context(
        self,
        results: list[RetrievalResult],
        max_tokens: int,
    ) -> tuple[str, int]:
        """Build combined context string for LLM.

        Args:
            results: Retrieval results
            max_tokens: Maximum tokens for context

        Returns:
            Tuple of (context string, total tokens)
        """
        if not results:
            return "", 0

        context_parts = []
        total_tokens = 0

        for i, result in enumerate(results, 1):
            # Prefer parent content for full context, fall back to child
            content = result.parent_content or result.content
            citation = result.parent_citation or result.citation

            # Estimate tokens (rough: 4 chars per token)
            chunk_tokens = result.token_count or (len(content) // 4)

            if total_tokens + chunk_tokens > max_tokens:
                # Use child content if parent is too long
                if result.parent_content and result.content:
                    content = result.content
                    chunk_tokens = result.token_count or (len(content) // 4)
                    if total_tokens + chunk_tokens > max_tokens:
                        break
                else:
                    break

            context_parts.append(
                f"[{i}] {citation}\n{content}"
            )
            total_tokens += chunk_tokens

        context = "\n\n".join(context_parts)
        return context, total_tokens

    @staticmethod
    def _serialize_embedding(embedding: np.ndarray) -> bytes:
        """Serialize embedding to bytes for sqlite-vec.

        Args:
            embedding: Numpy array of shape (EMBEDDING_DIM,)

        Returns:
            Bytes representation
        """
        # sqlite-vec expects little-endian float32
        return struct.pack(f"<{EMBEDDING_DIM}f", *embedding.astype(np.float32))

    @staticmethod
    def _prepare_fts_query(query: str) -> str:
        """Prepare query for FTS5 MATCH.

        Escapes special characters and converts to OR query
        for broader matching.

        Args:
            query: Raw query string

        Returns:
            FTS5-safe query
        """
        # Escape special FTS5 characters
        special_chars = ['"', "'", "(", ")", "*", ":", "^", "-", "+", "~"]
        escaped = query
        for char in special_chars:
            escaped = escaped.replace(char, " ")

        # Split into terms and join with OR for broader matching
        terms = escaped.split()
        if not terms:
            return "*"  # Match all if empty

        # Create OR query: term1 OR term2 OR term3
        # Also add prefix matching with *
        fts_terms = []
        for term in terms:
            if len(term) >= 3:  # Only add prefix matching for longer terms
                fts_terms.append(f'"{term}"*')
            elif len(term) >= 1:
                fts_terms.append(f'"{term}"')

        return " OR ".join(fts_terms) if fts_terms else "*"

    async def log_query(
        self,
        query: str,
        intent_type: str | None,
        response: RetrievalResponse,
        llm_response: str | None = None,
    ) -> int:
        """Log query to history for analytics.

        Args:
            query: Original query
            intent_type: Detected intent type
            response: Retrieval response
            llm_response: LLM-generated response text

        Returns:
            Query history record ID
        """
        chunk_ids = [r.chunk_id for r in response.results]

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO rag_query_history (
                    query_text, intent_type, retrieved_chunk_ids,
                    confidence_score, response_text, response_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    query,
                    intent_type,
                    json.dumps(chunk_ids),
                    response.top_score,
                    llm_response,
                    int(response.retrieval_time_ms),
                ),
            )
            await db.commit()
            return cursor.lastrowid or 0

    async def get_category_relevant_chunks(
        self,
        category: str,
        limit: int = 5,
    ) -> list[RetrievalResult]:
        """Get chunks relevant to a specific expense category.

        Args:
            category: Expense category (e.g., 'buero', 'reise')
            limit: Maximum results

        Returns:
            List of relevant chunks
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            query = """
                SELECT
                    c.id as chunk_id,
                    c.content,
                    c.citation,
                    c.token_count,
                    p.title,
                    p.content as parent_content,
                    p.citation as parent_citation,
                    s.source_type,
                    r.relevance_score
                FROM tax_law_references r
                JOIN tax_law_child_chunks c ON r.chunk_id = c.id
                JOIN tax_law_parent_chunks p ON c.parent_chunk_id = p.id
                JOIN tax_law_sources s ON c.source_id = s.id
                WHERE r.category = ?
                ORDER BY r.relevance_score DESC
                LIMIT ?
            """

            results = []
            async with db.execute(query, (category, limit)) as cursor:
                async for row in cursor:
                    results.append(
                        RetrievalResult(
                            chunk_id=row["chunk_id"],
                            content=row["content"],
                            citation=row["citation"],
                            title=row["title"],
                            rrf_score=row["relevance_score"],
                            parent_content=row["parent_content"],
                            parent_citation=row["parent_citation"],
                            source_type=row["source_type"],
                            token_count=row["token_count"],
                        )
                    )

            return results


# =============================================================================
# Singleton Instance
# =============================================================================

_retriever: HybridRetriever | None = None


def get_hybrid_retriever(db_path: str | None = None) -> HybridRetriever:
    """Get or create the hybrid retriever singleton.

    Args:
        db_path: Database path (required on first call)

    Returns:
        HybridRetriever singleton instance
    """
    global _retriever
    if _retriever is None:
        if db_path is None:
            raise ValueError("db_path required for first retriever initialization")
        _retriever = HybridRetriever(db_path)
    return _retriever
