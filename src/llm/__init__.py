"""FiscFox LLM Module.

Local-first AI integration for German freelancer tax management.
Privacy-first design with complete GDPR compliance.

Components:
- config: Hardware detection and model configuration
- manager: Model lifecycle management
- service: Central LLM service with async inference
- exceptions: LLM-specific exception hierarchy

Usage:
    from src.llm import get_llm_service, LLMService

    # In FastAPI lifespan
    service = await initialize_llm_service()

    # Generate response
    response = await service.generate("What is the VAT rate for software?")
"""

from src.llm.config import (
    HardwareCapabilities,
    InferenceDevice,
    LLMSettings,
    ModelConfig,
    ModelSize,
    detect_hardware,
    get_llm_settings,
    get_memory_pressure,
)
from src.llm.exceptions import (
    ContextLengthExceededError,
    EmbeddingError,
    GenerationError,
    InferenceError,
    InferenceTimeoutError,
    IngestionError,
    InsufficientResourcesError,
    LLMError,
    LLMNotAvailableError,
    LLMServiceError,
    ModelNotFoundError,
    ModelNotLoadedError,
    ModelSwitchError,
    RAGError,
    RetrievalError,
    RouterError,
    SQLExecutionError,
    SQLValidationError,
    StructuredOutputError,
)
from src.llm.manager import LLMModelManager, get_model_manager
from src.llm.schemas import (
    AfaMethod,
    AfaSuggestion,
    ConfidenceLevel,
    ExpenseCategory,
    ExpenseSchema,
    IntentClassification,
    InvoiceRisk,
    InvoiceRiskAssessment,
    MLPredictionExplanation,
    SQLQuery,
    SQLResult,
    TaxAnswer,
    TaxLawSource,
    UserIntent,
    VatRate,
)
from src.llm.service import (
    LLMResponse,
    LLMService,
    get_llm_service,
    initialize_llm_service,
    shutdown_llm_service,
)
from src.llm.structured import StructuredGenerator, get_structured_generator

__all__ = [
    # Config
    "HardwareCapabilities",
    "InferenceDevice",
    "LLMSettings",
    "ModelConfig",
    "ModelSize",
    "detect_hardware",
    "get_llm_settings",
    "get_memory_pressure",
    # Exceptions
    "ContextLengthExceededError",
    "EmbeddingError",
    "GenerationError",
    "InferenceError",
    "InferenceTimeoutError",
    "IngestionError",
    "InsufficientResourcesError",
    "LLMError",
    "LLMNotAvailableError",
    "LLMServiceError",
    "ModelNotFoundError",
    "ModelNotLoadedError",
    "ModelSwitchError",
    "RAGError",
    "RetrievalError",
    "RouterError",
    "SQLExecutionError",
    "SQLValidationError",
    "StructuredOutputError",
    # Manager
    "LLMModelManager",
    "get_model_manager",
    # Service
    "LLMResponse",
    "LLMService",
    "get_llm_service",
    "initialize_llm_service",
    "shutdown_llm_service",
    # Schemas
    "AfaMethod",
    "AfaSuggestion",
    "ConfidenceLevel",
    "ExpenseCategory",
    "ExpenseSchema",
    "IntentClassification",
    "InvoiceRisk",
    "InvoiceRiskAssessment",
    "MLPredictionExplanation",
    "SQLQuery",
    "SQLResult",
    "TaxAnswer",
    "TaxLawSource",
    "UserIntent",
    "VatRate",
    # Structured Generation
    "StructuredGenerator",
    "get_structured_generator",
]
