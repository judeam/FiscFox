"""Tests for the LLM function-calling toolset and tool-call parsing."""
from __future__ import annotations

from src.llm.agents.assistant import _extract_tool_call
from src.llm.tools import TOOL_SPECS, tools_prompt


class TestToolCallParser:
    """The parser must robustly find tool calls in varied model output."""

    def test_plain_json(self) -> None:
        out = _extract_tool_call('{"tool": "get_tax_summary", "args": {"year": 2025}}')
        assert out == {"tool": "get_tax_summary", "args": {"year": 2025}}

    def test_code_fenced(self) -> None:
        out = _extract_tool_call('```json\n{"tool":"get_financial_overview","args":{}}\n```')
        assert out == {"tool": "get_financial_overview", "args": {}}

    def test_prose_wrapped(self) -> None:
        out = _extract_tool_call('Sure! {"tool": "query_database", "args": {"question": "x"}}')
        assert out == {"tool": "query_database", "args": {"question": "x"}}

    def test_none_keyword(self) -> None:
        assert _extract_tool_call("NONE") is None

    def test_plain_answer(self) -> None:
        assert _extract_tool_call("Just a normal answer.") is None

    def test_unknown_tool_rejected(self) -> None:
        assert _extract_tool_call('{"tool": "rm_rf", "args": {}}') is None

    def test_missing_args_defaults_empty(self) -> None:
        out = _extract_tool_call('{"tool": "get_tax_summary"}')
        assert out == {"tool": "get_tax_summary", "args": {}}


class TestToolRegistry:
    """Tool specs must be well-formed and rendered into the decision prompt."""

    def test_specs_have_required_fields(self) -> None:
        for spec in TOOL_SPECS:
            assert spec["name"] and spec["description"]
            assert isinstance(spec["args"], dict)

    def test_expected_tools_present(self) -> None:
        names = {s["name"] for s in TOOL_SPECS}
        assert {"get_tax_summary", "get_financial_overview", "query_database"} <= names

    def test_prompt_lists_every_tool(self) -> None:
        prompt = tools_prompt()
        for spec in TOOL_SPECS:
            assert spec["name"] in prompt
