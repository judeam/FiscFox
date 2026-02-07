"""Main LLM service for FiscFox.

Provides async-safe inference with streaming support,
structured output generation, and response caching.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

from src.llm.config import LLMSettings, ModelSize, get_llm_settings
from src.llm.exceptions import (
    ContextLengthExceededError,
    GenerationError,
    InferenceError,
    InferenceTimeoutError,
    LLMNotAvailableError,
    ModelNotLoadedError,
    StructuredOutputError,
)
from src.llm.manager import LLMModelManager, get_model_manager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMResponse(BaseModel):
    """Standard LLM response wrapper."""

    content: str
    tokens_used: int
    generation_time_ms: float
    model_name: str
    cached: bool = False


class LLMService:
    """Async LLM service for FiscFox inference operations.

    Singleton pattern matching existing FiscFox services.
    Provides:
    - Async-safe blocking inference via thread pool
    - Token streaming for responsive UI
    - Structured output generation (JSON/SQL)
    - Response caching for repeated queries
    """

    # Thread pool for blocking inference operations
    # Separate from FastAPI's default pool to prevent blocking
    _executor: ThreadPoolExecutor | None = None

    def __init__(
        self,
        manager: LLMModelManager | None = None,
        settings: LLMSettings | None = None,
    ):
        """Initialize LLM service.

        Args:
            manager: Model manager (creates new if None)
            settings: LLM settings (uses manager's if None)
        """
        self._settings = settings or get_llm_settings()
        self._manager = manager or get_model_manager()

        # Response cache (simple dict-based, could use TTLCache)
        self._cache: dict[str, LLMResponse] = {}
        self._cache_timestamps: dict[str, datetime] = {}

        # Ensure executor exists
        if LLMService._executor is None:
            LLMService._executor = ThreadPoolExecutor(
                max_workers=1,  # Single inference at a time
                thread_name_prefix="llm_inference",
            )

    @property
    def is_ready(self) -> bool:
        """Check if service is ready for inference."""
        return self._settings.enabled and self._manager.is_loaded

    @property
    def is_enabled(self) -> bool:
        """Check if LLM features are enabled."""
        return self._settings.enabled

    @property
    def manager(self) -> LLMModelManager:
        """Get the model manager."""
        return self._manager

    async def ensure_loaded(self, model_size: ModelSize | None = None) -> None:
        """Ensure model is loaded, loading if necessary.

        Args:
            model_size: Specific model to load (None = auto)

        Raises:
            LLMNotAvailableError: If LLM is disabled
        """
        if not self._settings.enabled:
            raise LLMNotAvailableError("LLM features are disabled")

        if not self._manager.is_loaded:
            await self._manager.load_model(model_size)

    def _build_messages(
        self,
        user_message: str,
        system_prompt: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Build chat messages for inference.

        Args:
            user_message: Current user message
            system_prompt: Optional system prompt
            conversation_history: Optional prior messages

        Returns:
            List of chat messages in OpenAI format
        """
        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_message})

        return messages

    def _estimate_tokens(self, text: str) -> int:
        """Rough token count estimation.

        Args:
            text: Input text

        Returns:
            Estimated token count (conservative)
        """
        # Rough estimate: 4 characters per token for German/English
        return len(text) // 4 + 100  # +100 for safety

    def _get_cache_key(self, messages: list[dict[str, str]]) -> str:
        """Generate cache key from messages."""
        return str(hash(str(messages)))

    def _check_cache(self, cache_key: str) -> LLMResponse | None:
        """Check cache for response."""
        if self._settings.response_cache_ttl <= 0:
            return None

        if cache_key not in self._cache:
            return None

        timestamp = self._cache_timestamps.get(cache_key)
        if timestamp is None:
            return None

        age = (datetime.now() - timestamp).total_seconds()
        if age > self._settings.response_cache_ttl:
            # Expired
            del self._cache[cache_key]
            del self._cache_timestamps[cache_key]
            return None

        response = self._cache[cache_key]
        response.cached = True
        return response

    def _set_cache(self, cache_key: str, response: LLMResponse) -> None:
        """Store response in cache."""
        if self._settings.response_cache_ttl > 0:
            self._cache[cache_key] = response
            self._cache_timestamps[cache_key] = datetime.now()

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        use_cache: bool = True,
        timeout: float | None = None,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            conversation_history: Optional conversation context
            max_tokens: Max tokens to generate (default from settings)
            temperature: Sampling temperature (default from settings)
            use_cache: Whether to use response cache
            timeout: Inference timeout in seconds

        Returns:
            LLMResponse with generated content

        Raises:
            ModelNotLoadedError: If model not loaded
            InferenceError: If generation fails
            InferenceTimeoutError: If timeout exceeded
            ContextLengthExceededError: If input too long
        """
        await self.ensure_loaded()

        messages = self._build_messages(prompt, system_prompt, conversation_history)

        # Check cache
        cache_key = self._get_cache_key(messages)
        if use_cache:
            cached = self._check_cache(cache_key)
            if cached:
                return cached

        # Validate context length
        total_text = " ".join(m["content"] for m in messages)
        estimated_tokens = self._estimate_tokens(total_text)
        config = self._manager.current_model

        if config and estimated_tokens > config.context_length:
            raise ContextLengthExceededError(estimated_tokens, config.context_length)

        # Prepare generation parameters
        gen_params = {
            "messages": messages,
            "max_tokens": max_tokens or self._settings.max_tokens,
            "temperature": temperature if temperature is not None else self._settings.temperature,
            "top_p": self._settings.top_p,
        }

        # Run inference in thread pool
        start_time = datetime.now()

        def _generate() -> dict[str, Any]:
            model = self._manager.model
            return model.create_chat_completion(**gen_params)

        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    LLMService._executor, _generate
                ),
                timeout=timeout or self._settings.inference_timeout,
            )
        except asyncio.TimeoutError:
            raise InferenceTimeoutError(timeout or self._settings.inference_timeout)
        except Exception as e:
            raise InferenceError(f"Generation failed: {e}") from e

        # Extract response
        generation_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise GenerationError("Invalid response structure", str(result)) from e

        tokens_used = result.get("usage", {}).get("total_tokens", 0)

        response = LLMResponse(
            content=content,
            tokens_used=tokens_used,
            generation_time_ms=generation_time_ms,
            model_name=config.name if config else "unknown",
            cached=False,
        )

        # Cache response
        if use_cache:
            self._set_cache(cache_key, response)

        return response

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the LLM.

        Yields tokens as they're generated for real-time UI updates.

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            conversation_history: Optional conversation context
            max_tokens: Max tokens to generate
            temperature: Sampling temperature

        Yields:
            Generated tokens as they're produced

        Raises:
            ModelNotLoadedError: If model not loaded
            InferenceError: If generation fails
        """
        await self.ensure_loaded()

        messages = self._build_messages(prompt, system_prompt, conversation_history)

        gen_params = {
            "messages": messages,
            "max_tokens": max_tokens or self._settings.max_tokens,
            "temperature": temperature if temperature is not None else self._settings.temperature,
            "top_p": self._settings.top_p,
            "stream": True,
        }

        # Create streaming generator
        def _stream_generator():
            model = self._manager.model
            return model.create_chat_completion(**gen_params)

        # Run in thread and yield tokens
        loop = asyncio.get_event_loop()

        try:
            # Start streaming in thread
            stream = await loop.run_in_executor(LLMService._executor, _stream_generator)

            # Process stream chunks
            for chunk in stream:
                if "choices" in chunk and chunk["choices"]:
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content

        except Exception as e:
            raise InferenceError(f"Streaming generation failed: {e}") from e

    async def generate_structured(
        self,
        prompt: str,
        schema: type[T],
        system_prompt: str | None = None,
        max_retries: int = 2,
    ) -> T:
        """Generate structured output matching a Pydantic schema.

        Uses JSON mode with validation and retry logic.

        Args:
            prompt: User prompt
            schema: Pydantic model class for output structure
            system_prompt: Optional system instructions
            max_retries: Max generation attempts

        Returns:
            Instance of the schema class

        Raises:
            StructuredOutputError: If valid output cannot be generated
        """
        await self.ensure_loaded()

        # Build schema-aware prompt
        schema_json = schema.model_json_schema()
        full_system_prompt = (
            f"{system_prompt or ''}\n\n"
            f"Respond with valid JSON matching this schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Output ONLY valid JSON, no additional text."
        )

        last_error: str | None = None
        raw_output: str = ""

        for attempt in range(max_retries + 1):
            try:
                response = await self.generate(
                    prompt=prompt,
                    system_prompt=full_system_prompt,
                    temperature=0.1,  # Low temperature for structured output
                    use_cache=False,  # Don't cache structured attempts
                )

                raw_output = response.content.strip()

                # Try to extract JSON from response
                json_content = self._extract_json(raw_output)

                # Parse and validate
                return schema.model_validate_json(json_content)

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Structured output attempt {attempt + 1}/{max_retries + 1} failed: {e}"
                )

        raise StructuredOutputError(
            schema_name=schema.__name__,
            raw_output=raw_output,
            parse_error=last_error or "Unknown error",
        )

    def _extract_json(self, text: str) -> str:
        """Extract JSON from potentially markdown-wrapped text."""
        # Handle markdown code blocks
        if "```json" in text:
            json_start = text.index("```json") + 7
            json_end = text.index("```", json_start)
            return text[json_start:json_end].strip()
        elif "```" in text:
            json_start = text.index("```") + 3
            json_end = text.index("```", json_start)
            return text[json_start:json_end].strip()

        # Try to find JSON object/array
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            if start_char in text:
                start = text.index(start_char)
                # Find matching end
                depth = 0
                for i, char in enumerate(text[start:], start):
                    if char == start_char:
                        depth += 1
                    elif char == end_char:
                        depth -= 1
                        if depth == 0:
                            return text[start : i + 1]

        return text

    def clear_cache(self) -> int:
        """Clear response cache.

        Returns:
            Number of cached items cleared
        """
        count = len(self._cache)
        self._cache.clear()
        self._cache_timestamps.clear()
        return count

    async def shutdown(self) -> None:
        """Shutdown service and release resources."""
        await self._manager.unload_model()

        if LLMService._executor:
            LLMService._executor.shutdown(wait=False)
            LLMService._executor = None

        self.clear_cache()
        logger.info("LLM service shutdown complete")

    def get_status(self) -> dict[str, Any]:
        """Get service status.

        Returns:
            Status dict including manager status and cache stats
        """
        return {
            "enabled": self._settings.enabled,
            "is_ready": self.is_ready,
            "manager": self._manager.get_status(),
            "cache": {
                "size": len(self._cache),
                "ttl_seconds": self._settings.response_cache_ttl,
            },
            "settings": {
                "max_tokens": self._settings.max_tokens,
                "temperature": self._settings.temperature,
                "streaming_enabled": self._settings.enable_streaming,
                "inference_timeout": self._settings.inference_timeout,
            },
        }


# =============================================================================
# Singleton Instance and FastAPI Integration
# =============================================================================

_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Get or create the LLM service singleton.

    Returns:
        LLMService singleton instance
    """
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


async def initialize_llm_service() -> LLMService | None:
    """Initialize LLM service with model loading.

    Called during FastAPI startup via lifespan.

    Returns:
        Initialized LLMService with loaded model, or None if disabled
    """
    service = get_llm_service()

    if not service.is_enabled:
        logger.info("LLM features disabled, skipping initialization")
        return None

    try:
        await service.ensure_loaded()
        logger.info("LLM service initialized successfully")
        return service
    except Exception as e:
        logger.warning(f"LLM service initialization failed: {e}")
        logger.warning("LLM features will be unavailable")
        return None


async def shutdown_llm_service() -> None:
    """Shutdown LLM service.

    Called during FastAPI shutdown via lifespan.
    """
    global _llm_service
    if _llm_service is not None:
        await _llm_service.shutdown()
        _llm_service = None
