"""LLM model lifecycle management for FiscFox.

Handles GGUF model loading, unloading, memory monitoring,
and model switching between standard and lite variants.
"""

from __future__ import annotations

import asyncio
import gc
import logging
from typing import TYPE_CHECKING, Any

from src.llm.config import (
    MODEL_CONFIGS,
    HardwareCapabilities,
    LLMSettings,
    ModelConfig,
    ModelSize,
    detect_hardware,
    get_llm_settings,
    get_memory_pressure,
)
from src.llm.exceptions import (
    InsufficientResourcesError,
    ModelNotFoundError,
    ModelNotLoadedError,
    ModelSwitchError,
)

if TYPE_CHECKING:
    from llama_cpp import Llama

logger = logging.getLogger(__name__)


class LLMModelManager:
    """Manages LLM model lifecycle: loading, unloading, switching.

    Thread-safe model management with memory monitoring.
    Designed for single-model-at-a-time operation to minimize
    RAM usage on laptop-class hardware.
    """

    def __init__(self, settings: LLMSettings | None = None):
        """Initialize model manager.

        Args:
            settings: LLM settings (defaults to auto-detected)
        """
        self._settings = settings or get_llm_settings()
        self._model: Llama | None = None
        self._current_config: ModelConfig | None = None
        self._hardware: HardwareCapabilities | None = None
        self._lock = asyncio.Lock()
        self._loaded = False
        self._is_loading = False

    @property
    def is_loaded(self) -> bool:
        """Check if a model is currently loaded."""
        return self._loaded and self._model is not None

    @property
    def is_loading(self) -> bool:
        """Check if model is currently being loaded."""
        return self._is_loading

    @property
    def current_model(self) -> ModelConfig | None:
        """Get currently loaded model configuration."""
        return self._current_config

    @property
    def hardware(self) -> HardwareCapabilities:
        """Get detected hardware capabilities (cached)."""
        if self._hardware is None:
            self._hardware = detect_hardware()
        return self._hardware

    @property
    def model(self) -> Llama:
        """Get the loaded Llama model instance.

        Raises:
            ModelNotLoadedError: If no model is loaded
        """
        if not self.is_loaded or self._model is None:
            raise ModelNotLoadedError()
        return self._model

    @property
    def settings(self) -> LLMSettings:
        """Get current LLM settings."""
        return self._settings

    def get_model_path(self, model_size: ModelSize) -> str:
        """Get full path to model file.

        Args:
            model_size: Model size variant

        Returns:
            Full path to GGUF file as string
        """
        config = MODEL_CONFIGS[model_size]
        return str(self._settings.models_dir / config.filename)

    def _validate_resources(self, config: ModelConfig) -> None:
        """Validate hardware can support requested model.

        Args:
            config: Model configuration to validate

        Raises:
            InsufficientResourcesError: If hardware insufficient
        """
        hw = self.hardware

        # GPU-targeted models (e.g. Gemma 4 26B-A4B) live in VRAM when offloaded,
        # so validate against VRAM rather than system RAM. mmap'd weights keep the
        # system-RAM footprint small once layers are on the GPU.
        gpu_offload = self._settings.n_gpu_layers != 0
        if config.vram_required_gb is not None and hw.has_cuda and gpu_offload:
            available_vram = hw.cuda_vram_gb or 0.0
            if available_vram < config.vram_required_gb:
                raise InsufficientResourcesError(
                    f"Insufficient VRAM for {config.name}. "
                    f"Available: {available_vram:.1f}GB, "
                    f"Required: {config.vram_required_gb:.1f}GB (full GPU offload)",
                    required_ram_gb=config.vram_required_gb,
                    available_ram_gb=available_vram,
                )
            return

        # 1.5GB safety margin for system and application
        required_ram = config.ram_required_gb + 1.5

        if hw.available_ram_gb < required_ram:
            raise InsufficientResourcesError(
                f"Insufficient RAM for {config.name}. "
                f"Available: {hw.available_ram_gb:.1f}GB, "
                f"Required: {required_ram:.1f}GB (model + overhead)",
                required_ram_gb=required_ram,
                available_ram_gb=hw.available_ram_gb,
            )

    def _validate_model_file(self, config: ModelConfig) -> str:
        """Validate model file exists.

        Args:
            config: Model configuration

        Returns:
            Path to model file

        Raises:
            ModelNotFoundError: If file doesn't exist
        """
        model_path = self._settings.models_dir / config.filename

        if not model_path.exists():
            raise ModelNotFoundError(
                str(self._settings.models_dir),
                config.filename,
            )

        return str(model_path)

    async def load_model(
        self,
        model_size: ModelSize | None = None,
        force_reload: bool = False,
    ) -> ModelConfig:
        """Load a model into memory.

        Args:
            model_size: Model size to load (None = auto-select)
            force_reload: Force reload even if same model loaded

        Returns:
            Loaded model configuration

        Raises:
            ModelNotFoundError: If model file not found
            InsufficientResourcesError: If hardware insufficient
        """
        async with self._lock:
            # Auto-select model if not specified
            if model_size is None:
                if self._settings.auto_select_model:
                    model_size = self.hardware.recommended_model
                    logger.info(f"Auto-selected model size: {model_size.value}")
                else:
                    model_size = self._settings.model_size

            config = MODEL_CONFIGS[model_size]

            # Skip if already loaded
            if (
                self.is_loaded
                and self._current_config
                and self._current_config.size == model_size
                and not force_reload
            ):
                logger.info(f"Model {config.name} already loaded, skipping")
                return config

            # Unload existing model first
            if self.is_loaded:
                await self._unload_internal()

            # Validate resources and file
            self._validate_resources(config)
            model_path = self._validate_model_file(config)

            # Determine inference settings
            hw = self.hardware
            n_threads = self._settings.n_threads or hw.recommended_threads
            n_gpu_layers = self._settings.n_gpu_layers

            # KV-cache quantization: trade a little quality for big VRAM savings,
            # letting large models hold much longer context. Quantized KV requires
            # flash attention, so enable it automatically in that case.
            kv_types = {"f16": 1, "q8_0": 8, "q4_0": 2}  # ggml type ids
            kv_type = kv_types.get(self._settings.kv_cache_type.lower(), 1)
            flash_attn = self._settings.flash_attention or kv_type != 1
            n_ctx = self._settings.context_length_override or config.context_length

            logger.info(
                f"Loading {config.name} from {model_path} "
                f"(threads={n_threads}, gpu_layers={n_gpu_layers}, "
                f"n_ctx={n_ctx}, kv_cache={self._settings.kv_cache_type})"
            )

            # Mark as loading
            self._is_loading = True

            try:
                # Load model (blocking operation - run in thread)
                def _load() -> Llama:
                    from llama_cpp import Llama

                    return Llama(
                        model_path=model_path,
                        n_ctx=n_ctx,
                        n_batch=config.batch_size,
                        n_threads=n_threads,
                        n_gpu_layers=n_gpu_layers,
                        flash_attn=flash_attn,
                        type_k=kv_type,
                        type_v=kv_type,
                        verbose=False,
                        use_mmap=True,  # Memory-map for fast loading
                        use_mlock=False,  # Don't lock in RAM (allow swapping if needed)
                    )

                loop = asyncio.get_event_loop()
                self._model = await loop.run_in_executor(None, _load)
                self._current_config = config
                self._loaded = True

                logger.info(f"Successfully loaded {config.name}")
                return config
            finally:
                self._is_loading = False

    async def _unload_internal(self) -> None:
        """Internal unload without lock (caller must hold lock)."""
        if self._model is not None:
            model_name = self._current_config.name if self._current_config else "unknown"
            logger.info(f"Unloading model {model_name}")

            # Delete model and force garbage collection
            del self._model
            self._model = None
            self._current_config = None
            self._loaded = False

            gc.collect()
            logger.info("Model unloaded, memory freed")

    async def unload_model(self) -> None:
        """Unload current model and free memory."""
        async with self._lock:
            await self._unload_internal()

    async def switch_model(self, new_size: ModelSize) -> ModelConfig:
        """Switch to a different model size.

        Unloads current model first to minimize peak RAM usage.

        Args:
            new_size: Target model size

        Returns:
            New model configuration

        Raises:
            ModelSwitchError: If switch fails
        """
        try:
            current_name = (
                self._current_config.name if self._current_config else "none"
            )
            new_config = MODEL_CONFIGS[new_size]

            logger.info(f"Switching model: {current_name} -> {new_config.name}")

            # Unload and load with lock held across both operations
            async with self._lock:
                if self.is_loaded:
                    await self._unload_internal()

            # Load new model (releases lock during load)
            return await self.load_model(new_size)

        except Exception as e:
            raise ModelSwitchError(f"Failed to switch model: {e}") from e

    async def auto_downgrade_if_needed(self) -> bool:
        """Automatically switch to lite mode if memory pressure is high.

        Returns:
            True if downgraded, False otherwise
        """
        pressure = get_memory_pressure()

        if (
            pressure > 0.8
            and self._current_config
            and self._current_config.size == ModelSize.STANDARD
        ):
            logger.warning(
                f"High memory pressure ({pressure:.1%}), downgrading to lite mode"
            )
            await self.switch_model(ModelSize.LITE)
            return True

        return False

    def get_status(self) -> dict[str, Any]:
        """Get model manager status.

        Returns:
            Status dict with model info and hardware capabilities
        """
        hw = self.hardware

        return {
            "is_loaded": self.is_loaded,
            "current_model": (
                {
                    "name": self._current_config.name,
                    "size": self._current_config.size.value,
                    "context_length": self._current_config.context_length,
                    "ram_required_gb": self._current_config.ram_required_gb,
                }
                if self._current_config
                else None
            ),
            "hardware": {
                "total_ram_gb": round(hw.total_ram_gb, 1),
                "available_ram_gb": round(hw.available_ram_gb, 1),
                "cpu_cores": hw.cpu_cores,
                "has_avx2": hw.has_avx2,
                "has_avx512": hw.has_avx512,
                "has_metal": hw.has_metal,
                "has_cuda": hw.has_cuda,
                "cuda_vram_gb": (
                    round(hw.cuda_vram_gb, 1) if hw.cuda_vram_gb else None
                ),
                "recommended_model": hw.recommended_model.value,
                "recommended_device": hw.recommended_device.value,
            },
            "settings": {
                "models_dir": str(self._settings.models_dir),
                "context_length": self._settings.context_length,
                "auto_select_model": self._settings.auto_select_model,
            },
            "memory_pressure": round(get_memory_pressure(), 2),
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_manager: LLMModelManager | None = None


def get_model_manager() -> LLMModelManager:
    """Get or create the model manager singleton."""
    global _manager
    if _manager is None:
        _manager = LLMModelManager()
    return _manager
