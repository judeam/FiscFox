"""Tool registry for the FiscFox financial assistant (LLM function calling).

Each tool wraps existing, tested computation — the DashboardService (which runs
the German tax calculators) or the text2SQL agent — so the chat answers from the
user's ACTUAL data instead of generic knowledge. Tools return JSON-serializable
dicts that get fed back to the model to compose the final answer.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


# Tool specifications advertised to the model in the decision prompt.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_tax_summary",
        "description": (
            "Compute the user's income tax (Einkommensteuer), solidarity surcharge "
            "(Soli), VAT liability (Umsatzsteuer-Zahllast), taxable income and the "
            "suggested quarterly prepayment for a tax year, from their recorded "
            "invoices and expenses. Use for ANY question about how much tax is "
            "owed/due/payable (Einkommensteuer, USt, Steuer, Zahllast, Nachzahlung)."
        ),
        "args": {"year": "integer tax year e.g. 2025 (optional, defaults to current)"},
    },
    {
        "name": "get_financial_overview",
        "description": (
            "Get total revenue, total expenses, VAT collected and effective tax rate "
            "for a tax year. Use for questions about income, turnover (Umsatz), "
            "expenses (Ausgaben) or profit (Gewinn)."
        ),
        "args": {"year": "integer tax year (optional, defaults to current)"},
    },
    {
        "name": "query_database",
        "description": (
            "Run a natural-language query against the user's financial database to "
            "list or look up specific records (open/overdue invoices, expenses by "
            "category, clients). Use when the answer is a list or specific lookup "
            "rather than a tax computation."
        ),
        "args": {"question": "the user's data question"},
    },
]

_TOOL_NAMES = {spec["name"] for spec in TOOL_SPECS}


def tools_prompt() -> str:
    """Render the tool list for the model's decision prompt."""
    lines = []
    for spec in TOOL_SPECS:
        args = ", ".join(f"{k} — {v}" for k, v in spec["args"].items()) or "none"
        lines.append(f'- {spec["name"]}: {spec["description"]} Args: {args}')
    return "\n".join(lines)


def _default_year() -> int:
    """Current tax year from settings, falling back to the calendar year."""
    try:
        from src.web.routes.settings import get_tax_year

        return get_tax_year()
    except Exception:
        return date.today().year


def _coerce_year(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return _default_year()


async def execute_tool(
    name: str, args: dict[str, Any] | None, llm_service: Any
) -> dict[str, Any]:
    """Execute a tool by name and return a JSON-serializable result dict.

    Imports are lazy to avoid an llm -> web/db import cycle at module load.
    """
    args = args or {}

    if name == "get_tax_summary":
        from src.web.services.dashboard import DashboardService

        year = _coerce_year(args.get("year"))
        estimate = await DashboardService().get_tax_estimate(year)
        data = estimate.model_dump(mode="json")
        data["year"] = year
        return data

    if name == "get_financial_overview":
        from src.web.services.dashboard import DashboardService

        year = _coerce_year(args.get("year"))
        stats = await DashboardService().get_dashboard_stats(year)
        data = stats.model_dump(mode="json")
        data["year"] = year
        return data

    if name == "query_database":
        from src.db.repository import DB_PATH
        from src.llm.agents import get_text2sql_agent

        question = str(args.get("question") or "").strip()
        if not question:
            return {"error": "no question provided"}
        agent = get_text2sql_agent(llm_service, str(DB_PATH))
        result = await agent.query(question)
        return {
            "answer": result.formatted_answer,
            "rows": result.rows[:20],
            "row_count": result.row_count,
        }

    return {"error": f"Unknown tool: {name}"}
