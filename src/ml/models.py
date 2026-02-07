"""Pydantic models for ML predictions and reports.

These models define the structure of ML prediction results
used throughout FiscFox's ML-powered features.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Feature 1: Expense Categorization
# =============================================================================


class CategoryPrediction(BaseModel):
    """Result of expense category prediction."""

    predicted_category: str
    confidence: float = Field(ge=0.0, le=1.0)
    alternatives: list[tuple[str, float]] = []
    needs_review: bool = False  # True if confidence < threshold


# =============================================================================
# Feature 2: Invoice Payment Risk
# =============================================================================


class RiskLevel(StrEnum):
    """Payment risk classification levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InvoiceRiskScore(BaseModel):
    """Payment risk score for an invoice."""

    invoice_id: int
    risk_score: float = Field(ge=0.0, le=100.0)
    risk_level: RiskLevel
    predicted_days_to_payment: float
    confidence: float = Field(ge=0.0, le=1.0)
    risk_factors: list[str] = []


class InvoiceRiskSummary(BaseModel):
    """Summary of invoice payment risks."""

    total_pending: int
    total_pending_amount: Decimal
    high_risk_count: int
    high_risk_amount: Decimal
    avg_predicted_days: float
    top_risks: list[InvoiceRiskScore]


# =============================================================================
# Feature 3: Cash Flow Forecasting
# =============================================================================


class CriticalWeek(BaseModel):
    """Week with potential cash flow issues."""

    week_number: int
    week_start: date
    predicted_balance: Decimal
    lower_bound: Decimal
    upper_bound: Decimal
    is_negative: bool
    recommendation: str


class CashFlowForecast(BaseModel):
    """Cash flow forecast result."""

    generated_at: date
    weeks_ahead: int
    current_balance: Decimal
    weekly_predictions: list[dict[str, Any]]  # {week, balance, lower, upper}
    critical_weeks: list[CriticalWeek]
    confidence_level: float
    tax_obligations_included: list[dict[str, Any]]


# =============================================================================
# Feature 4: Mid-Quarter Tax Estimation
# =============================================================================


class TaxLiabilityEstimate(BaseModel):
    """Mid-quarter tax liability estimate."""

    quarter: str  # e.g., "2026-Q2"
    days_elapsed: int
    days_in_quarter: int = 90
    current_revenue: Decimal
    current_expenses: Decimal
    projected_revenue: Decimal
    projected_expenses: Decimal
    estimated_income_tax: Decimal
    estimated_vat_liability: Decimal
    total_estimated_liability: Decimal
    confidence: float = Field(ge=0.0, le=1.0)
    vs_previous_quarter: float | None = None  # % change
    recommendation: str


# =============================================================================
# Feature 5: Audit Risk
# =============================================================================


class AuditRiskLevel(StrEnum):
    """Audit risk classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskFlag(BaseModel):
    """Individual audit risk flag."""

    code: str
    severity: str  # "info", "warning", "critical"
    points: int
    title: str
    description: str
    affected_records: list[int] = []
    law_reference: str = ""
    recommendation: str = ""


class AuditRiskReport(BaseModel):
    """Comprehensive audit risk analysis."""

    year: int
    total_score: float = Field(ge=0.0, le=100.0)
    risk_level: AuditRiskLevel
    rule_flags: list[RiskFlag]
    pattern_flags: list[RiskFlag]
    recommendations: list[str]
    generated_at: date


# =============================================================================
# Feature 6: Vendor Deduplication
# =============================================================================


class VendorMerge(BaseModel):
    """Proposed vendor merge."""

    vendor1: str
    vendor2: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    expense_count_1: int = 0
    expense_count_2: int = 0


class VendorCluster(BaseModel):
    """Cluster of similar vendors."""

    cluster_id: int
    canonical_name: str
    variants: list[str]
    total_expenses: int
    confidence: float = Field(ge=0.0, le=1.0)


class VendorCleanupReport(BaseModel):
    """Vendor cleanup analysis."""

    clusters: list[VendorCluster]
    total_duplicates: int
    potential_savings: int  # Number of records to consolidate


# =============================================================================
# Feature 7: Expense Anomaly Detection
# =============================================================================


class AnomalyType(StrEnum):
    """Types of expense anomalies."""

    DUPLICATE = "duplicate"
    OUTLIER = "outlier"
    UNUSUAL_TIMING = "unusual_timing"
    CATEGORY_MISMATCH = "category_mismatch"
    FREQUENCY = "frequency"
    UNKNOWN = "unknown"


class AnomalyReport(BaseModel):
    """Anomaly detection result for an expense."""

    expense_id: int
    anomaly_score: float = Field(ge=0.0, le=1.0)
    anomaly_type: AnomalyType
    explanation: str
    similar_expense_id: int | None = None  # For duplicates
    expected_value: float | None = None  # For outliers
    recommendation: str


class AnomalySummary(BaseModel):
    """Summary of detected anomalies."""

    total_checked: int
    anomalies_found: int
    by_type: dict[str, int]
    top_anomalies: list[AnomalyReport]


# =============================================================================
# Feature 8: Client Lifetime Value
# =============================================================================


class ClientSegment(StrEnum):
    """Client value segments."""

    CHAMPION = "champion"
    LOYAL = "loyal"
    POTENTIAL = "potential"
    AT_RISK = "at_risk"
    LOW_VALUE = "low_value"


class ClientValuePrediction(BaseModel):
    """Client lifetime value prediction."""

    client_id: int
    client_name: str
    historical_revenue: Decimal
    predicted_revenue_12mo: Decimal
    predicted_lifetime_value: Decimal
    churn_probability: float = Field(ge=0.0, le=1.0)
    segment: ClientSegment
    confidence: float = Field(ge=0.0, le=1.0)
    risk_factors: list[str] = []
    recommendations: list[str] = []


class ClientPortfolioSummary(BaseModel):
    """Summary of client portfolio value."""

    total_clients: int
    total_lifetime_value: Decimal
    by_segment: dict[str, int]
    at_risk_value: Decimal
    top_clients: list[ClientValuePrediction]


# =============================================================================
# Feature 9: Invoice Timing
# =============================================================================


class TimingSuggestion(BaseModel):
    """Invoice timing recommendation."""

    recommended_date: date
    expected_days_to_payment: float
    worst_date: date
    worst_days_to_payment: float
    potential_days_saved: float
    explanation: str
    client_patterns: list[str]


# =============================================================================
# Feature 10: Tax Deduction Opportunities
# =============================================================================


class DeductionOpportunity(BaseModel):
    """Potential tax deduction opportunity."""

    category: str
    title: str
    description: str
    potential_deduction: Decimal
    potential_tax_savings: Decimal
    action: str
    law_reference: str
    priority: int = Field(ge=1, le=10)


class DeductionOpportunityReport(BaseModel):
    """Tax deduction opportunity analysis."""

    year: int
    total_potential_savings: Decimal
    opportunities: list[DeductionOpportunity]
    rules_checked: int
    patterns_analyzed: int
    generated_at: date


# =============================================================================
# ML System Status
# =============================================================================


class ModelStatus(BaseModel):
    """Status of an ML model."""

    model_name: str
    is_trained: bool
    sample_count: int = 0
    trained_at: str | None = None
    accuracy: float | None = None


class MLSystemStatus(BaseModel):
    """Overall ML system status."""

    tabpfn_available: bool
    sklearn_version: str
    models: list[ModelStatus]
    total_predictions_today: int = 0
