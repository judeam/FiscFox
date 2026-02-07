"""Pydantic schemas for LLM structured output.

All monetary values use string representation with regex validation
to ensure Decimal precision is preserved.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Common Types and Patterns
# =============================================================================

# Pattern for German decimal notation: digits with exactly 2 decimal places
MONEY_PATTERN = r"^\d+\.\d{2}$"


class ConfidenceLevel(StrEnum):
    """Confidence levels for LLM predictions."""

    HIGH = "high"  # > 0.85
    MEDIUM = "medium"  # 0.6 - 0.85
    LOW = "low"  # < 0.6


# =============================================================================
# Expense Categorization
# =============================================================================


class ExpenseCategory(StrEnum):
    """German expense categories for tax purposes.

    Based on EÜR (Einnahmen-Überschuss-Rechnung) structure.
    """

    BUERO = "buero"  # Office supplies, stationery
    SOFTWARE = "software"  # Software subscriptions, licenses
    HARDWARE = "hardware"  # Computer equipment (may require AfA)
    REISE = "reise"  # Travel expenses
    BEWIRTUNG = "bewirtung"  # Business meals (70% deductible)
    TELEFON = "telefon"  # Phone, internet, communication
    VERSICHERUNG = "versicherung"  # Business insurance
    FORTBILDUNG = "fortbildung"  # Training, education
    FACHLITERATUR = "fachliteratur"  # Professional books, journals
    BERATUNG = "beratung"  # Legal, tax, consulting
    MIETE = "miete"  # Rent, premises costs
    WERBUNG = "werbung"  # Marketing, advertising
    KFZKOSTEN = "kfzkosten"  # Vehicle costs
    SONSTIGE = "sonstige"  # Other business expenses
    GESCHENKE = "geschenke"  # Gifts (§ 4 Abs. 5 Nr. 1 EStG, 50€ limit)


class VatRate(StrEnum):
    """German VAT rates.

    § 12 UStG: Standard 19%, reduced 7%
    § 13b UStG: Reverse charge 0% for B2B international
    """

    STANDARD = "0.19"  # 19% standard rate
    REDUCED = "0.07"  # 7% reduced rate (food, books, etc.)
    ZERO = "0.00"  # Exempt or reverse charge


class ExpenseSchema(BaseModel):
    """Schema for LLM expense categorization output.

    All monetary fields use string with pattern to preserve precision.
    """

    amount_gross_str: Annotated[str, Field(pattern=MONEY_PATTERN)]
    category: ExpenseCategory
    vat_rate: VatRate
    vendor_name: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=500)
    is_afa_relevant: bool = Field(
        default=False, description="True if amount > 250€ and is a capital asset"
    )
    confidence: ConfidenceLevel
    reasoning: str = Field(
        max_length=300, description="Brief explanation for categorization"
    )

    @property
    def amount_gross(self) -> Decimal:
        """Convert string amount to Decimal."""
        return Decimal(self.amount_gross_str)

    @property
    def amount_net(self) -> Decimal:
        """Calculate net amount from gross."""
        vat_factor = Decimal("1") + Decimal(self.vat_rate.value)
        return (self.amount_gross / vat_factor).quantize(Decimal("0.01"))

    @property
    def vat_amount(self) -> Decimal:
        """Calculate VAT (Vorsteuer) amount."""
        return (self.amount_gross - self.amount_net).quantize(Decimal("0.01"))


# =============================================================================
# AfA (Depreciation) Suggestions
# =============================================================================


class AfaMethod(StrEnum):
    """Depreciation methods per § 7 EStG.

    GWG: Geringwertige Wirtschaftsgüter (<= 800€), immediate write-off
    Pool: Sammelposten (250.01€ - 1000€), 5-year straight-line
    Linear: Standard straight-line depreciation
    Degressive: Declining balance (30% max per § 7 Abs. 2 EStG 2024)
    Digital: BMF 2021-02-26, 1-year for hardware/software
    """

    IMMEDIATE = "immediate"  # GWG direct deduction
    POOL = "pool"  # Sammelposten 5-year
    LINEAR = "linear"  # Standard AfA
    DEGRESSIVE = "degressive"  # Declining balance
    DIGITAL = "digital"  # Digital assets 1-year


class AfaSuggestion(BaseModel):
    """LLM suggestion for depreciation method.

    Provides tax-optimized recommendation based on asset type and value.
    """

    asset_name: str = Field(min_length=1, max_length=200)
    amount_str: Annotated[str, Field(pattern=MONEY_PATTERN)]
    suggested_method: AfaMethod
    useful_life_years: int = Field(ge=1, le=50)
    tax_reference: str = Field(
        max_length=100,
        description="German tax law reference (e.g., '§ 7 Abs. 2 EStG')",
    )
    annual_depreciation_str: Annotated[str, Field(pattern=MONEY_PATTERN)]
    reasoning: str = Field(max_length=500)
    confidence: ConfidenceLevel

    @property
    def amount(self) -> Decimal:
        """Convert amount string to Decimal."""
        return Decimal(self.amount_str)

    @property
    def annual_depreciation(self) -> Decimal:
        """Convert annual depreciation to Decimal."""
        return Decimal(self.annual_depreciation_str)

    @field_validator("useful_life_years", mode="before")
    @classmethod
    def validate_useful_life(cls, v: int, info) -> int:
        """Validate useful life based on method."""
        # Note: Will be validated in context of method
        return v


# =============================================================================
# Text-to-SQL
# =============================================================================


class SQLQuery(BaseModel):
    """LLM-generated SQL query with validation.

    Only SELECT queries are allowed for safety.
    """

    sql: str = Field(
        min_length=10,
        max_length=2000,
        description="Read-only SQL query (SELECT only)",
    )
    explanation: str = Field(
        max_length=500, description="Human-readable query explanation in German"
    )
    tables_used: list[str] = Field(
        min_length=1, description="List of tables referenced in the query"
    )
    confidence: ConfidenceLevel

    @field_validator("sql")
    @classmethod
    def validate_read_only(cls, v: str) -> str:
        """Ensure query is read-only (no modifications)."""
        upper = v.upper().strip()

        # Block dangerous keywords
        forbidden = [
            "DROP",
            "DELETE",
            "UPDATE",
            "INSERT",
            "ALTER",
            "CREATE",
            "TRUNCATE",
            "REPLACE",
            "GRANT",
            "REVOKE",
            "ATTACH",
            "DETACH",
            "PRAGMA",  # Block most pragmas
            "VACUUM",
            "REINDEX",
        ]

        for keyword in forbidden:
            if keyword in upper.split():
                raise ValueError(f"SQL contains forbidden keyword: {keyword}")

        # Must start with SELECT or WITH (for CTEs)
        if not (upper.startswith("SELECT") or upper.startswith("WITH")):
            raise ValueError("SQL must start with SELECT or WITH clause")

        return v


class SQLResult(BaseModel):
    """Result from SQL query execution."""

    columns: list[str]
    rows: list[dict[str, str | int | float | None]]
    row_count: int
    summary: str = Field(
        max_length=500, description="Natural language summary of results in German"
    )


# =============================================================================
# Tax Law RAG
# =============================================================================


class TaxLawSource(BaseModel):
    """Citation from German tax law knowledge base."""

    source_type: Literal["estg", "ustg", "ao", "bmf", "bfh"]
    section: str = Field(max_length=50, description="e.g., '§ 7 Abs. 2'")
    title: str = Field(max_length=200)
    content_snippet: str = Field(max_length=1000)
    relevance_score: float = Field(ge=0.0, le=1.0)


class TaxAnswer(BaseModel):
    """LLM answer to tax-related question."""

    answer: str = Field(
        min_length=10,
        max_length=2000,
        description="Natural language answer in German",
    )
    sources: list[TaxLawSource] = Field(min_length=0, max_length=5)
    confidence: ConfidenceLevel
    disclaimer: str = Field(
        default="Diese Information ersetzt keine professionelle Steuerberatung.",
        max_length=200,
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Suggested follow-up questions",
    )


# =============================================================================
# Invoice Risk Assessment
# =============================================================================


class InvoiceRisk(StrEnum):
    """Invoice payment risk levels."""

    LOW = "low"  # < 10% default probability
    MEDIUM = "medium"  # 10-30% default probability
    HIGH = "high"  # > 30% default probability


class InvoiceRiskAssessment(BaseModel):
    """Risk assessment for invoice payment."""

    risk_level: InvoiceRisk
    probability_of_delay: float = Field(ge=0.0, le=1.0)
    recommended_actions: list[str] = Field(max_length=5)
    reasoning: str = Field(max_length=500)
    confidence: ConfidenceLevel


# =============================================================================
# Intent Classification
# =============================================================================


class UserIntent(StrEnum):
    """Classified user intent for routing."""

    TAX_LAW = "tax_law"  # Question about German tax law → RAG
    FINANCIAL_QUERY = "financial_query"  # Data query → Text-to-SQL
    AFA_ASSIST = "afa_assist"  # Depreciation help → AfA agent
    EXPENSE_CATEGORIZE = "expense_categorize"  # Categorization → Expense agent
    INVOICE_RISK = "invoice_risk"  # Risk assessment → Risk agent
    ML_INTERPRETATION = "ml_interpretation"  # Explain ML predictions
    GENERAL_CHAT = "general_chat"  # General assistance


class IntentClassification(BaseModel):
    """Classified intent with extracted entities."""

    intent: UserIntent
    entities: dict[str, str] = Field(
        default_factory=dict,
        description="Extracted entities: year, quarter, amount, category, etc.",
    )
    confidence: ConfidenceLevel
    original_query: str


# =============================================================================
# ML Prediction Interpretation
# =============================================================================


class MLPredictionExplanation(BaseModel):
    """Natural language explanation of ML predictions."""

    prediction_type: Literal[
        "expense_category", "invoice_risk", "cash_flow_forecast", "vendor_match"
    ]
    prediction_value: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(
        max_length=1000, description="Natural language explanation in German"
    )
    key_factors: list[str] = Field(
        max_length=5, description="Most important factors for prediction"
    )
    uncertainty_notes: str | None = Field(
        default=None, max_length=300, description="Notes about prediction uncertainty"
    )
