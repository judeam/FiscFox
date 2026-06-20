"""Tool-calling financial assistant for FiscFox.

A small, model-agnostic function-calling loop over the local LLM:
1. the model decides whether a tool is needed (emitting a JSON tool call),
2. the tool runs against the user's REAL data (tax calculators / SQL),
3. the model answers in the user's language using the returned data.

This is robust to Gemma's JSON style and does not depend on llama.cpp's
per-model `tools=` formatting.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator

from src.llm.service import LLMService
from src.llm.tools import TOOL_SPECS, execute_tool, tools_prompt

logger = logging.getLogger(__name__)

_TOOL_NAMES = {spec["name"] for spec in TOOL_SPECS}


def _extract_tool_call(text: str) -> dict | None:
    """Find a {"tool": ..., "args": ...} object in the model output, if any."""
    if not text or "tool" not in text:
        return None
    cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
    candidates = [cleaned]
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("tool") in _TOOL_NAMES:
            return {"tool": obj["tool"], "args": obj.get("args") or {}}
    return None


def _assistant_system(lang: str) -> str:
    language = "English" if lang == "en" else "German"
    return (
        "You are FiscFox, a helpful assistant for German freelancers (Freiberufler). "
        f"Always answer in {language}. Be concise and practical, and you may "
        "reference German tax law (EStG, UStG) where relevant."
    )


class FinancialAssistant:
    """Chat assistant that can call tools to read the user's financial data."""

    def __init__(self, llm_service: LLMService):
        self._llm = llm_service

    async def answer_stream(
        self, message: str, lang: str = "de"
    ) -> AsyncIterator[str]:
        """Answer a chat message, calling a data tool first when needed."""
        call = await self._decide_tool(message)

        if call is None:
            # No data needed — answer directly (general/tax-law/greeting).
            async for token in self._llm.generate_stream(
                prompt=message, system_prompt=_assistant_system(lang)
            ):
                yield token
            return

        # Run the tool against the user's real data, then answer from it.
        try:
            result = await execute_tool(call["tool"], call["args"], self._llm)
        except Exception as e:
            logger.error(f"Tool {call['tool']} failed: {e}")
            result = {"error": str(e)}

        result_json = json.dumps(result, ensure_ascii=False, default=str)
        system = (
            _assistant_system(lang)
            + f"\n\nThe tool `{call['tool']}` returned this data about the user's "
            f"finances (all amounts in EUR):\n{result_json}\n\n"
            "Answer the user's question using ONLY this data. Cite the actual "
            "figures, format money as EUR, and be concise. If the figures are zero, "
            "say there are no recorded entries for that period."
        )
        async for token in self._llm.generate_stream(
            prompt=message, system_prompt=system
        ):
            yield token

    async def _decide_tool(self, message: str) -> dict | None:
        """Ask the model whether a tool is needed; return the parsed call or None."""
        system = (
            "You are the tool router for a German freelancer tax app. These tools "
            "read the user's REAL financial data:\n"
            f"{tools_prompt()}\n\n"
            "If answering the message needs their actual figures, respond with ONLY a "
            'JSON object: {"tool": "<name>", "args": {...}}. '
            "If no tool is needed (general questions, tax-law theory, greetings), "
            "respond with exactly: NONE. Output nothing else."
        )
        try:
            decision = await self._llm.generate(
                prompt=message,
                system_prompt=system,
                max_tokens=120,
                temperature=0.0,
                use_cache=False,
            )
        except Exception as e:
            logger.warning(f"Tool decision failed, answering directly: {e}")
            return None
        return _extract_tool_call(decision.content)


_assistant: FinancialAssistant | None = None


def get_financial_assistant(llm_service: LLMService) -> FinancialAssistant:
    """Get or create the financial assistant singleton."""
    global _assistant
    if _assistant is None or _assistant._llm is not llm_service:
        _assistant = FinancialAssistant(llm_service)
    return _assistant
