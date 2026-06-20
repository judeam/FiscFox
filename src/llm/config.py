"""LLM configuration and hardware detection for FiscFox.

Provides configuration models for llama-cpp-python inference,
hardware capability detection, and model path management.
"""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class ModelSize(StrEnum):
    """Available model sizes for FiscFox LLM."""

    LARGE = "large"  # Gemma 4 26B-A4B (MoE, ~3.8B active, ~17GB, needs ~18GB VRAM)
    STANDARD = "standard"  # Qwen3-4B-Instruct-2507 (~2.5GB, 6GB RAM)
    LITE = "lite"  # Phi-3.5 Mini (~2.3GB, 4GB RAM)


class InferenceDevice(StrEnum):
    """Inference device types."""

    CPU = "cpu"
    GPU_AUTO = "gpu_auto"  # Auto-detect and use available GPU layers
    METAL = "metal"  # Apple Silicon
    CUDA = "cuda"  # NVIDIA GPU


@dataclass(frozen=True)
class HardwareCapabilities:
    """Detected hardware capabilities for inference optimization."""

    total_ram_gb: float
    available_ram_gb: float
    cpu_cores: int
    has_avx2: bool
    has_avx512: bool
    has_metal: bool  # Apple Silicon
    has_cuda: bool  # NVIDIA GPU detected
    cuda_vram_gb: float | None

    @property
    def can_run_standard(self) -> bool:
        """Check if hardware can run standard Qwen3-4B model."""
        return self.available_ram_gb >= 6.0  # 2.5GB model + 3.5GB overhead

    @property
    def can_run_lite(self) -> bool:
        """Check if hardware can run lite Phi-3.5 model."""
        return self.available_ram_gb >= 4.0  # 2.3GB model + 1.7GB overhead

    @property
    def can_run_large(self) -> bool:
        """Check if a capable GPU can run the large Gemma 4 26B-A4B model.

        The MoE weights (~17GB at Q4_K_M) plus the KV cache need a GPU with
        enough VRAM for full offload; CPU-only inference of a 26B model is too
        slow to be usable, so this requires CUDA with >= 18GB VRAM.
        """
        return (
            self.has_cuda
            and self.cuda_vram_gb is not None
            and self.cuda_vram_gb >= 18.0
        )

    @property
    def recommended_model(self) -> ModelSize:
        """Recommend model size based on available resources.

        Prefers the large GPU model when a capable CUDA GPU is present, then
        falls back to RAM-based standard/lite selection for laptop-class CPUs.
        """
        if self.can_run_large:
            return ModelSize.LARGE
        elif self.can_run_standard:
            return ModelSize.STANDARD
        elif self.can_run_lite:
            return ModelSize.LITE
        else:
            # Return lite anyway, let load fail with proper error
            return ModelSize.LITE

    @property
    def recommended_device(self) -> InferenceDevice:
        """Recommend inference device based on hardware."""
        if self.has_metal:
            return InferenceDevice.METAL
        elif self.has_cuda and self.cuda_vram_gb and self.cuda_vram_gb >= 6.0:
            return InferenceDevice.CUDA
        else:
            return InferenceDevice.CPU

    @property
    def recommended_threads(self) -> int:
        """Recommend thread count for CPU inference."""
        # Use physical cores, leave 2 for system/FastAPI
        return max(1, self.cpu_cores - 2)


class ModelConfig(BaseModel):
    """Configuration for a specific model variant."""

    name: str = Field(..., description="Human-readable model name")
    filename: str = Field(..., description="GGUF filename")
    size: ModelSize
    context_length: int = Field(default=8192, ge=512, le=131072)
    batch_size: int = Field(default=512, ge=1, le=2048)
    ram_required_gb: float = Field(..., ge=1.0)
    vram_required_gb: float | None = Field(
        default=None,
        ge=1.0,
        description="VRAM needed for full GPU offload (None = CPU-friendly model)",
    )

    # Model-specific parameters
    rope_freq_base: float | None = Field(
        default=None, description="RoPE frequency base"
    )
    rope_freq_scale: float | None = Field(
        default=None, description="RoPE frequency scale"
    )


class LLMSettings(BaseModel):
    """Main LLM configuration settings.

    Can be loaded from environment variables with FISCFOX_LLM_ prefix.
    """

    # Feature toggle
    enabled: bool = Field(
        default=True, description="Enable/disable LLM features globally"
    )

    # Model selection
    model_size: ModelSize = Field(
        default=ModelSize.STANDARD, description="Model size to use (standard or lite)"
    )

    # Inference backend: "llamacpp" (in-process GGUF) or "ollama" (shared server).
    # Ollama shares one model pool with other local apps, avoiding a second copy
    # of the model competing for VRAM on a single GPU.
    backend: str = Field(
        default="llamacpp",
        description="Inference backend: 'llamacpp' or 'ollama'",
    )
    ollama_host: str = Field(
        default="http://localhost:11434", description="Ollama server URL"
    )
    ollama_model: str = Field(
        default="gemma4", description="Ollama model tag used for the assistant"
    )

    # Paths
    models_dir: Path = Field(
        default=Path("data/models/llm"),
        description="Directory containing GGUF model files",
    )

    # Inference settings
    context_length: int = Field(
        default=8192, ge=512, le=131072, description="Context window size in tokens"
    )
    batch_size: int = Field(
        default=512, ge=1, le=2048, description="Batch size for prompt processing"
    )

    # Hardware settings
    n_gpu_layers: int = Field(
        default=-1, ge=-1, description="Layers to offload to GPU (-1 = auto)"
    )
    n_threads: int | None = Field(
        default=None, ge=1, description="CPU threads (None = auto-detect)"
    )

    # KV cache / attention (trade VRAM for longer context)
    flash_attention: bool = Field(
        default=True,
        description="Enable flash attention (also required for KV cache quantization)",
    )
    kv_cache_type: str = Field(
        default="q8_0",
        description="KV cache dtype: f16 (full), q8_0 (~half VRAM, near-lossless), q4_0 (quarter)",
    )
    context_length_override: int | None = Field(
        default=None,
        ge=512,
        le=131072,
        description="Override the per-model context window (None = use model default)",
    )

    # RAG embeddings (sentence-transformers + sqlite-vec)
    embedding_model: str = Field(
        default="BAAI/bge-m3",
        description="sentence-transformers model for RAG embeddings",
    )
    embedding_dim: int = Field(
        default=1024,
        ge=64,
        le=4096,
        description="Embedding dimension (must match embedding_model and the vec0 schema)",
    )
    embedding_query_prefix: str = Field(
        default="",
        description="Instruction prefix prepended to queries (e.g. 'query: ' for e5/Qwen3)",
    )
    embedding_passage_prefix: str = Field(
        default="",
        description="Instruction prefix prepended to passages (e.g. 'passage: ' for e5)",
    )
    embedding_device: str | None = Field(
        default=None,
        description="Device for embeddings/reranker: 'cuda', 'cpu', or None (auto-detect)",
    )

    # RAG reranker (cross-encoder second stage over retrieved candidates)
    reranker_enabled: bool = Field(
        default=True,
        description="Enable cross-encoder reranking of retrieved candidates",
    )
    reranker_model: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        description="Cross-encoder model for reranking",
    )

    # Generation defaults
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)

    # Behavioral settings
    auto_select_model: bool = Field(
        default=True, description="Auto-select model based on hardware"
    )
    enable_streaming: bool = Field(
        default=True, description="Enable token streaming for responses"
    )
    response_cache_ttl: int = Field(
        default=300, ge=0, description="Response cache TTL in seconds (0 = disabled)"
    )

    # Timeouts
    inference_timeout: float = Field(
        default=120.0, ge=1.0, description="Inference timeout in seconds"
    )
    load_timeout: float = Field(
        default=300.0, ge=10.0, description="Model load timeout in seconds"
    )

    @field_validator("models_dir", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        """Resolve model directory path."""
        path = Path(v)
        if not path.is_absolute():
            # Resolve relative to project root
            project_root = Path(__file__).parent.parent.parent
            path = project_root / path
        return path

    @classmethod
    def from_env(cls) -> LLMSettings:
        """Load settings from environment variables."""
        env_values: dict[str, Any] = {}

        prefix = "FISCFOX_LLM_"
        for key, field_info in cls.model_fields.items():
            env_key = f"{prefix}{key.upper()}"
            env_value = os.environ.get(env_key)
            if env_value is not None:
                # Handle boolean conversion
                if field_info.annotation == bool:
                    env_values[key] = env_value.lower() in ("true", "1", "yes")
                # Handle ModelSize enum
                elif key == "model_size":
                    env_values[key] = ModelSize(env_value.lower())
                else:
                    env_values[key] = env_value

        return cls(**env_values)


# =============================================================================
# Pre-configured Model Variants
# =============================================================================

LARGE_MODEL = ModelConfig(
    name="Gemma 4 26B-A4B Instruct",
    filename="gemma-4-26B-A4B-it-UD-Q4_K_M.gguf",
    size=ModelSize.LARGE,
    # Gemma 4 supports up to 256K context. ~16GB weights + a q8_0 KV cache at 32K
    # fit in 24GB VRAM *when the GPU is otherwise free* (unload other resident
    # models, e.g. `ollama stop ...`). Raise via FISCFOX_LLM_CONTEXT_LENGTH_OVERRIDE.
    context_length=32768,
    batch_size=512,
    ram_required_gb=18.0,  # ~17GB weights + overhead (system RAM if run on CPU)
    vram_required_gb=18.0,  # full GPU offload target for the RTX 50-series tier
)

STANDARD_MODEL = ModelConfig(
    name="Qwen3-4B-Instruct-2507",
    filename="Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
    size=ModelSize.STANDARD,
    context_length=32768,  # Qwen3 supports 32K natively, 262K with YaRN
    batch_size=512,
    ram_required_gb=2.5,
)

LITE_MODEL = ModelConfig(
    name="Phi-3.5 Mini Instruct",
    filename="Phi-3.5-mini-instruct-Q4_K_M.gguf",
    size=ModelSize.LITE,
    context_length=4096,
    batch_size=256,
    ram_required_gb=2.3,
)

MODEL_CONFIGS: dict[ModelSize, ModelConfig] = {
    ModelSize.LARGE: LARGE_MODEL,
    ModelSize.STANDARD: STANDARD_MODEL,
    ModelSize.LITE: LITE_MODEL,
}


# =============================================================================
# Hardware Detection
# =============================================================================


def detect_hardware() -> HardwareCapabilities:
    """Detect system hardware capabilities for inference optimization.

    Returns:
        HardwareCapabilities with detected system specs
    """
    try:
        import psutil

        # RAM detection
        mem = psutil.virtual_memory()
        total_ram_gb = mem.total / (1024**3)
        available_ram_gb = mem.available / (1024**3)

        # CPU detection
        cpu_cores = psutil.cpu_count(logical=False) or 4
    except ImportError:
        logger.warning("psutil not installed, using default hardware values")
        total_ram_gb = 16.0
        available_ram_gb = 8.0
        cpu_cores = 4

    # CPU instruction set detection
    has_avx2 = False
    has_avx512 = False
    try:
        import cpuinfo

        info = cpuinfo.get_cpu_info()
        flags = info.get("flags", [])
        has_avx2 = "avx2" in flags
        has_avx512 = any("avx512" in f for f in flags)
    except ImportError:
        logger.debug("cpuinfo not installed, CPU features unknown")

    # Metal detection (Apple Silicon)
    has_metal = platform.system() == "Darwin" and platform.machine() == "arm64"

    # CUDA detection — prefer torch, fall back to nvidia-smi (no torch dependency)
    has_cuda = False
    cuda_vram_gb: float | None = None
    try:
        import torch

        if torch.cuda.is_available():
            has_cuda = True
            cuda_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    except ImportError:
        pass

    if not has_cuda:
        # Torch-free fallback: query the NVIDIA driver directly. Lets the app
        # detect the GPU (and auto-select the large model) without the heavy torch
        # dependency, since inference runs through llama.cpp (CUDA), not torch.
        try:
            import shutil
            import subprocess

            smi = shutil.which("nvidia-smi")
            if smi:
                result = subprocess.run(
                    [smi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                lines = result.stdout.strip().splitlines()
                if lines and lines[0].strip():
                    has_cuda = True
                    cuda_vram_gb = float(lines[0].strip()) / 1024.0  # MiB -> GiB
        except Exception:
            pass

    return HardwareCapabilities(
        total_ram_gb=total_ram_gb,
        available_ram_gb=available_ram_gb,
        cpu_cores=cpu_cores,
        has_avx2=has_avx2,
        has_avx512=has_avx512,
        has_metal=has_metal,
        has_cuda=has_cuda,
        cuda_vram_gb=cuda_vram_gb,
    )


def get_memory_pressure() -> float:
    """Get current memory pressure (0.0 = low, 1.0 = critical).

    Returns:
        Memory pressure ratio
    """
    try:
        import psutil

        mem = psutil.virtual_memory()
        used_ratio = mem.used / mem.total

        # Map to pressure: <70% = 0.0, 70-85% = 0.0-0.5, 85-95% = 0.5-1.0, >95% = 1.0
        if used_ratio < 0.70:
            return 0.0
        elif used_ratio < 0.85:
            return (used_ratio - 0.70) / 0.15 * 0.5
        elif used_ratio < 0.95:
            return 0.5 + (used_ratio - 0.85) / 0.10 * 0.5
        else:
            return 1.0
    except ImportError:
        return 0.5  # Default to medium pressure if psutil unavailable


# =============================================================================
# Singleton Settings Instance
# =============================================================================

_settings: LLMSettings | None = None


def get_llm_settings() -> LLMSettings:
    """Get or create LLM settings singleton."""
    global _settings
    if _settings is None:
        _settings = LLMSettings.from_env()
    return _settings
