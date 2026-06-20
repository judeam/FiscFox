"""Ollama HTTP backend for FiscFox.

Talks to a local Ollama server (``/api/chat``) instead of loading a GGUF
in-process via llama.cpp. Sharing Ollama's model pool means there's only ever
one copy of a model in VRAM, so FiscFox no longer fights other local Ollama
apps for GPU memory on a single-GPU machine.

httpx is imported lazily so the dependency is only required when the Ollama
backend is actually selected.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Raised when the Ollama server is unreachable or returns an error."""


class OllamaBackend:
    """Thin async client for the Ollama chat API."""

    def __init__(self, host: str, model: str):
        self._host = host.rstrip("/")
        self._model = model

    def _client(self, timeout: float):
        try:
            import httpx
        except ImportError as e:  # pragma: no cover - depends on install extras
            raise OllamaError(
                "httpx is required for the Ollama backend. "
                "Install it with: uv pip install httpx"
            ) from e
        return httpx.AsyncClient(base_url=self._host, timeout=timeout)

    @staticmethod
    def _options(
        max_tokens: int | None, temperature: float | None, top_p: float | None
    ) -> dict[str, Any]:
        opts: dict[str, Any] = {}
        if max_tokens is not None:
            opts["num_predict"] = max_tokens
        if temperature is not None:
            opts["temperature"] = temperature
        if top_p is not None:
            opts["top_p"] = top_p
        return opts

    async def health(self) -> bool:
        """Return True if the Ollama server responds to /api/tags."""
        try:
            async with self._client(5.0) as client:
                resp = await client.get("/api/tags")
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Non-streaming chat completion. Returns {content, tokens}."""
        body = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": self._options(max_tokens, temperature, top_p),
        }
        async with self._client(timeout) as client:
            resp = await client.post("/api/chat", json=body)
            if resp.status_code != 200:
                raise OllamaError(
                    f"Ollama /api/chat returned {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
        content = data.get("message", {}).get("content", "")
        tokens = int(data.get("eval_count", 0)) + int(data.get("prompt_eval_count", 0))
        return {"content": content, "tokens": tokens}

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        timeout: float = 120.0,
    ) -> AsyncIterator[str]:
        """Streaming chat completion. Yields content pieces as they arrive."""
        body = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": self._options(max_tokens, temperature, top_p),
        }
        async with self._client(timeout) as client:
            async with client.stream("POST", "/api/chat", json=body) as resp:
                if resp.status_code != 200:
                    text = (await resp.aread()).decode("utf-8", "replace")
                    raise OllamaError(
                        f"Ollama stream returned {resp.status_code}: {text[:200]}"
                    )
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
