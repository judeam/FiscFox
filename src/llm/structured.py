"""Structured generation using Outlines for constrained decoding.

Compiles Pydantic schemas to finite state machines (FSM) for
guaranteed valid JSON output from the LLM.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

from src.llm.config import get_llm_settings
from src.llm.exceptions import ModelNotLoadedError, StructuredOutputError
from src.llm.manager import LLMModelManager, get_model_manager

if TYPE_CHECKING:
    from outlines import generate
    from outlines.models.llamacpp import LlamaCpp

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class StructuredGenerator:
    """Generates structured output using Outlines constrained decoding.

    Uses schema-guided generation to ensure LLM outputs valid JSON
    matching Pydantic model definitions. Caches compiled generators
    for reuse across requests.

    Features:
    - FSM-based constrained generation
    - Schema compilation caching
    - Async-safe execution via thread pool
    - Fallback to JSON mode with validation
    """

    # Shared thread pool for blocking operations
    _executor: ThreadPoolExecutor | None = None

    def __init__(
        self,
        manager: LLMModelManager | None = None,
    ):
        """Initialize structured generator.

        Args:
            manager: LLM model manager (creates new if None)
        """
        self._manager = manager or get_model_manager()
        self._settings = get_llm_settings()

        # Cache for compiled generators per schema
        self._generator_cache: dict[str, Any] = {}

        # Outlines model wrapper (lazy loaded)
        self._outlines_model: LlamaCpp | None = None

        # Ensure executor exists
        if StructuredGenerator._executor is None:
            StructuredGenerator._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="structured_gen",
            )

    @property
    def is_ready(self) -> bool:
        """Check if generator is ready for use."""
        return self._manager.is_loaded

    def _get_outlines_model(self) -> Any:
        """Get or create Outlines model wrapper.

        Lazily wraps the llama-cpp model for Outlines integration.
        """
        if not self._manager.is_loaded:
            raise ModelNotLoadedError()

        if self._outlines_model is None:
            try:
                from outlines.models.llamacpp import LlamaCpp

                # Wrap existing llama-cpp model
                self._outlines_model = LlamaCpp(self._manager.model)
                logger.info("Created Outlines model wrapper")
            except ImportError:
                logger.warning("Outlines not installed, using fallback mode")
                raise

        return self._outlines_model

    def _get_schema_key(self, schema: type[T]) -> str:
        """Generate unique cache key for schema."""
        return f"{schema.__module__}.{schema.__name__}"

    def _get_or_compile_generator(
        self,
        schema: type[T],
    ) -> Callable[[str], str]:
        """Get cached generator or compile new one.

        Args:
            schema: Pydantic model class

        Returns:
            Compiled Outlines generator function
        """
        key = self._get_schema_key(schema)

        if key not in self._generator_cache:
            try:
                from outlines import generate

                model = self._get_outlines_model()
                json_schema = schema.model_json_schema()

                # Compile JSON generator from schema
                generator = generate.json(model, json_schema)
                self._generator_cache[key] = generator

                logger.debug(f"Compiled generator for schema: {key}")

            except ImportError:
                # Return None to signal fallback mode
                logger.warning(
                    f"Outlines not available, schema {key} will use fallback"
                )
                self._generator_cache[key] = None

        return self._generator_cache[key]

    async def generate(
        self,
        prompt: str,
        schema: type[T],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.1,
        max_retries: int = 2,
    ) -> T:
        """Generate structured output matching the Pydantic schema.

        Uses Outlines for constrained generation when available,
        falls back to JSON mode with validation otherwise.

        Args:
            prompt: User prompt/question
            schema: Pydantic model class for output
            system_prompt: Optional system instructions
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (low for structured)
            max_retries: Number of retry attempts on validation failure

        Returns:
            Instance of schema class with validated data

        Raises:
            ModelNotLoadedError: If model not loaded
            StructuredOutputError: If valid output cannot be generated
        """
        if not self._manager.is_loaded:
            raise ModelNotLoadedError()

        generator = self._get_or_compile_generator(schema)

        if generator is not None:
            # Use Outlines constrained generation
            return await self._generate_constrained(
                prompt=prompt,
                schema=schema,
                generator=generator,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            # Fallback to JSON mode with validation
            return await self._generate_fallback(
                prompt=prompt,
                schema=schema,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                max_retries=max_retries,
            )

    async def _generate_constrained(
        self,
        prompt: str,
        schema: type[T],
        generator: Callable,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.1,
    ) -> T:
        """Generate using Outlines constrained decoding.

        This guarantees valid JSON output matching the schema.
        """
        # Build full prompt
        full_prompt = self._build_prompt(prompt, schema, system_prompt)

        def _generate() -> str:
            return generator(
                full_prompt,
                max_tokens=max_tokens or self._settings.max_tokens,
                temperature=temperature,
            )

        try:
            loop = asyncio.get_event_loop()
            json_output = await loop.run_in_executor(
                StructuredGenerator._executor, _generate
            )

            # Parse and validate
            return schema.model_validate_json(json_output)

        except Exception as e:
            logger.error(f"Constrained generation failed: {e}")
            raise StructuredOutputError(
                schema_name=schema.__name__,
                raw_output=str(e),
                parse_error=str(e),
            ) from e

    async def _generate_fallback(
        self,
        prompt: str,
        schema: type[T],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.1,
        max_retries: int = 2,
    ) -> T:
        """Fallback generation using JSON mode with validation.

        Less reliable than constrained generation but works
        without Outlines dependency.
        """
        # Build schema-aware prompt
        schema_json = schema.model_json_schema()
        full_system = (
            f"{system_prompt or ''}\n\n"
            f"Du musst mit gültigem JSON antworten, das diesem Schema entspricht:\n"
            f"```json\n{schema_json}\n```\n"
            f"Antworte NUR mit gültigem JSON, kein zusätzlicher Text."
        )

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": prompt},
        ]

        last_error: str | None = None
        raw_output: str = ""

        for attempt in range(max_retries + 1):
            try:
                # Run inference
                def _generate() -> dict:
                    model = self._manager.model
                    return model.create_chat_completion(
                        messages=messages,
                        max_tokens=max_tokens or self._settings.max_tokens,
                        temperature=temperature,
                        response_format={"type": "json_object"},
                    )

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    StructuredGenerator._executor, _generate
                )

                raw_output = result["choices"][0]["message"]["content"]
                json_content = self._extract_json(raw_output)

                # Validate against schema
                return schema.model_validate_json(json_content)

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Fallback generation attempt {attempt + 1}/{max_retries + 1} "
                    f"failed: {e}"
                )

        raise StructuredOutputError(
            schema_name=schema.__name__,
            raw_output=raw_output,
            parse_error=last_error or "Unknown error",
        )

    def _build_prompt(
        self,
        prompt: str,
        schema: type[T],
        system_prompt: str | None = None,
    ) -> str:
        """Build prompt for constrained generation.

        Outlines uses a single prompt string, so we combine
        system and user content.
        """
        parts = []

        if system_prompt:
            parts.append(f"[System]\n{system_prompt}\n")

        # Add schema description for context
        schema_desc = schema.__doc__ or schema.__name__
        parts.append(f"[Schema: {schema_desc}]\n")

        parts.append(f"[User]\n{prompt}\n")
        parts.append("[Assistant]\n")

        return "\n".join(parts)

    def _extract_json(self, text: str) -> str:
        """Extract JSON from potentially markdown-wrapped text."""
        text = text.strip()

        # Handle markdown code blocks
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            return text[start:end].strip()

        # Try to find JSON object/array
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            if start_char in text:
                start = text.index(start_char)
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
        """Clear compiled generator cache.

        Returns:
            Number of cached generators cleared
        """
        count = len(self._generator_cache)
        self._generator_cache.clear()
        self._outlines_model = None
        logger.info(f"Cleared {count} cached generators")
        return count

    async def shutdown(self) -> None:
        """Shutdown generator and release resources."""
        self.clear_cache()

        if StructuredGenerator._executor:
            StructuredGenerator._executor.shutdown(wait=False)
            StructuredGenerator._executor = None

        logger.info("Structured generator shutdown complete")


# =============================================================================
# Singleton Instance
# =============================================================================

_generator: StructuredGenerator | None = None


def get_structured_generator() -> StructuredGenerator:
    """Get or create the structured generator singleton."""
    global _generator
    if _generator is None:
        _generator = StructuredGenerator()
    return _generator
