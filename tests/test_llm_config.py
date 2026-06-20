"""Tests for LLM hardware-aware model selection.

Verifies that the VRAM-aware tiering picks the large Gemma 4 GPU model on
capable GPUs and falls back to the RAM-based standard/lite tiers otherwise.
"""
from __future__ import annotations

from src.llm.config import (
    MODEL_CONFIGS,
    HardwareCapabilities,
    LLMSettings,
    ModelSize,
)
from src.llm.reranker import RerankerService


def _hw(
    *,
    available_ram_gb: float,
    has_cuda: bool = False,
    cuda_vram_gb: float | None = None,
) -> HardwareCapabilities:
    """Build a HardwareCapabilities fixture with sensible defaults."""
    return HardwareCapabilities(
        total_ram_gb=available_ram_gb,
        available_ram_gb=available_ram_gb,
        cpu_cores=24,
        has_avx2=True,
        has_avx512=False,
        has_metal=False,
        has_cuda=has_cuda,
        cuda_vram_gb=cuda_vram_gb,
    )


class TestRecommendedModel:
    """Test VRAM-aware model recommendation."""

    def test_capable_gpu_selects_large(self) -> None:
        """A 24GB CUDA GPU (e.g. RTX 5090) should select the large model."""
        hw = _hw(available_ram_gb=62.0, has_cuda=True, cuda_vram_gb=24.0)
        assert hw.can_run_large is True
        assert hw.recommended_model == ModelSize.LARGE

    def test_small_gpu_does_not_select_large(self) -> None:
        """A GPU below the 18GB VRAM threshold falls back to RAM-based tiers."""
        hw = _hw(available_ram_gb=32.0, has_cuda=True, cuda_vram_gb=8.0)
        assert hw.can_run_large is False
        assert hw.recommended_model == ModelSize.STANDARD

    def test_cpu_with_ram_selects_standard(self) -> None:
        """A CPU-only machine with enough RAM selects the standard model."""
        hw = _hw(available_ram_gb=16.0)
        assert hw.can_run_large is False
        assert hw.recommended_model == ModelSize.STANDARD

    def test_low_ram_selects_lite(self) -> None:
        """A constrained machine selects the lite model."""
        hw = _hw(available_ram_gb=5.0)
        assert hw.recommended_model == ModelSize.LITE

    def test_no_vram_value_does_not_select_large(self) -> None:
        """has_cuda True but unknown VRAM must not select the large model."""
        hw = _hw(available_ram_gb=62.0, has_cuda=True, cuda_vram_gb=None)
        assert hw.can_run_large is False


class TestModelConfigs:
    """Test the registered model variants."""

    def test_large_model_registered(self) -> None:
        """The large tier maps to the Gemma 4 26B-A4B GGUF."""
        cfg = MODEL_CONFIGS[ModelSize.LARGE]
        assert cfg.size == ModelSize.LARGE
        assert cfg.filename == "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf"
        assert cfg.vram_required_gb == 18.0

    def test_all_sizes_have_configs(self) -> None:
        """Every ModelSize has a corresponding config."""
        for size in ModelSize:
            assert size in MODEL_CONFIGS
            assert MODEL_CONFIGS[size].size == size

    def test_cpu_models_have_no_vram_requirement(self) -> None:
        """Standard/lite are CPU-friendly and carry no VRAM requirement."""
        assert MODEL_CONFIGS[ModelSize.STANDARD].vram_required_gb is None
        assert MODEL_CONFIGS[ModelSize.LITE].vram_required_gb is None


class TestKVCacheSettings:
    """Test KV-cache / context override settings."""

    def test_kv_cache_defaults(self) -> None:
        """KV cache defaults to q8_0 with flash attention enabled."""
        s = LLMSettings()
        assert s.kv_cache_type == "q8_0"
        assert s.flash_attention is True
        assert s.context_length_override is None

    def test_large_model_uses_extended_context(self) -> None:
        """The large model uses an extended 32K context (q8_0 KV headroom)."""
        assert MODEL_CONFIGS[ModelSize.LARGE].context_length == 32768


class TestEmbeddingSettings:
    """Test RAG embedding / reranker settings."""

    def test_embedding_defaults(self) -> None:
        """Defaults to BGE-M3 at 1024 dims with reranking enabled."""
        s = LLMSettings()
        assert s.embedding_model == "BAAI/bge-m3"
        assert s.embedding_dim == 1024
        assert s.reranker_enabled is True
        assert s.reranker_model == "BAAI/bge-reranker-v2-m3"


class TestReranker:
    """Test the reranker's graceful-fallback behavior (no model download)."""

    def test_disabled_reranker_reports_unavailable(self) -> None:
        """reranker_enabled=False makes the service report disabled."""
        svc = RerankerService(settings=LLMSettings(reranker_enabled=False))
        assert svc.is_enabled is False

    def test_disabled_rerank_preserves_order(self) -> None:
        """A disabled reranker returns the identity order with zero scores."""
        svc = RerankerService(settings=LLMSettings(reranker_enabled=False))
        ranked = svc._rank_sync("frage", ["a", "b", "c"])
        assert [idx for idx, _ in ranked] == [0, 1, 2]
        assert all(score == 0.0 for _, score in ranked)
