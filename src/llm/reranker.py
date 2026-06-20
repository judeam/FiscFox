"""Cross-encoder reranker for German tax law RAG.

Second-stage reranking over candidates retrieved by hybrid (vector + FTS5)
search. A cross-encoder scores each (query, passage) pair jointly, which is far
more precise than first-stage bi-encoder similarity for fragmented statute text.

Uses a sentence-transformers ``CrossEncoder`` and degrades gracefully to a no-op
(preserving the input/retrieval order) if the dependency or model is unavailable
or reranking is disabled in settings.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from src.llm.config import LLMSettings, get_llm_settings

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class RerankerService:
    """Lazy, async-safe cross-encoder reranker.

    Features:
    - Lazy model loading (no cost until first rerank)
    - Async-safe via a dedicated thread pool
    - Config-driven model name and device
    - Graceful fallback to retrieval order if unavailable
    """

    # Shared thread pool for blocking inference
    _executor: ThreadPoolExecutor | None = None

    def __init__(self, settings: LLMSettings | None = None):
        """Initialize the reranker service.

        Args:
            settings: LLM settings (defaults to the singleton)
        """
        self._settings = settings or get_llm_settings()
        self._model_name = self._settings.reranker_model
        self._device = self._settings.embedding_device
        self._model: CrossEncoder | None = None
        # Disabled either by config or after a failed load (graceful fallback)
        self._unavailable = not self._settings.reranker_enabled

        if RerankerService._executor is None:
            RerankerService._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="reranker",
            )

    @property
    def is_enabled(self) -> bool:
        """Whether reranking is enabled and not known-broken."""
        return not self._unavailable

    def _load_model(self) -> None:
        """Load the cross-encoder model (blocking)."""
        if self._model is not None or self._unavailable:
            return
        try:
            from sentence_transformers import CrossEncoder

            logger.info(
                f"Loading reranker model: {self._model_name} "
                f"(device={self._device or 'auto'})"
            )
            self._model = CrossEncoder(self._model_name, device=self._device)
            logger.info(f"Reranker model loaded: {self._model_name}")
        except Exception as e:  # ImportError or model load failure
            logger.warning(
                "Reranker unavailable (%s); falling back to retrieval order.", e
            )
            self._unavailable = True

    async def ensure_loaded(self) -> None:
        """Ensure the model is loaded (async-safe)."""
        if self._model is not None or self._unavailable:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(RerankerService._executor, self._load_model)

    def _rank_sync(
        self, query: str, documents: list[str]
    ) -> list[tuple[int, float]]:
        """Score documents against the query (blocking).

        Returns:
            ``[(original_index, score), ...]`` sorted by score descending. If the
            model is unavailable, returns the identity order with zero scores.
        """
        if self._model is None:
            self._load_model()
        if self._unavailable or self._model is None:
            return [(i, 0.0) for i in range(len(documents))]

        pairs = [[query, doc] for doc in documents]
        scores = self._model.predict(pairs, show_progress_bar=False)
        return sorted(
            ((i, float(s)) for i, s in enumerate(scores)),
            key=lambda x: x[1],
            reverse=True,
        )

    async def rerank(
        self, query: str, documents: list[str]
    ) -> list[tuple[int, float]]:
        """Rerank documents for a query.

        Args:
            query: The search query
            documents: Candidate passage texts (retrieval order)

        Returns:
            ``[(original_index, score), ...]`` sorted by relevance descending.
        """
        if not documents:
            return []
        await self.ensure_loaded()
        if self._unavailable:
            return [(i, 0.0) for i in range(len(documents))]
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            RerankerService._executor,
            lambda: self._rank_sync(query, documents),
        )

    async def shutdown(self) -> None:
        """Release model and executor resources."""
        self._model = None
        if RerankerService._executor:
            RerankerService._executor.shutdown(wait=False)
            RerankerService._executor = None
        logger.info("Reranker service shutdown complete")


# =============================================================================
# Singleton Instance
# =============================================================================

_reranker_service: RerankerService | None = None


def get_reranker_service() -> RerankerService:
    """Get or create the reranker service singleton."""
    global _reranker_service
    if _reranker_service is None:
        _reranker_service = RerankerService()
    return _reranker_service
