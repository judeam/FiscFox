"""Embedding service for German tax law RAG.

Uses sentence-transformers with multilingual model for semantic search.
Includes German tax text preprocessing and caching.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from src.llm.config import LLMSettings, get_llm_settings
from src.llm.exceptions import EmbeddingError

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Embedding configuration is driven by LLMSettings (env-overridable via
# FISCFOX_LLM_EMBEDDING_MODEL / FISCFOX_LLM_EMBEDDING_DIM). The default is
# BAAI/bge-m3 (1024-dim, multilingual, strong German, 8K context, no prefixes).
_embedding_settings = get_llm_settings()

# Default model for multilingual German RAG
DEFAULT_MODEL = _embedding_settings.embedding_model

# Embedding dimension — MUST match DEFAULT_MODEL and the vec0 schema FLOAT[N]
EMBEDDING_DIM = _embedding_settings.embedding_dim


# =============================================================================
# German Tax Text Preprocessor
# =============================================================================


class GermanTaxTextProcessor:
    """Preprocessor for German tax legal text.

    Expands abbreviations and normalizes text for better embedding quality.
    """

    # Common German tax abbreviations
    ABBREVIATIONS = {
        "EStG": "Einkommensteuergesetz",
        "UStG": "Umsatzsteuergesetz",
        "AO": "Abgabenordnung",
        "BGB": "Bürgerliches Gesetzbuch",
        "HGB": "Handelsgesetzbuch",
        "BMF": "Bundesministerium der Finanzen",
        "BFH": "Bundesfinanzhof",
        "FG": "Finanzgericht",
        "BStBl": "Bundessteuerblatt",
        "AfA": "Absetzung für Abnutzung",
        "GWG": "Geringwertige Wirtschaftsgüter",
        "USt": "Umsatzsteuer",
        "ESt": "Einkommensteuer",
        "GewSt": "Gewerbesteuer",
        "EÜR": "Einnahmen-Überschuss-Rechnung",
        "BWA": "Betriebswirtschaftliche Auswertung",
        "Abs": "Absatz",
        "Nr": "Nummer",
        "Satz": "Satz",
        "ff": "folgende",
        "i.S.d": "im Sinne des",
        "i.V.m": "in Verbindung mit",
        "gem": "gemäß",
        "z.B": "zum Beispiel",
        "u.a": "unter anderem",
        "usw": "und so weiter",
        "bzw": "beziehungsweise",
        "d.h": "das heißt",
        "ggf": "gegebenenfalls",
        "o.g": "oben genannte",
        "u.U": "unter Umständen",
        "vgl": "vergleiche",
        "s.o": "siehe oben",
        "s.u": "siehe unten",
    }

    # Section reference pattern: § 7 Abs. 1 Satz 1
    SECTION_PATTERN = re.compile(r"§\s*(\d+[a-z]?)\s*(Abs\.\s*\d+)?\s*(Satz\s*\d+)?")

    @classmethod
    def preprocess(cls, text: str, expand_abbrev: bool = True) -> str:
        """Preprocess German tax text for embedding.

        Args:
            text: Input text
            expand_abbrev: Whether to expand abbreviations

        Returns:
            Preprocessed text
        """
        if not text:
            return ""

        result = text

        # Expand abbreviations if requested
        if expand_abbrev:
            for abbrev, full in cls.ABBREVIATIONS.items():
                # Match word boundaries to avoid partial replacements
                pattern = re.compile(rf"\b{re.escape(abbrev)}\b", re.IGNORECASE)
                result = pattern.sub(full, result)

        # Normalize whitespace
        result = " ".join(result.split())

        # Normalize section references for consistency
        # § 7 → Paragraph 7, etc. (aids semantic understanding)
        result = re.sub(r"§\s*", "Paragraph ", result)

        return result.strip()

    @classmethod
    def extract_citations(cls, text: str) -> list[str]:
        """Extract German law citations from text.

        Args:
            text: Input text

        Returns:
            List of citations found (e.g., ["§ 7 Abs. 1 EStG"])
        """
        citations = []

        # Find all section references
        for match in cls.SECTION_PATTERN.finditer(text):
            citation = match.group(0).strip()
            # Look for law name after the section
            after = text[match.end() : match.end() + 30]
            for law in ["EStG", "UStG", "AO", "HGB", "BGB"]:
                if law in after:
                    citation = f"{citation} {law}"
                    break
            citations.append(citation)

        return citations


# =============================================================================
# Embedding Service
# =============================================================================


class EmbeddingService:
    """Service for generating text embeddings.

    Features:
    - Lazy model loading
    - Batch embedding generation
    - German tax text preprocessing
    - Embedding caching (SHA256 hash key)
    - Async-safe via thread pool
    """

    # Shared thread pool for blocking operations
    _executor: ThreadPoolExecutor | None = None

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        settings: LLMSettings | None = None,
        cache_dir: Path | None = None,
    ):
        """Initialize embedding service.

        Args:
            model_name: Sentence transformer model name
            settings: LLM settings
            cache_dir: Directory for model cache
        """
        self._model_name = model_name
        self._settings = settings or get_llm_settings()
        self._cache_dir = cache_dir or self._settings.models_dir / "embeddings"
        self._device = self._settings.embedding_device
        self._query_prefix = self._settings.embedding_query_prefix
        self._passage_prefix = self._settings.embedding_passage_prefix

        # Lazy loaded model
        self._model: SentenceTransformer | None = None
        self._preprocessor = GermanTaxTextProcessor()

        # In-memory embedding cache (hash -> embedding)
        self._cache: dict[str, np.ndarray] = {}

        # Ensure executor exists
        if EmbeddingService._executor is None:
            EmbeddingService._executor = ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="embedding",
            )

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None

    @property
    def embedding_dim(self) -> int:
        """Get embedding dimension."""
        return EMBEDDING_DIM

    def _load_model(self) -> None:
        """Load sentence transformer model (blocking)."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(
                f"Loading embedding model: {self._model_name} "
                f"(device={self._device or 'auto'})"
            )
            self._model = SentenceTransformer(
                self._model_name,
                cache_folder=str(self._cache_dir),
                device=self._device,
            )

            # Guard against a model/dim mismatch that would corrupt vec0 packing
            actual_dim = self._model.get_sentence_embedding_dimension()
            if actual_dim is not None and actual_dim != EMBEDDING_DIM:
                logger.warning(
                    "Embedding model %s produces %d dims but EMBEDDING_DIM=%d; "
                    "set FISCFOX_LLM_EMBEDDING_DIM and the vec0 schema to match.",
                    self._model_name,
                    actual_dim,
                    EMBEDDING_DIM,
                )
            logger.info(f"Embedding model loaded: {self._model_name}")

        except ImportError:
            raise EmbeddingError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
        except Exception as e:
            raise EmbeddingError(f"Failed to load embedding model: {e}") from e

    async def ensure_loaded(self) -> None:
        """Ensure model is loaded (async-safe)."""
        if self._model is not None:
            return

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(EmbeddingService._executor, self._load_model)

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.sha256(text.encode()).hexdigest()[:32]

    def _embed_sync(
        self,
        texts: list[str],
        preprocess: bool = True,
        prefix: str = "",
    ) -> np.ndarray:
        """Generate embeddings synchronously (blocking).

        Args:
            texts: List of texts to embed
            preprocess: Whether to preprocess German tax text
            prefix: Model-specific instruction prefix (e.g. e5/Qwen3 query/passage)

        Returns:
            Numpy array of shape (len(texts), EMBEDDING_DIM)
        """
        if self._model is None:
            self._load_model()

        # Preprocess texts
        if preprocess:
            processed = [self._preprocessor.preprocess(t) for t in texts]
        else:
            processed = list(texts)

        # Apply model-specific instruction prefix (no-op for prefix-free models)
        if prefix:
            processed = [prefix + t for t in processed]

        # Check cache for each text
        embeddings = []
        texts_to_embed = []
        text_indices = []

        for i, text in enumerate(processed):
            key = self._get_cache_key(text)
            if key in self._cache:
                embeddings.append((i, self._cache[key]))
            else:
                texts_to_embed.append(text)
                text_indices.append(i)

        # Embed uncached texts
        if texts_to_embed:
            new_embeddings = self._model.encode(
                texts_to_embed,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            # Cache new embeddings
            for text, emb in zip(texts_to_embed, new_embeddings):
                key = self._get_cache_key(text)
                self._cache[key] = emb

            # Add to results
            for idx, emb in zip(text_indices, new_embeddings):
                embeddings.append((idx, emb))

        # Sort by original index and stack
        embeddings.sort(key=lambda x: x[0])
        return np.stack([e[1] for e in embeddings])

    async def embed_text(
        self,
        text: str,
        preprocess: bool = True,
    ) -> np.ndarray:
        """Generate embedding for a single text.

        Args:
            text: Input text
            preprocess: Whether to preprocess German tax text

        Returns:
            Numpy array of shape (EMBEDDING_DIM,)
        """
        await self.ensure_loaded()

        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            EmbeddingService._executor,
            lambda: self._embed_sync([text], preprocess, self._passage_prefix),
        )
        return embeddings[0]

    async def embed_batch(
        self,
        texts: list[str],
        preprocess: bool = True,
        batch_size: int = 32,
    ) -> np.ndarray:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts
            preprocess: Whether to preprocess German tax text
            batch_size: Batch size for processing

        Returns:
            Numpy array of shape (len(texts), EMBEDDING_DIM)
        """
        await self.ensure_loaded()

        if not texts:
            return np.array([]).reshape(0, EMBEDDING_DIM)

        # Process in batches to avoid memory issues
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            loop = asyncio.get_event_loop()
            batch_embeddings = await loop.run_in_executor(
                EmbeddingService._executor,
                lambda b=batch: self._embed_sync(b, preprocess, self._passage_prefix),
            )
            all_embeddings.append(batch_embeddings)

        return np.vstack(all_embeddings)

    async def embed_query(
        self,
        query: str,
        preprocess: bool = True,
    ) -> np.ndarray:
        """Generate embedding for a search query.

        Queries may need different preprocessing than documents.

        Args:
            query: Search query text
            preprocess: Whether to preprocess

        Returns:
            Numpy array of shape (EMBEDDING_DIM,)
        """
        # For queries, we might want less aggressive preprocessing
        # to preserve the user's original intent
        processed = query
        if preprocess:
            # Only normalize whitespace for queries
            processed = " ".join(query.split())

        # Queries use the query-side instruction prefix (asymmetric models)
        await self.ensure_loaded()
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            EmbeddingService._executor,
            lambda: self._embed_sync(
                [processed], preprocess=False, prefix=self._query_prefix
            ),
        )
        return embeddings[0]

    def clear_cache(self) -> int:
        """Clear embedding cache.

        Returns:
            Number of cached embeddings cleared
        """
        count = len(self._cache)
        self._cache.clear()
        return count

    async def shutdown(self) -> None:
        """Shutdown service and release resources."""
        self.clear_cache()
        self._model = None

        if EmbeddingService._executor:
            EmbeddingService._executor.shutdown(wait=False)
            EmbeddingService._executor = None

        logger.info("Embedding service shutdown complete")


# =============================================================================
# Singleton Instance
# =============================================================================

_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
