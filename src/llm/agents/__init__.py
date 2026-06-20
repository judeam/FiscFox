"""LLM Agents for FiscFox.

Specialized agents for different task types:
- TaxRAGAgent: German tax law Q&A with RAG
- Text2SQLAgent: Natural language to SQL queries
"""

from src.llm.agents.assistant import FinancialAssistant, get_financial_assistant
from src.llm.agents.tax_rag import TaxRAGAgent, get_tax_rag_agent
from src.llm.agents.text2sql import Text2SQLAgent, get_text2sql_agent

__all__ = [
    "FinancialAssistant",
    "TaxRAGAgent",
    "Text2SQLAgent",
    "get_financial_assistant",
    "get_tax_rag_agent",
    "get_text2sql_agent",
]
