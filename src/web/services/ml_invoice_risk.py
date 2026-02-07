"""Feature 2: Invoice Payment Risk Scoring Service.

Predicts which invoices are at risk of late or non-payment based on:
- Invoice amount and payment terms
- Client payment history
- Temporal patterns
- Client country and reverse charge status

Helps prioritize follow-up and manage cash flow.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from src.core.models import Invoice, InvoiceStatus
from src.ml.base import ClassificationPredictor, RegressionPredictor
from src.ml.features import (
    calculate_statistics,
    cyclical_encode,
    extract_temporal_features,
    log_transform,
)
from src.ml.models import (
    InvoiceRiskScore,
    InvoiceRiskSummary,
    RiskLevel,
)


class InvoiceRiskScorer:
    """Scores invoices for payment risk.

    Uses two models:
    1. Regressor: Predicts days to payment
    2. Classifier: Predicts risk category (low/medium/high)

    Combines both for a 0-100 risk score.
    """

    def __init__(self, models_dir: Path | None = None):
        """Initialize risk scorer.

        Args:
            models_dir: Directory for model storage
        """
        self.models_dir = models_dir or Path("data/models")
        self.delay_predictor = PaymentDelayPredictor(models_dir)
        self.risk_classifier = PaymentRiskClassifier(models_dir)

        # Cache for client history
        self._client_cache: dict[int, dict[str, Any]] = {}

    def clear_cache(self) -> None:
        """Clear client history cache."""
        self._client_cache.clear()

    async def score_invoice(
        self,
        invoice: Invoice,
        client_history: list[Invoice] | None = None,
    ) -> InvoiceRiskScore:
        """Score a single invoice for payment risk.

        Args:
            invoice: Invoice to score
            client_history: Optional pre-fetched client payment history

        Returns:
            InvoiceRiskScore with risk assessment
        """
        # Extract features
        features = self._extract_invoice_features(invoice, client_history or [])

        # Get predictions from both models
        if self.delay_predictor.is_trained:
            predicted_days, _ = await self.delay_predictor.predict(features)
        else:
            predicted_days = self._heuristic_days(invoice, client_history or [])

        if self.risk_classifier.is_trained:
            risk_class, confidence = await self.risk_classifier.predict(features)
        else:
            risk_class, confidence = self._heuristic_risk(predicted_days)

        # Calculate composite risk score (0-100)
        risk_score = self._calculate_risk_score(predicted_days, risk_class, confidence)

        # Identify risk factors
        risk_factors = self._identify_risk_factors(invoice, client_history or [], features)

        return InvoiceRiskScore(
            invoice_id=invoice.id,
            risk_score=risk_score,
            risk_level=RiskLevel(risk_class),
            predicted_days_to_payment=predicted_days,
            confidence=confidence,
            risk_factors=risk_factors,
        )

    async def score_all_pending(
        self,
        pending_invoices: list[Invoice],
        all_invoices: list[Invoice] | None = None,
    ) -> InvoiceRiskSummary:
        """Score all pending invoices.

        Args:
            pending_invoices: List of pending invoices to score
            all_invoices: All invoices for history (if not provided, uses pending only)

        Returns:
            InvoiceRiskSummary with all risk assessments
        """
        # Build client history lookup
        client_invoices: dict[int, list[Invoice]] = {}
        for inv in (all_invoices or pending_invoices):
            client_id = getattr(inv, "client_id", 0) or 0
            if client_id not in client_invoices:
                client_invoices[client_id] = []
            client_invoices[client_id].append(inv)

        # Score each pending invoice
        scores = []
        for invoice in pending_invoices:
            client_id = getattr(invoice, "client_id", 0) or 0
            history = client_invoices.get(client_id, [])
            score = await self.score_invoice(invoice, history)
            scores.append(score)

        # Sort by risk (highest first)
        scores.sort(key=lambda s: s.risk_score, reverse=True)

        # Calculate summary
        high_risk = [s for s in scores if s.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)]
        total_pending = sum(
            Decimal(str(inv.amount)) for inv in pending_invoices
        )
        high_risk_amount = sum(
            Decimal(str(inv.amount))
            for inv, score in zip(pending_invoices, scores)
            if score.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        )

        return InvoiceRiskSummary(
            total_pending=len(pending_invoices),
            total_pending_amount=total_pending,
            high_risk_count=len(high_risk),
            high_risk_amount=high_risk_amount,
            avg_predicted_days=np.mean([s.predicted_days_to_payment for s in scores]) if scores else 0,
            top_risks=scores[:5],
        )

    def _extract_invoice_features(
        self,
        invoice: Invoice,
        client_history: list[Invoice],
    ) -> dict[str, float]:
        """Extract features for risk prediction.

        Args:
            invoice: Invoice to extract features from
            client_history: Client's payment history

        Returns:
            Feature dictionary
        """
        # Invoice features
        amount = float(invoice.amount)
        payment_terms = 14  # Default
        if invoice.due_date and invoice.date:
            payment_terms = (invoice.due_date - invoice.date).days

        is_reverse_charge = getattr(invoice, "is_reverse_charge", False)
        client_country = getattr(invoice, "client_country", "DE") or "DE"

        # Temporal features
        temporal = extract_temporal_features(invoice.date)

        # Client history features
        paid_invoices = [inv for inv in client_history if inv.status == InvoiceStatus.PAID]
        if paid_invoices:
            days_to_pay = []
            for inv in paid_invoices:
                if inv.paid_date and inv.due_date:
                    days_to_pay.append((inv.paid_date - inv.due_date).days)

            hist_stats = calculate_statistics(days_to_pay)
            payment_rate = len(paid_invoices) / len(client_history) if client_history else 1.0
        else:
            hist_stats = {"mean": 0, "std": 0, "max": 0}
            payment_rate = 1.0

        return {
            "amount_log": log_transform(Decimal(str(amount))),
            "payment_terms": payment_terms,
            "is_reverse_charge": float(is_reverse_charge),
            "is_international": float(client_country != "DE"),
            "day_of_week_sin": temporal["day_of_week_sin"],
            "day_of_week_cos": temporal["day_of_week_cos"],
            "month_sin": temporal["month_sin"],
            "month_cos": temporal["month_cos"],
            "is_quarter_end": temporal["is_quarter_end"],
            "client_avg_days_late": hist_stats["mean"],
            "client_std_days": hist_stats["std"],
            "client_max_late": hist_stats["max"],
            "client_payment_rate": payment_rate,
            "client_invoice_count": len(client_history),
        }

    def _calculate_risk_score(
        self,
        predicted_days: float,
        risk_class: str,
        confidence: float,
    ) -> float:
        """Calculate composite 0-100 risk score.

        Args:
            predicted_days: Predicted days to payment
            risk_class: Predicted risk class
            confidence: Model confidence

        Returns:
            Risk score 0-100
        """
        # Base score from risk class
        class_scores = {
            "low": 20,
            "medium": 50,
            "high": 75,
            "critical": 90,
        }
        base_score = class_scores.get(risk_class, 50)

        # Adjust based on predicted days
        if predicted_days > 30:
            base_score = min(100, base_score + 15)
        elif predicted_days > 14:
            base_score = min(100, base_score + 5)
        elif predicted_days < 7:
            base_score = max(0, base_score - 10)

        # Weight by confidence
        return base_score * confidence + (50 * (1 - confidence))

    def _identify_risk_factors(
        self,
        invoice: Invoice,
        client_history: list[Invoice],
        features: dict[str, float],
    ) -> list[str]:
        """Identify specific risk factors for an invoice.

        Args:
            invoice: Invoice being analyzed
            client_history: Client payment history
            features: Extracted features

        Returns:
            List of risk factor descriptions
        """
        factors = []

        # High amount
        if features["amount_log"] > 8:  # ~$3000+
            factors.append("Hoher Rechnungsbetrag")

        # International
        if features["is_international"]:
            factors.append("Internationaler Kunde")

        # Poor payment history
        if features["client_avg_days_late"] > 14:
            factors.append(f"Kunde zahlt im Schnitt {int(features['client_avg_days_late'])} Tage zu spät")

        if features["client_payment_rate"] < 0.8:
            factors.append(f"Nur {int(features['client_payment_rate'] * 100)}% der Rechnungen bezahlt")

        # New client
        if features["client_invoice_count"] < 3:
            factors.append("Neuer Kunde (wenig Historie)")

        # Quarter end timing
        if features["is_quarter_end"]:
            factors.append("Quartalsende (erhöhte Zahlungsverzögerungen)")

        return factors

    def _heuristic_days(
        self,
        invoice: Invoice,
        client_history: list[Invoice],
    ) -> float:
        """Heuristic prediction when model not trained.

        Args:
            invoice: Invoice to predict
            client_history: Client history

        Returns:
            Estimated days to payment
        """
        base_days = 14.0

        # Adjust based on client history
        paid = [inv for inv in client_history if inv.status == InvoiceStatus.PAID and inv.paid_date]
        if paid:
            avg_days = np.mean([
                (inv.paid_date - inv.date).days for inv in paid
            ])
            base_days = avg_days

        # Adjust for amount
        if float(invoice.amount) > 5000:
            base_days += 5

        # Adjust for international
        if getattr(invoice, "client_country", "DE") != "DE":
            base_days += 7

        return max(1, base_days)

    def _heuristic_risk(self, predicted_days: float) -> tuple[str, float]:
        """Heuristic risk classification when model not trained.

        Args:
            predicted_days: Predicted days to payment

        Returns:
            (risk_class, confidence) tuple
        """
        if predicted_days > 30:
            return "high", 0.5
        elif predicted_days > 21:
            return "medium", 0.5
        else:
            return "low", 0.5

    async def train(
        self,
        training_invoices: list[Invoice],
    ) -> dict[str, Any]:
        """Train both prediction models.

        Args:
            training_invoices: Invoices with payment history

        Returns:
            Training results
        """
        # Only use paid invoices with known payment dates
        paid = [inv for inv in training_invoices if inv.status == InvoiceStatus.PAID and inv.paid_date]

        if len(paid) < 20:
            return {
                "success": False,
                "error": "Need at least 20 paid invoices with dates",
                "current_samples": len(paid),
            }

        # Train delay predictor
        delay_result = self.delay_predictor.train(paid)

        # Train risk classifier
        risk_result = self.risk_classifier.train(paid)

        return {
            "success": delay_result.get("success", False) and risk_result.get("success", False),
            "delay_predictor": delay_result,
            "risk_classifier": risk_result,
        }


class PaymentDelayPredictor(RegressionPredictor):
    """Predicts number of days until payment."""

    def __init__(self, models_dir: Path | None = None):
        super().__init__(
            model_name="payment_delay",
            models_dir=models_dir,
            min_samples_to_train=20,
        )

    def _extract_features(self, data: Any) -> np.ndarray:
        """Extract features from invoice data."""
        if isinstance(data, dict):
            return np.array([[
                data.get("amount_log", 0),
                data.get("payment_terms", 14),
                data.get("is_reverse_charge", 0),
                data.get("is_international", 0),
                data.get("day_of_week_sin", 0),
                data.get("day_of_week_cos", 0),
                data.get("month_sin", 0),
                data.get("month_cos", 0),
                data.get("client_avg_days_late", 0),
                data.get("client_payment_rate", 1),
                data.get("client_invoice_count", 0),
            ]])

        # List of invoices for training
        features = []
        for inv in data:
            features.append([
                log_transform(inv.amount),
                (inv.due_date - inv.date).days if inv.due_date else 14,
                float(getattr(inv, "is_reverse_charge", False)),
                float(getattr(inv, "client_country", "DE") != "DE"),
                cyclical_encode(inv.date.weekday(), 7)[0],
                cyclical_encode(inv.date.weekday(), 7)[1],
                cyclical_encode(inv.date.month - 1, 12)[0],
                cyclical_encode(inv.date.month - 1, 12)[1],
                0,  # Would need client history lookup
                1,
                0,
            ])
        return np.array(features)

    def _extract_labels(self, data: Any) -> np.ndarray:
        """Extract days to payment labels."""
        labels = []
        for inv in data:
            if inv.paid_date and inv.date:
                days = (inv.paid_date - inv.date).days
            else:
                days = 14  # Default
            labels.append(max(0, days))
        return np.array(labels)


class PaymentRiskClassifier(ClassificationPredictor):
    """Classifies invoices into risk categories."""

    def __init__(self, models_dir: Path | None = None):
        super().__init__(
            model_name="payment_risk",
            classes=["low", "medium", "high", "critical"],
            models_dir=models_dir,
            min_samples_to_train=20,
        )

    def _extract_features(self, data: Any) -> np.ndarray:
        """Extract features from invoice data."""
        if isinstance(data, dict):
            return np.array([[
                data.get("amount_log", 0),
                data.get("payment_terms", 14),
                data.get("is_international", 0),
                data.get("client_avg_days_late", 0),
                data.get("client_payment_rate", 1),
                data.get("client_invoice_count", 0),
            ]])

        features = []
        for inv in data:
            features.append([
                log_transform(inv.amount),
                (inv.due_date - inv.date).days if inv.due_date else 14,
                float(getattr(inv, "client_country", "DE") != "DE"),
                0,
                1,
                0,
            ])
        return np.array(features)

    def _extract_labels(self, data: Any) -> np.ndarray:
        """Classify invoices based on actual payment behavior."""
        labels = []
        for inv in data:
            if inv.paid_date and inv.due_date:
                days_late = (inv.paid_date - inv.due_date).days
                if days_late <= 0:
                    labels.append(0)  # low
                elif days_late <= 14:
                    labels.append(1)  # medium
                elif days_late <= 30:
                    labels.append(2)  # high
                else:
                    labels.append(3)  # critical
            else:
                labels.append(0)  # Assume low risk for paid without date
        return np.array(labels)


# Singleton instance
_scorer: InvoiceRiskScorer | None = None


def get_invoice_risk_scorer() -> InvoiceRiskScorer:
    """Get or create the invoice risk scorer singleton."""
    global _scorer
    if _scorer is None:
        _scorer = InvoiceRiskScorer()
    return _scorer
