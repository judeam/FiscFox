"""LLM-specific exception hierarchy for FiscFox.

Extends the FiscFoxError base for consistent error handling.
"""

from typing import Any

from src.core.exceptions import FiscFoxError


class LLMError(FiscFoxError):
    """Base exception for all LLM-related errors."""

    code = "LLM_ERROR"


# =============================================================================
# Model Loading Errors
# =============================================================================


class ModelNotLoadedError(LLMError):
    """Model not loaded when inference requested."""

    code = "MODEL_NOT_LOADED"

    def __init__(self) -> None:
        super().__init__(
            "LLM model not loaded. Call load_model() first or ensure "
            "the model file exists in the configured directory."
        )


class ModelNotFoundError(LLMError):
    """Model file not found at configured path."""

    code = "MODEL_NOT_FOUND"

    def __init__(self, model_path: str, expected_filename: str) -> None:
        super().__init__(
            f"Model file '{expected_filename}' not found at '{model_path}'. "
            "Download the model or configure the correct path.",
            details={"model_path": model_path, "expected_filename": expected_filename},
        )


class InsufficientResourcesError(LLMError):
    """Insufficient system resources for model loading."""

    code = "INSUFFICIENT_RESOURCES"

    def __init__(
        self,
        message: str,
        required_ram_gb: float | None = None,
        available_ram_gb: float | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if required_ram_gb is not None:
            details["required_ram_gb"] = required_ram_gb
        if available_ram_gb is not None:
            details["available_ram_gb"] = available_ram_gb
        super().__init__(message, details=details)


class ModelSwitchError(LLMError):
    """Error while switching between models."""

    code = "MODEL_SWITCH_ERROR"


# =============================================================================
# Inference Errors
# =============================================================================


class InferenceError(LLMError):
    """Error during model inference."""

    code = "INFERENCE_ERROR"


class InferenceTimeoutError(InferenceError):
    """Inference operation timed out."""

    code = "INFERENCE_TIMEOUT"

    def __init__(self, timeout_seconds: float) -> None:
        super().__init__(
            f"LLM inference timed out after {timeout_seconds:.1f} seconds",
            details={"timeout_seconds": timeout_seconds},
        )


class ContextLengthExceededError(InferenceError):
    """Input exceeded model's context length."""

    code = "CONTEXT_LENGTH_EXCEEDED"

    def __init__(self, input_tokens: int, max_tokens: int) -> None:
        super().__init__(
            f"Input ({input_tokens} tokens) exceeds model context length ({max_tokens} tokens)",
            details={"input_tokens": input_tokens, "max_tokens": max_tokens},
        )


class GenerationError(InferenceError):
    """Error during text generation."""

    code = "GENERATION_ERROR"

    def __init__(self, reason: str, raw_output: str | None = None) -> None:
        details: dict[str, Any] = {"reason": reason}
        if raw_output:
            details["raw_output"] = raw_output[:500]  # Truncate for logs
        super().__init__(f"Generation failed: {reason}", details=details)


# =============================================================================
# Structured Output Errors
# =============================================================================


class StructuredOutputError(LLMError):
    """Error in structured output generation (JSON/SQL)."""

    code = "STRUCTURED_OUTPUT_ERROR"

    def __init__(self, schema_name: str, raw_output: str, parse_error: str) -> None:
        super().__init__(
            f"Failed to generate valid {schema_name}: {parse_error}",
            details={
                "schema_name": schema_name,
                "raw_output": raw_output[:500],
                "parse_error": parse_error,
            },
        )


class SQLValidationError(StructuredOutputError):
    """Generated SQL failed validation."""

    code = "SQL_VALIDATION_ERROR"

    def __init__(self, sql: str, reason: str) -> None:
        super().__init__(
            schema_name="SQL",
            raw_output=sql,
            parse_error=reason,
        )


class SQLExecutionError(LLMError):
    """SQL execution failed."""

    code = "SQL_EXECUTION_ERROR"

    def __init__(self, sql: str, error: str) -> None:
        super().__init__(
            f"SQL execution failed: {error}",
            details={"sql": sql[:500], "error": error},
        )


# =============================================================================
# RAG Errors
# =============================================================================


class RAGError(LLMError):
    """Base exception for RAG-related errors."""

    code = "RAG_ERROR"


class EmbeddingError(RAGError):
    """Error during embedding generation."""

    code = "EMBEDDING_ERROR"

    def __init__(self, reason: str) -> None:
        super().__init__(f"Embedding generation failed: {reason}")


class RetrievalError(RAGError):
    """Error during document retrieval."""

    code = "RETRIEVAL_ERROR"

    def __init__(self, reason: str, query: str | None = None) -> None:
        details: dict[str, Any] = {"reason": reason}
        if query:
            details["query"] = query[:200]
        super().__init__(f"Document retrieval failed: {reason}", details=details)


class IngestionError(RAGError):
    """Error during document ingestion."""

    code = "INGESTION_ERROR"

    def __init__(self, reason: str, source: str | None = None) -> None:
        details: dict[str, Any] = {"reason": reason}
        if source:
            details["source"] = source
        super().__init__(f"Document ingestion failed: {reason}", details=details)


# =============================================================================
# Service Errors
# =============================================================================


class LLMServiceError(LLMError):
    """LLM service layer error."""

    code = "LLM_SERVICE_ERROR"


class LLMNotAvailableError(LLMServiceError):
    """LLM service not available (disabled or failed to initialize)."""

    code = "LLM_NOT_AVAILABLE"

    def __init__(self, reason: str = "LLM features are disabled") -> None:
        super().__init__(reason)


class RouterError(LLMError):
    """Error in semantic routing."""

    code = "ROUTER_ERROR"

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            f"Failed to route query: {reason}",
            details={"query": query[:200], "reason": reason},
        )
