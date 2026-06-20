"""Tests for the Ollama backend wiring (no live server required)."""
from __future__ import annotations

from src.llm.config import LLMSettings
from src.llm.ollama_backend import OllamaBackend


class TestOllamaSettings:
    """Backend selection settings and defaults."""

    def test_defaults_to_llamacpp(self) -> None:
        s = LLMSettings()
        assert s.backend == "llamacpp"
        assert s.ollama_host == "http://localhost:11434"
        assert s.ollama_model == "gemma4"

    def test_ollama_backend_selectable(self) -> None:
        s = LLMSettings(backend="ollama", ollama_model="gemma4:12b")
        assert s.backend == "ollama"
        assert s.ollama_model == "gemma4:12b"


class TestOllamaBackend:
    """OllamaBackend request shaping (pure, no network)."""

    def test_host_trailing_slash_stripped(self) -> None:
        be = OllamaBackend("http://localhost:11434/", "gemma4")
        assert be._host == "http://localhost:11434"

    def test_options_only_includes_set_values(self) -> None:
        assert OllamaBackend._options(None, None, None) == {}
        opts = OllamaBackend._options(256, 0.1, 0.9)
        assert opts == {"num_predict": 256, "temperature": 0.1, "top_p": 0.9}

    def test_options_partial(self) -> None:
        assert OllamaBackend._options(128, None, None) == {"num_predict": 128}


class TestServiceUsesBackend:
    """LLMService should select the Ollama path when configured."""

    def test_service_constructs_ollama_backend(self) -> None:
        from src.llm.service import LLMService

        svc = LLMService(settings=LLMSettings(backend="ollama"))
        assert svc._backend == "ollama"
        assert svc._ollama is not None
        # not ready until ensure_loaded() health-checks the server
        assert svc.is_ready is False
