"""Text-to-SQL Agent for FiscFox.

Converts natural language queries to SQL for financial data analysis.
Includes SQL validation, sandboxing, and result formatting.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import aiosqlite
from pydantic import BaseModel, Field

from src.llm.exceptions import SQLExecutionError, SQLValidationError
from src.llm.router import ExtractedEntities

if TYPE_CHECKING:
    from src.llm.service import LLMService

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class SQLQuery(BaseModel):
    """Generated SQL query with explanation."""

    sql: str = Field(..., description="Generated SQL query")
    explanation: str = Field(default="", description="Human-readable explanation")
    tables_used: list[str] = Field(default_factory=list, description="Tables referenced")
    is_aggregate: bool = Field(default=False, description="Whether query aggregates data")


class SQLResult(BaseModel):
    """SQL query execution result."""

    query: SQLQuery
    columns: list[str] = Field(default_factory=list, description="Column names")
    rows: list[dict[str, Any]] = Field(default_factory=list, description="Result rows")
    row_count: int = Field(default=0, description="Number of rows returned")
    execution_time_ms: float = Field(default=0.0, description="Query execution time")

    # Formatting
    formatted_answer: str = Field(default="", description="Natural language answer")
    chart_data: dict[str, Any] | None = Field(default=None, description="Data for visualization")


@dataclass
class Text2SQLConfig:
    """Configuration for Text-to-SQL Agent."""

    # Generation settings
    max_tokens: int = 500
    temperature: float = 0.0  # Deterministic for SQL
    max_retries: int = 2

    # Execution settings
    max_rows: int = 100
    timeout_seconds: float = 10.0
    read_only: bool = True

    # Formatting
    format_currency: bool = True
    include_chart_data: bool = False


# =============================================================================
# Schema Definitions
# =============================================================================

# FiscFox database schema for SQL generation
SCHEMA_DESCRIPTION = """
DATABASE SCHEMA (FiscFox - German Freelance Tax Management):

-- Clients table
CREATE TABLE clients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- Client name
    email TEXT,                   -- Contact email
    address TEXT,                 -- Address
    tax_id TEXT,                  -- German tax ID (Steuernummer)
    vat_id TEXT,                  -- EU VAT ID (USt-IdNr.)
    is_eu BOOLEAN DEFAULT 0,      -- EU client flag
    created_at TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL  -- NULL = active, set = soft-deleted
);

-- Invoices table
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    client TEXT NOT NULL,         -- Denormalized client name
    invoice_number TEXT NOT NULL, -- e.g., "2025-001"
    date DATE NOT NULL,           -- Rechnungsdatum (invoice date)
    due_date DATE,                -- Fälligkeitsdatum
    amount TEXT NOT NULL,         -- Gross amount (Brutto)
    amount_net TEXT NOT NULL,     -- Net amount (Netto)
    vat_amount TEXT NOT NULL,     -- VAT amount
    vat_rate TEXT NOT NULL,       -- VAT rate as decimal ('0.19', '0.07', '0.00')
    description TEXT NOT NULL,    -- Invoice description/items
    status TEXT DEFAULT 'pending', -- pending, paid, overdue
    paid_date DATE,               -- When payment received
    is_reverse_charge BOOLEAN DEFAULT 0,
    created_at TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL,  -- NULL = active, set = soft-deleted
    is_storno BOOLEAN DEFAULT 0   -- Reversal flag
);

-- Expenses table
CREATE TABLE expenses (
    id INTEGER PRIMARY KEY,
    date DATE NOT NULL,           -- Belegdatum (expense date)
    vendor TEXT NOT NULL,         -- Vendor/supplier name
    description TEXT NOT NULL,    -- Expense description
    amount_gross TEXT NOT NULL,   -- Gross amount (Brutto)
    amount_net TEXT NOT NULL,     -- Net amount (Netto)
    vat_amount TEXT NOT NULL,     -- VAT amount
    vat_rate TEXT NOT NULL,       -- VAT rate as decimal
    category TEXT NOT NULL,       -- buero, software, hardware, reise, bewirtung, etc.
    created_at TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL,  -- NULL = active, set = soft-deleted
    is_storno BOOLEAN DEFAULT 0
);

-- Assets for depreciation (AfA)
CREATE TABLE assets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- Asset description
    purchase_date DATE NOT NULL,
    purchase_price TEXT NOT NULL, -- Purchase price
    useful_life_years INTEGER,    -- Nutzungsdauer
    depreciation_method TEXT,     -- gwg, pool, linear, degressive, digital
    category TEXT,                -- Asset category
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP
);

-- Depreciation records
CREATE TABLE depreciation_records (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id),
    year INTEGER NOT NULL,
    amount TEXT NOT NULL,         -- Annual depreciation
    cumulative TEXT NOT NULL,     -- Cumulative depreciation
    book_value TEXT NOT NULL,     -- Remaining book value
    created_at TIMESTAMP
);

-- Travel expenses (Reisekosten)
CREATE TABLE travel_expenses (
    id INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    travel_date DATE NOT NULL,
    destination TEXT,
    purpose TEXT,                 -- Business purpose
    km_driven REAL,               -- Kilometers driven
    km_rate TEXT DEFAULT '0.30',  -- EUR per km
    per_diem_days REAL,           -- Days for per diem
    per_diem_rate TEXT,           -- Per diem rate (14/28 EUR)
    accommodation_cost TEXT,
    other_costs TEXT,
    total_amount TEXT NOT NULL,
    created_at TIMESTAMP
);

IMPORTANT NOTES:
- All monetary values are stored as TEXT (Decimal precision)
- Use CAST(column AS REAL) for calculations
- Dates are in ISO format (YYYY-MM-DD)
- deleted_at IS NOT NULL means soft-deleted, always filter with: deleted_at IS NULL
- is_storno=1 means reversal entry, filter with: is_storno = 0
- Invoice status values: 'pending', 'paid', 'overdue'
- VAT rates: '0.19' (standard), '0.07' (reduced), '0.00' (exempt/reverse-charge)
"""

# Few-shot examples for SQL generation
FEW_SHOT_EXAMPLES = """
EXAMPLES:

User: "Liste alle Kunden"
SQL:
SELECT
    id,
    name,
    email
FROM clients
WHERE deleted_at IS NULL;

User: "Wie viele Rechnungen sind offen?"
SQL:
SELECT COUNT(*) as anzahl_offen
FROM invoices
WHERE deleted_at IS NULL
  AND status IN ('pending', 'overdue');

User: "Welche Rechnungen sind überfällig?"
SQL:
SELECT
    id,
    invoice_number,
    client as kunde,
    date as rechnungsdatum,
    due_date,
    amount as betrag
FROM invoices
WHERE deleted_at IS NULL
  AND status = 'overdue'
ORDER BY due_date ASC;

User: "Which invoices are overdue?"
SQL:
SELECT
    id,
    invoice_number,
    client as client_name,
    date as invoice_date,
    due_date,
    amount
FROM invoices
WHERE deleted_at IS NULL
  AND status = 'overdue'
ORDER BY due_date ASC;

User: "Zeige Ausgaben"
SQL:
SELECT
    id,
    description,
    vendor,
    date as datum,
    category,
    amount_gross as betrag
FROM expenses
WHERE date >= date('now', 'start of year')
  AND deleted_at IS NULL
ORDER BY date DESC
LIMIT 100;

User: "Show all expenses"
SQL:
SELECT
    id,
    description,
    vendor,
    date,
    category,
    amount_gross as amount
FROM expenses
WHERE date >= date('now', 'start of year')
  AND deleted_at IS NULL
ORDER BY date DESC
LIMIT 100;

User: "Wie viel Umsatz habe ich in Q1 2025 gemacht?"
SQL:
SELECT
    SUM(CAST(amount_net AS REAL)) as umsatz_netto,
    SUM(CAST(amount AS REAL)) as umsatz_brutto
FROM invoices
WHERE date >= '2025-01-01'
  AND date <= '2025-03-31'
  AND deleted_at IS NULL
  AND is_storno = 0
  AND status IN ('pending', 'paid');

User: "Zeige alle offenen Rechnungen"
SQL:
SELECT
    id,
    invoice_number,
    client,
    date as rechnungsdatum,
    due_date,
    amount,
    status
FROM invoices
WHERE deleted_at IS NULL
  AND status IN ('pending', 'overdue')
ORDER BY due_date ASC;

User: "Wie viel Vorsteuer kann ich für Software geltend machen?"
SQL:
SELECT
    SUM(CAST(vat_amount AS REAL)) as vorsteuer,
    COUNT(*) as anzahl_belege
FROM expenses
WHERE category = 'software'
  AND deleted_at IS NULL
  AND is_storno = 0;

User: "Gewinn nach Monaten in 2025"
SQL:
WITH monthly_revenue AS (
    SELECT
        strftime('%Y-%m', date) as monat,
        SUM(CAST(amount_net AS REAL)) as einnahmen
    FROM invoices
    WHERE date >= '2025-01-01'
      AND deleted_at IS NULL AND is_storno = 0
      AND status IN ('pending', 'paid')
    GROUP BY strftime('%Y-%m', date)
),
monthly_expenses AS (
    SELECT
        strftime('%Y-%m', date) as monat,
        SUM(CAST(amount_net AS REAL)) as ausgaben
    FROM expenses
    WHERE date >= '2025-01-01'
      AND deleted_at IS NULL AND is_storno = 0
    GROUP BY strftime('%Y-%m', date)
)
SELECT
    COALESCE(r.monat, e.monat) as monat,
    COALESCE(r.einnahmen, 0) as einnahmen,
    COALESCE(e.ausgaben, 0) as ausgaben,
    COALESCE(r.einnahmen, 0) - COALESCE(e.ausgaben, 0) as gewinn
FROM monthly_revenue r
FULL OUTER JOIN monthly_expenses e ON r.monat = e.monat
ORDER BY monat;
"""


SYSTEM_PROMPT = """Du bist ein SQL-Experte für eine deutsche Buchhaltungssoftware (FiscFox).
Generiere ausschließlich SELECT-Abfragen basierend auf dem folgenden Schema.

{schema}

{examples}

WICHTIG - IMMER SQL GENERIEREN:
- Generiere IMMER ein SELECT-Statement, stelle NIEMALS Fragen
- Bei mehrdeutigen Anfragen treffe vernünftige Annahmen:
  * Kein Zeitraum angegeben → Aktuelles Jahr
  * Keine Kategorie angegeben → Alle Kategorien
  * Kein Status angegeben → Nur aktive Einträge (deleted_at IS NULL)
- Frage NIEMALS nach mehr Details oder Klärung

REGELN:
1. Generiere NUR SELECT-Statements - keine INSERT, UPDATE, DELETE, DROP
2. Beachte deleted_at IS NULL und is_storno = 0 Filter
3. Verwende CAST(column AS REAL) für Berechnungen mit Geldbeträgen
4. Formatiere Datumsfilter als 'YYYY-MM-DD'
5. Verwende deutsche Spaltennamen in der Ausgabe (AS alias)
6. Begrenze Ergebnisse auf maximal 100 Zeilen
7. Inkludiere IMMER die id-Spalte als erste Spalte (für Verlinkung im UI)

Antworte NUR mit dem SQL-Statement, keine Erklärungen."""


# =============================================================================
# SQL Validator
# =============================================================================


class SQLValidator:
    """Validates and sanitizes generated SQL."""

    # Forbidden keywords
    FORBIDDEN = {
        "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
        "TRUNCATE", "REPLACE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
        "ATTACH", "DETACH", "VACUUM", "PRAGMA",
    }

    # Allowed tables
    ALLOWED_TABLES = {
        "clients", "invoices", "expenses", "assets",
        "depreciation_records", "travel_expenses", "gift_expenses",
        "home_office_days", "business_meals", "settings",
    }

    @classmethod
    def validate(cls, sql: str) -> tuple[bool, str]:
        """Validate SQL query.

        Args:
            sql: SQL query string

        Returns:
            Tuple of (is_valid, error_message)
        """
        sql_upper = sql.upper()

        # Check for forbidden keywords
        for keyword in cls.FORBIDDEN:
            if re.search(rf"\b{keyword}\b", sql_upper):
                return False, f"Forbidden keyword: {keyword}"

        # Must be a SELECT statement
        if not sql_upper.strip().startswith("SELECT"):
            # Allow WITH (CTE) followed by SELECT
            if not re.match(r"\s*WITH\s+", sql_upper):
                return False, "Only SELECT queries are allowed"

        # Check for table names (basic check)
        # Extract table names from FROM and JOIN clauses
        tables = re.findall(r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)", sql_upper)
        for match in tables:
            table = (match[0] or match[1]).lower()
            if table not in cls.ALLOWED_TABLES:
                return False, f"Table not allowed: {table}"

        # Check for dangerous patterns
        if re.search(r";\s*\w", sql):  # Multiple statements
            return False, "Multiple statements not allowed"

        if "--" in sql or "/*" in sql:  # SQL comments
            return False, "SQL comments not allowed"

        return True, ""

    @classmethod
    def extract_tables(cls, sql: str) -> list[str]:
        """Extract table names from SQL.

        Args:
            sql: SQL query

        Returns:
            List of table names
        """
        tables = set()
        sql_upper = sql.upper()

        for match in re.finditer(r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)", sql_upper):
            table = (match.group(1) or match.group(2)).lower()
            if table in cls.ALLOWED_TABLES:
                tables.add(table)

        return list(tables)


# =============================================================================
# Text-to-SQL Agent
# =============================================================================


class Text2SQLAgent:
    """Agent for converting natural language to SQL.

    Features:
    - Schema-aware SQL generation
    - Query validation and sandboxing
    - Result formatting with German localization
    - Natural language answer generation
    """

    def __init__(
        self,
        llm_service: LLMService,
        db_path: str,
    ):
        """Initialize Text-to-SQL Agent.

        Args:
            llm_service: LLM service for generation
            db_path: Path to SQLite database
        """
        self._llm = llm_service
        self._db_path = db_path
        self._validator = SQLValidator()

    async def query(
        self,
        question: str,
        config: Text2SQLConfig | None = None,
        entities: ExtractedEntities | None = None,
    ) -> SQLResult:
        """Convert question to SQL and execute.

        Args:
            question: Natural language question
            config: Agent configuration
            entities: Pre-extracted entities

        Returns:
            SQLResult with query and results
        """
        config = config or Text2SQLConfig()
        start_time = datetime.now()

        # Generate SQL
        sql_query = await self._generate_sql(question, config, entities)

        # Validate SQL
        is_valid, error = self._validator.validate(sql_query.sql)
        if not is_valid:
            raise SQLValidationError(sql_query.sql, error)

        # Execute query
        try:
            columns, rows = await self._execute_sql(
                sql_query.sql,
                config.max_rows,
                config.timeout_seconds,
                config.read_only,
            )
        except Exception as e:
            raise SQLExecutionError(sql_query.sql, str(e)) from e

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        # Format results
        formatted_rows = self._format_rows(rows, config.format_currency)

        # Generate natural language answer
        formatted_answer = await self._format_answer(
            question, sql_query, columns, formatted_rows
        )

        # Prepare chart data if requested
        chart_data = None
        if config.include_chart_data and rows:
            chart_data = self._prepare_chart_data(columns, rows)

        return SQLResult(
            query=sql_query,
            columns=columns,
            rows=formatted_rows,
            row_count=len(rows),
            execution_time_ms=execution_time,
            formatted_answer=formatted_answer,
            chart_data=chart_data,
        )

    async def _generate_sql(
        self,
        question: str,
        config: Text2SQLConfig,
        entities: ExtractedEntities | None,
    ) -> SQLQuery:
        """Generate SQL from question.

        Args:
            question: Natural language question
            config: Configuration
            entities: Extracted entities

        Returns:
            SQLQuery with generated SQL
        """
        # Build enhanced prompt with entities
        enhanced_question = question
        if entities:
            hints = []
            if entities.years:
                hints.append(f"Jahre: {', '.join(map(str, entities.years))}")
            if entities.quarters:
                hints.append(f"Quartale: {', '.join(f'Q{q}' for q in entities.quarters)}")
            if entities.categories:
                hints.append(f"Kategorien: {', '.join(entities.categories)}")

            if hints:
                enhanced_question = f"{question}\n\nHinweise: {'; '.join(hints)}"

        system_prompt = SYSTEM_PROMPT.format(
            schema=SCHEMA_DESCRIPTION,
            examples=FEW_SHOT_EXAMPLES,
        )

        last_error: SQLValidationError | None = None

        # Retry loop for clarification questions
        for attempt in range(config.max_retries + 1):
            try:
                # On retry, add stricter instructions
                prompt_to_use = enhanced_question
                if attempt > 0:
                    current_year = datetime.now().year
                    prompt_to_use = f"""{enhanced_question}

WICHTIG: Generiere das SQL sofort. Keine Fragen stellen.
Verwende diese Annahmen falls nötig:
- Zeitraum: Aktuelles Jahr ({current_year})
- Status: Alle aktiven Einträge (deleted_at IS NULL)
- Kategorie: Alle Kategorien (kein Filter)"""

                # Generate SQL
                response = await self._llm.generate(
                    prompt=prompt_to_use,
                    system_prompt=system_prompt,
                    max_tokens=config.max_tokens,
                    temperature=0.0 if attempt > 0 else config.temperature,  # More deterministic on retry
                    use_cache=attempt == 0,  # Don't cache retries
                )

                # Extract SQL from response (may raise SQLValidationError)
                sql = self._extract_sql(response.content)

                # Determine if aggregate query
                is_aggregate = any(
                    kw in sql.upper()
                    for kw in ["SUM(", "COUNT(", "AVG(", "MIN(", "MAX(", "GROUP BY"]
                )

                return SQLQuery(
                    sql=sql,
                    explanation=f"SQL generiert für: {question}",
                    tables_used=self._validator.extract_tables(sql),
                    is_aggregate=is_aggregate,
                )

            except SQLValidationError as e:
                last_error = e
                # Only retry if it was a clarification issue
                if "clarification" not in str(e).lower():
                    raise
                logger.warning(f"SQL generation attempt {attempt + 1} failed: LLM asked for clarification")
                continue

        # All retries exhausted
        if last_error:
            raise last_error
        raise SQLValidationError("", "SQL generation failed after retries")

    def _extract_sql(self, response: str) -> str:
        """Extract SQL from LLM response.

        Args:
            response: LLM response text

        Returns:
            Extracted SQL query

        Raises:
            SQLValidationError: If LLM returned a clarification question
        """
        # Check for clarification questions FIRST
        clarification_markers = [
            "?",  # Question marks
            "könntest", "kannst du", "bitte", "mehr details", "genauer",
            "could you", "can you", "please provide", "more details",
            "clarify", "specify", "what kind", "which specific",
        ]

        response_lower = response.lower()
        has_clarification = any(marker in response_lower for marker in clarification_markers)
        has_sql = any(kw in response.upper() for kw in ["SELECT", "WITH"])

        if has_clarification and not has_sql:
            raise SQLValidationError(
                sql=response[:200] + ("..." if len(response) > 200 else ""),
                reason="LLM returned clarification question instead of SQL. "
                       "Query will be retried with explicit defaults.",
            )

        # Remove markdown code blocks
        if "```sql" in response:
            start = response.index("```sql") + 6
            end = response.index("```", start)
            return response[start:end].strip()
        elif "```" in response:
            start = response.index("```") + 3
            end = response.index("```", start)
            return response[start:end].strip()

        # Find SELECT statement
        match = re.search(r"(WITH\s+.+?)?SELECT\s+.+", response, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(0).strip().rstrip(";") + ";"

        return response.strip()

    async def _execute_sql(
        self,
        sql: str,
        max_rows: int,
        timeout: float,
        read_only: bool,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Execute SQL query safely.

        Args:
            sql: SQL query
            max_rows: Maximum rows to return
            timeout: Timeout in seconds
            read_only: Enforce read-only mode

        Returns:
            Tuple of (column_names, rows)
        """
        # Add LIMIT if not present
        sql_upper = sql.upper()
        if "LIMIT" not in sql_upper:
            sql = sql.rstrip(";") + f" LIMIT {max_rows};"

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # Enable read-only mode
            if read_only:
                await db.execute("PRAGMA query_only = ON")

            # Execute query
            cursor = await db.execute(sql)
            rows_raw = await cursor.fetchall()

            # Get column names
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            # Convert to dicts
            rows = [dict(row) for row in rows_raw]

        return columns, rows

    def _format_rows(
        self,
        rows: list[dict[str, Any]],
        format_currency: bool,
    ) -> list[dict[str, Any]]:
        """Format row values for display.

        Args:
            rows: Raw query results
            format_currency: Whether to format currency values

        Returns:
            Formatted rows
        """
        formatted = []

        for row in rows:
            formatted_row = {}
            for key, value in row.items():
                if value is None:
                    formatted_row[key] = "-"
                elif isinstance(value, (int, float)) and format_currency:
                    # Check if this looks like a currency column
                    if any(
                        kw in key.lower()
                        for kw in ["amount", "betrag", "umsatz", "summe", "gewinn", "kosten", "preis"]
                    ):
                        formatted_row[key] = f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
                    else:
                        formatted_row[key] = value
                else:
                    formatted_row[key] = value
            formatted.append(formatted_row)

        return formatted

    async def _format_answer(
        self,
        question: str,
        query: SQLQuery,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> str:
        """Generate natural language answer from results.

        Args:
            question: Original question
            query: Generated SQL query
            columns: Column names
            rows: Query results

        Returns:
            Natural language answer with formatted data
        """
        if not rows:
            return "Keine Ergebnisse gefunden."

        # For aggregate queries, format as summary
        if query.is_aggregate and len(rows) == 1:
            row = rows[0]
            parts = []
            for col, val in row.items():
                if val != "-" and val is not None:
                    parts.append(f"**{col}**: {val}")
            return "\n".join(parts)

        # For list queries, format as markdown table
        result_parts = []

        # Header line
        if len(rows) == 1:
            result_parts.append("**1 Ergebnis gefunden:**\n")
        else:
            result_parts.append(f"**{len(rows)} Ergebnisse gefunden:**\n")

        # Build markdown table
        if columns:
            # Table header
            result_parts.append("| " + " | ".join(columns) + " |")
            result_parts.append("| " + " | ".join(["---"] * len(columns)) + " |")

            # Table rows (limit to 20 for readability)
            display_rows = rows[:20]
            for row in display_rows:
                values = [str(row.get(col, "-")) for col in columns]
                result_parts.append("| " + " | ".join(values) + " |")

            if len(rows) > 20:
                result_parts.append(f"\n*... und {len(rows) - 20} weitere Einträge*")

        return "\n".join(result_parts)

    def _prepare_chart_data(
        self,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Prepare data for chart visualization.

        Args:
            columns: Column names
            rows: Query results

        Returns:
            Chart data dict or None
        """
        if not rows or len(columns) < 2:
            return None

        # Try to identify label and value columns
        label_col = columns[0]
        value_cols = columns[1:]

        labels = [str(row.get(label_col, "")) for row in rows]

        datasets = []
        for col in value_cols:
            values = []
            for row in rows:
                val = row.get(col)
                if isinstance(val, str):
                    # Try to parse currency format
                    val = val.replace(" €", "").replace(".", "").replace(",", ".")
                    try:
                        val = float(val)
                    except ValueError:
                        val = 0
                values.append(val if isinstance(val, (int, float)) else 0)
            datasets.append({"label": col, "data": values})

        return {
            "type": "bar" if len(rows) <= 12 else "line",
            "labels": labels,
            "datasets": datasets,
        }

    def get_status(self) -> dict[str, Any]:
        """Get agent status.

        Returns:
            Status dict
        """
        return {
            "ready": self._llm.is_ready,
            "db_path": self._db_path,
            "allowed_tables": list(SQLValidator.ALLOWED_TABLES),
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_text2sql_agent: Text2SQLAgent | None = None


def get_text2sql_agent(
    llm_service: LLMService | None = None,
    db_path: str | None = None,
) -> Text2SQLAgent:
    """Get or create the Text-to-SQL Agent singleton.

    Args:
        llm_service: LLM service (required on first call)
        db_path: Database path (required on first call)

    Returns:
        Text2SQLAgent singleton instance
    """
    global _text2sql_agent
    if _text2sql_agent is None:
        if llm_service is None or db_path is None:
            raise ValueError("llm_service and db_path required for first initialization")
        _text2sql_agent = Text2SQLAgent(llm_service, db_path)
    return _text2sql_agent
