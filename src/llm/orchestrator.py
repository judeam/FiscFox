"""ML Orchestrator for FiscFox LLM Integration.

Interprets TabPFN predictions and Prophet forecasts using LLM
for human-readable explanations and actionable insights.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.llm.service import LLMService

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class MLExplanation(BaseModel):
    """LLM-generated explanation of ML prediction."""

    summary: str = Field(..., description="One-sentence summary")
    explanation: str = Field(default="", description="Detailed explanation")
    confidence_level: str = Field(default="medium", description="high/medium/low")
    key_factors: list[str] = Field(default_factory=list, description="Key contributing factors")
    recommendations: list[str] = Field(default_factory=list, description="Actionable recommendations")
    caveats: list[str] = Field(default_factory=list, description="Important caveats")


class CategoryPredictionExplanation(BaseModel):
    """Explanation for expense categorization prediction."""

    predicted_category: str
    confidence: float
    explanation: MLExplanation
    alternative_categories: list[tuple[str, float]] = Field(default_factory=list)


class ForecastExplanation(BaseModel):
    """Explanation for time series forecast."""

    metric_name: str
    forecast_period: str
    explanation: MLExplanation
    trend_direction: str = Field(default="stable", description="up/down/stable")
    seasonality_note: str = Field(default="", description="Seasonal patterns detected")


class RiskAssessmentExplanation(BaseModel):
    """Explanation for invoice risk assessment."""

    risk_level: str  # low, medium, high
    risk_score: float
    explanation: MLExplanation
    risk_factors: list[str] = Field(default_factory=list)
    mitigation_suggestions: list[str] = Field(default_factory=list)


@dataclass
class OrchestratorConfig:
    """Configuration for ML Orchestrator."""

    # Generation settings
    max_tokens: int = 500
    temperature: float = 0.3

    # Confidence thresholds
    high_confidence_threshold: float = 0.8
    low_confidence_threshold: float = 0.5

    # Include detailed analysis
    include_key_factors: bool = True
    include_recommendations: bool = True


# =============================================================================
# System Prompts
# =============================================================================

CATEGORY_EXPLANATION_PROMPT = """Du bist ein Experte für deutsches Steuerrecht und Buchhaltung.
Erkläre die Kategorisierung einer Betriebsausgabe.

AUSGABE:
- Beschreibung: {description}
- Betrag: {amount} EUR
- Vorhergesagte Kategorie: {predicted_category}
- Konfidenz: {confidence:.0%}

ALTERNATIVE KATEGORIEN:
{alternatives}

KATEGORIE-DEFINITIONEN:
- buero: Bürobedarf, Schreibwaren, Druckerpapier
- software: Softwarelizenzen, SaaS-Abonnements, Apps
- hardware: Computer, Monitore, Drucker, Peripherie
- reise: Geschäftsreisen, Fahrtkosten, Übernachtungen
- bewirtung: Geschäftsessen (70% absetzbar, § 4 Abs. 5 Nr. 2 EStG)
- telefon: Telefon, Internet, Mobilfunk
- fortbildung: Seminare, Kurse, Weiterbildung
- fachliteratur: Fachbücher, Zeitschriften
- beratung: Steuerberater, Rechtsanwalt, Consulting
- geschenke: Kundengeschenke (bis 50 EUR/Person/Jahr)

Erkläre kurz:
1. Warum diese Kategorie passt
2. Steuerliche Relevanz (falls relevant)
3. Falls Konfidenz < 70%: Warum Unsicherheit besteht"""

FORECAST_EXPLANATION_PROMPT = """Du bist ein Finanzanalyst für Freelancer.
Erkläre die folgende Prognose verständlich.

PROGNOSE:
- Metrik: {metric_name}
- Zeitraum: {forecast_period}
- Prognosewert: {forecast_value}
- Untere Grenze: {lower_bound}
- Obere Grenze: {upper_bound}
- Trend: {trend}

HISTORISCHE DATEN (letzte 6 Monate):
{historical_summary}

Erkläre:
1. Was bedeutet diese Prognose konkret?
2. Welche Faktoren beeinflussen den Trend?
3. Konkrete Handlungsempfehlungen"""

RISK_EXPLANATION_PROMPT = """Du bist ein Finanzexperte für Forderungsmanagement.
Erkläre die Risikoeinschätzung für eine Rechnung.

RECHNUNG:
- Kunde: {client_name}
- Betrag: {amount} EUR
- Rechnungsdatum: {invoice_date}
- Fälligkeit: {due_date}
- Risiko-Score: {risk_score:.0%}
- Risiko-Stufe: {risk_level}

RISIKOFAKTOREN:
{risk_factors}

KUNDENHISTORIE:
{client_history}

Erkläre:
1. Warum diese Risikoeinstufung?
2. Welche Faktoren sind besonders relevant?
3. Empfohlene Maßnahmen"""

LOW_CONFIDENCE_CLARIFICATION_PROMPT = """Die ML-Vorhersage hat eine niedrige Konfidenz ({confidence:.0%}).

VORHERSAGE:
{prediction_details}

Formuliere 2-3 Rückfragen an den Nutzer, um die Kategorisierung zu verbessern.
Sei präzise und freundlich."""


# =============================================================================
# Category Mappings
# =============================================================================

CATEGORY_NAMES_DE = {
    "buero": "Bürobedarf",
    "software": "Software & Lizenzen",
    "hardware": "Hardware & Geräte",
    "reise": "Reisekosten",
    "bewirtung": "Bewirtung",
    "telefon": "Telekommunikation",
    "versicherung": "Versicherungen",
    "fortbildung": "Fortbildung",
    "fachliteratur": "Fachliteratur",
    "beratung": "Beratung",
    "miete": "Miete & Räume",
    "werbung": "Werbung & Marketing",
    "kfzkosten": "KFZ-Kosten",
    "geschenke": "Geschenke",
    "sonstige": "Sonstige",
}


# =============================================================================
# ML Orchestrator
# =============================================================================


class MLOrchestrator:
    """Orchestrates ML predictions with LLM explanations.

    Provides human-readable interpretations of:
    - TabPFN expense categorization
    - TabPFN invoice risk assessment
    - Prophet cash flow forecasts
    """

    def __init__(
        self,
        llm_service: LLMService,
        config: OrchestratorConfig | None = None,
    ):
        """Initialize ML Orchestrator.

        Args:
            llm_service: LLM service for explanations
            config: Orchestrator configuration
        """
        self._llm = llm_service
        self._config = config or OrchestratorConfig()

    async def explain_categorization(
        self,
        description: str,
        amount: Decimal | str,
        predicted_category: str,
        confidence: float,
        alternatives: list[tuple[str, float]] | None = None,
    ) -> CategoryPredictionExplanation:
        """Generate explanation for expense categorization.

        Args:
            description: Expense description
            amount: Expense amount
            predicted_category: Predicted category
            confidence: Prediction confidence
            alternatives: Alternative categories with scores

        Returns:
            CategoryPredictionExplanation
        """
        # Format alternatives
        alt_text = ""
        if alternatives:
            alt_lines = [
                f"- {CATEGORY_NAMES_DE.get(cat, cat)}: {score:.0%}"
                for cat, score in alternatives[:3]
            ]
            alt_text = "\n".join(alt_lines)
        else:
            alt_text = "Keine Alternativen berechnet"

        # Build prompt
        prompt = CATEGORY_EXPLANATION_PROMPT.format(
            description=description,
            amount=amount,
            predicted_category=CATEGORY_NAMES_DE.get(predicted_category, predicted_category),
            confidence=confidence,
            alternatives=alt_text,
        )

        # Generate explanation
        response = await self._llm.generate(
            prompt=prompt,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
        )

        # Parse response into structure
        explanation = self._parse_explanation(
            response.content,
            confidence,
        )

        return CategoryPredictionExplanation(
            predicted_category=predicted_category,
            confidence=confidence,
            explanation=explanation,
            alternative_categories=alternatives or [],
        )

    async def explain_forecast(
        self,
        metric_name: str,
        forecast_period: str,
        forecast_value: float,
        lower_bound: float,
        upper_bound: float,
        trend: str,
        historical_data: list[tuple[str, float]] | None = None,
    ) -> ForecastExplanation:
        """Generate explanation for time series forecast.

        Args:
            metric_name: Name of forecast metric
            forecast_period: Period being forecast
            forecast_value: Point forecast
            lower_bound: Lower confidence bound
            upper_bound: Upper confidence bound
            trend: Trend direction (up/down/stable)
            historical_data: Recent historical values

        Returns:
            ForecastExplanation
        """
        # Format historical data
        hist_summary = ""
        if historical_data:
            hist_lines = [
                f"- {date}: {value:,.2f} EUR"
                for date, value in historical_data[-6:]
            ]
            hist_summary = "\n".join(hist_lines)
        else:
            hist_summary = "Keine historischen Daten verfügbar"

        # Build prompt
        prompt = FORECAST_EXPLANATION_PROMPT.format(
            metric_name=metric_name,
            forecast_period=forecast_period,
            forecast_value=f"{forecast_value:,.2f} EUR",
            lower_bound=f"{lower_bound:,.2f} EUR",
            upper_bound=f"{upper_bound:,.2f} EUR",
            trend={"up": "steigend", "down": "fallend", "stable": "stabil"}.get(trend, trend),
            historical_summary=hist_summary,
        )

        # Generate explanation
        response = await self._llm.generate(
            prompt=prompt,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
        )

        # Determine confidence from forecast range
        range_pct = (upper_bound - lower_bound) / forecast_value if forecast_value > 0 else 1.0
        confidence = max(0.3, min(0.95, 1.0 - range_pct))

        explanation = self._parse_explanation(response.content, confidence)

        # Detect seasonality mention
        seasonality_note = ""
        if any(kw in response.content.lower() for kw in ["saisonal", "jahreszeit", "quartal", "monat"]):
            seasonality_note = "Saisonale Muster erkannt"

        return ForecastExplanation(
            metric_name=metric_name,
            forecast_period=forecast_period,
            explanation=explanation,
            trend_direction=trend,
            seasonality_note=seasonality_note,
        )

    async def explain_risk_assessment(
        self,
        client_name: str,
        amount: Decimal | str,
        invoice_date: str,
        due_date: str,
        risk_score: float,
        risk_factors: list[str] | None = None,
        client_history: dict[str, Any] | None = None,
    ) -> RiskAssessmentExplanation:
        """Generate explanation for invoice risk assessment.

        Args:
            client_name: Client name
            amount: Invoice amount
            invoice_date: Invoice date
            due_date: Due date
            risk_score: Risk score (0-1)
            risk_factors: Identified risk factors
            client_history: Client payment history

        Returns:
            RiskAssessmentExplanation
        """
        # Determine risk level
        if risk_score >= 0.7:
            risk_level = "high"
        elif risk_score >= 0.4:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Format risk factors
        factors_text = ""
        if risk_factors:
            factors_text = "\n".join(f"- {f}" for f in risk_factors)
        else:
            factors_text = "Keine spezifischen Risikofaktoren identifiziert"

        # Format client history
        history_text = ""
        if client_history:
            history_lines = []
            if "total_invoices" in client_history:
                history_lines.append(f"Gesamte Rechnungen: {client_history['total_invoices']}")
            if "paid_on_time" in client_history:
                history_lines.append(f"Pünktlich bezahlt: {client_history['paid_on_time']}")
            if "avg_payment_days" in client_history:
                history_lines.append(f"Durchschn. Zahlungsziel: {client_history['avg_payment_days']} Tage")
            if "total_overdue" in client_history:
                history_lines.append(f"Überfällige Rechnungen: {client_history['total_overdue']}")
            history_text = "\n".join(history_lines)
        else:
            history_text = "Keine Kundenhistorie verfügbar"

        # Build prompt
        prompt = RISK_EXPLANATION_PROMPT.format(
            client_name=client_name,
            amount=amount,
            invoice_date=invoice_date,
            due_date=due_date,
            risk_score=risk_score,
            risk_level={"high": "Hoch", "medium": "Mittel", "low": "Niedrig"}[risk_level],
            risk_factors=factors_text,
            client_history=history_text,
        )

        # Generate explanation
        response = await self._llm.generate(
            prompt=prompt,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
        )

        explanation = self._parse_explanation(response.content, 1.0 - risk_score)

        # Extract mitigation suggestions from response
        mitigation = []
        response_lower = response.content.lower()
        if "mahnung" in response_lower or "erinnerung" in response_lower:
            mitigation.append("Zahlungserinnerung senden")
        if "vorkasse" in response_lower:
            mitigation.append("Vorkasse für zukünftige Aufträge")
        if "ratenzahlung" in response_lower:
            mitigation.append("Ratenzahlung anbieten")
        if "inkasso" in response_lower:
            mitigation.append("Inkasso-Optionen prüfen")

        return RiskAssessmentExplanation(
            risk_level=risk_level,
            risk_score=risk_score,
            explanation=explanation,
            risk_factors=risk_factors or [],
            mitigation_suggestions=mitigation,
        )

    async def generate_clarification_questions(
        self,
        prediction_type: str,
        prediction_details: dict[str, Any],
        confidence: float,
    ) -> list[str]:
        """Generate clarification questions for low-confidence predictions.

        Args:
            prediction_type: Type of prediction (category, risk, etc.)
            prediction_details: Prediction details
            confidence: Prediction confidence

        Returns:
            List of clarification questions
        """
        if confidence >= self._config.low_confidence_threshold:
            return []

        # Format prediction details
        details_text = "\n".join(f"- {k}: {v}" for k, v in prediction_details.items())

        prompt = LOW_CONFIDENCE_CLARIFICATION_PROMPT.format(
            confidence=confidence,
            prediction_details=details_text,
        )

        response = await self._llm.generate(
            prompt=prompt,
            max_tokens=200,
            temperature=0.5,
        )

        # Parse questions from response
        questions = []
        for line in response.content.split("\n"):
            line = line.strip()
            if line and ("?" in line or line[0].isdigit()):
                # Clean up numbering
                line = line.lstrip("0123456789.-) ")
                if line:
                    questions.append(line)

        return questions[:3]  # Max 3 questions

    def _parse_explanation(
        self,
        response_text: str,
        confidence: float,
    ) -> MLExplanation:
        """Parse LLM response into structured explanation.

        Args:
            response_text: Raw LLM response
            confidence: Prediction confidence

        Returns:
            MLExplanation
        """
        # Determine confidence level
        if confidence >= self._config.high_confidence_threshold:
            confidence_level = "high"
        elif confidence >= self._config.low_confidence_threshold:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        # Extract first sentence as summary
        sentences = response_text.split(". ")
        summary = sentences[0] + "." if sentences else response_text[:100]

        # Extract key factors (look for bullet points or numbered items)
        key_factors = []
        for line in response_text.split("\n"):
            line = line.strip()
            if line.startswith(("-", "•", "*")) or (len(line) > 2 and line[0].isdigit() and line[1] in ".)"):
                factor = line.lstrip("-•*0123456789.) ").strip()
                if factor and len(factor) > 10:
                    key_factors.append(factor)

        # Extract recommendations (look for keywords)
        recommendations = []
        rec_keywords = ["empfehlung", "sollte", "empfehle", "ratsam", "wichtig"]
        for sentence in sentences:
            if any(kw in sentence.lower() for kw in rec_keywords):
                recommendations.append(sentence.strip())

        # Extract caveats
        caveats = []
        caveat_keywords = ["achtung", "beachte", "vorsicht", "allerdings", "jedoch", "aber"]
        for sentence in sentences:
            if any(kw in sentence.lower() for kw in caveat_keywords):
                caveats.append(sentence.strip())

        return MLExplanation(
            summary=summary[:200],
            explanation=response_text,
            confidence_level=confidence_level,
            key_factors=key_factors[:5] if self._config.include_key_factors else [],
            recommendations=recommendations[:3] if self._config.include_recommendations else [],
            caveats=caveats[:2],
        )

    def get_status(self) -> dict[str, Any]:
        """Get orchestrator status.

        Returns:
            Status dict
        """
        return {
            "ready": self._llm.is_ready,
            "config": {
                "high_confidence_threshold": self._config.high_confidence_threshold,
                "low_confidence_threshold": self._config.low_confidence_threshold,
            },
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_orchestrator: MLOrchestrator | None = None


def get_ml_orchestrator(
    llm_service: LLMService | None = None,
) -> MLOrchestrator:
    """Get or create the ML Orchestrator singleton.

    Args:
        llm_service: LLM service (required on first call)

    Returns:
        MLOrchestrator singleton instance
    """
    global _orchestrator
    if _orchestrator is None:
        if llm_service is None:
            raise ValueError("llm_service required for first initialization")
        _orchestrator = MLOrchestrator(llm_service)
    return _orchestrator
