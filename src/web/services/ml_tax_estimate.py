"""Feature 4: Mid-Quarter Tax Liability Estimation Service.

Estimates tax liability based on current quarter trajectory:
- Einkommensteuer (income tax)
- Umsatzsteuer (VAT liability)
- Solidaritätszuschlag

Provides real-time estimates before official quarter-end calculations.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from src.core.models import Expense, Invoice
from src.core.tax.einkommensteuer import EinkommensteuerCalculator
from src.ml.features import extract_temporal_features
from src.ml.models import TaxLiabilityEstimate
from src.ml.tabpfn_wrapper import FiscFoxTabPFN


class MidQuarterTaxEstimator:
    """Estimates tax liability mid-quarter using trajectory analysis.

    Uses TabPFN to learn seasonal patterns and adjust linear projections
    based on historical accuracy.
    """

    def __init__(self, models_dir: Path | None = None):
        """Initialize estimator.

        Args:
            models_dir: Directory for model storage
        """
        self.models_dir = models_dir or Path("data/models")
        self._adjustment_model = None
        self._is_trained = False
        self._historical_accuracy: list[float] = []

    @property
    def is_trained(self) -> bool:
        """Check if adjustment model is trained."""
        return self._is_trained

    async def estimate(
        self,
        invoices: list[Invoice],
        expenses: list[Expense],
        as_of_date: date | None = None,
        previous_quarters: list[dict[str, Any]] | None = None,
    ) -> TaxLiabilityEstimate:
        """Estimate tax liability for current quarter.

        Args:
            invoices: All invoices (current and historical)
            expenses: All expenses (current and historical)
            as_of_date: Date to estimate as of (default: today)
            previous_quarters: Historical quarter data for comparison

        Returns:
            TaxLiabilityEstimate with projections
        """
        as_of_date = as_of_date or date.today()
        quarter_info = self._get_quarter_info(as_of_date)

        # Get current quarter data
        current_revenue = self._get_period_revenue(
            invoices, quarter_info["start"], as_of_date
        )
        current_expenses = self._get_period_expenses(
            expenses, quarter_info["start"], as_of_date
        )

        # Linear projection to quarter end
        days_elapsed = quarter_info["days_elapsed"]
        days_in_quarter = quarter_info["days_total"]

        if days_elapsed > 0:
            linear_revenue = current_revenue * Decimal(str(days_in_quarter / days_elapsed))
            linear_expenses = current_expenses * Decimal(str(days_in_quarter / days_elapsed))
        else:
            linear_revenue = Decimal("0")
            linear_expenses = Decimal("0")

        # Apply ML adjustment if trained
        if self._is_trained and self._adjustment_model:
            adjustment = await self._get_adjustment_factor(
                days_elapsed, current_revenue, as_of_date
            )
            projected_revenue = linear_revenue * Decimal(str(adjustment))
        else:
            # Heuristic adjustment based on position in quarter
            adjustment = self._heuristic_adjustment(days_elapsed, days_in_quarter)
            projected_revenue = linear_revenue * adjustment

        projected_expenses = linear_expenses  # Expenses are more predictable

        # Calculate taxes using existing calculators
        taxable_income = projected_revenue - projected_expenses
        annual_taxable = taxable_income * 4  # Annualize for tax calculation

        try:
            est_calc = EinkommensteuerCalculator(as_of_date.year)
            tax_result = est_calc.calculate(annual_taxable)
            quarterly_income_tax = tax_result.einkommensteuer / 4
            quarterly_soli = tax_result.solidaritaetszuschlag / 4
        except Exception:
            # Fallback simple calculation
            quarterly_income_tax = taxable_income * Decimal("0.25")
            quarterly_soli = Decimal("0")

        # Calculate VAT liability
        vat_collected = self._get_period_vat_collected(
            invoices, quarter_info["start"], quarter_info["end"]
        )
        vat_paid = self._get_period_vat_paid(
            expenses, quarter_info["start"], quarter_info["end"]
        )
        vat_liability = vat_collected - vat_paid

        # Scale VAT to full quarter
        if days_elapsed > 0:
            vat_liability = vat_liability * Decimal(str(days_in_quarter / days_elapsed))

        total_liability = quarterly_income_tax + quarterly_soli + max(Decimal("0"), vat_liability)

        # Calculate confidence based on days elapsed
        confidence = min(0.95, 0.4 + (days_elapsed / days_in_quarter) * 0.5)

        # Compare to previous quarter
        vs_previous = None
        if previous_quarters:
            last_quarter = previous_quarters[-1]
            last_total = Decimal(str(last_quarter.get("total_liability", 0)))
            if last_total > 0:
                vs_previous = float((total_liability - last_total) / last_total * 100)

        # Generate recommendation
        recommendation = self._generate_recommendation(
            total_liability, confidence, days_elapsed, days_in_quarter
        )

        return TaxLiabilityEstimate(
            quarter=quarter_info["quarter_str"],
            days_elapsed=days_elapsed,
            days_in_quarter=days_in_quarter,
            current_revenue=current_revenue,
            current_expenses=current_expenses,
            projected_revenue=projected_revenue,
            projected_expenses=projected_expenses,
            estimated_income_tax=quarterly_income_tax + quarterly_soli,
            estimated_vat_liability=max(Decimal("0"), vat_liability),
            total_estimated_liability=total_liability,
            confidence=confidence,
            vs_previous_quarter=vs_previous,
            recommendation=recommendation,
        )

    def _get_quarter_info(self, d: date) -> dict[str, Any]:
        """Get quarter information for a date.

        Args:
            d: Date to analyze

        Returns:
            Dict with quarter details
        """
        quarter = (d.month - 1) // 3 + 1
        year = d.year

        # Quarter boundaries
        quarter_starts = {
            1: date(year, 1, 1),
            2: date(year, 4, 1),
            3: date(year, 7, 1),
            4: date(year, 10, 1),
        }
        quarter_ends = {
            1: date(year, 3, 31),
            2: date(year, 6, 30),
            3: date(year, 9, 30),
            4: date(year, 12, 31),
        }

        start = quarter_starts[quarter]
        end = quarter_ends[quarter]
        days_elapsed = (d - start).days + 1
        days_total = (end - start).days + 1

        return {
            "quarter": quarter,
            "year": year,
            "quarter_str": f"{year}-Q{quarter}",
            "start": start,
            "end": end,
            "days_elapsed": days_elapsed,
            "days_total": days_total,
        }

    def _get_period_revenue(
        self,
        invoices: list[Invoice],
        start: date,
        end: date,
    ) -> Decimal:
        """Calculate revenue for a period.

        Args:
            invoices: All invoices
            start: Period start
            end: Period end

        Returns:
            Total revenue (net)
        """
        total = Decimal("0")
        for inv in invoices:
            if start <= inv.date <= end:
                # Use amount_net if available
                if hasattr(inv, "amount_net"):
                    total += inv.amount_net
                else:
                    # Calculate net from gross
                    rate = Decimal(inv.vat_rate.value)
                    total += inv.amount / (1 + rate)
        return total

    def _get_period_expenses(
        self,
        expenses: list[Expense],
        start: date,
        end: date,
    ) -> Decimal:
        """Calculate expenses for a period.

        Args:
            expenses: All expenses
            start: Period start
            end: Period end

        Returns:
            Total expenses (net)
        """
        total = Decimal("0")
        for exp in expenses:
            if start <= exp.date <= end:
                total += exp.amount_net
        return total

    def _get_period_vat_collected(
        self,
        invoices: list[Invoice],
        start: date,
        end: date,
    ) -> Decimal:
        """Calculate VAT collected for a period.

        Args:
            invoices: All invoices
            start: Period start
            end: Period end

        Returns:
            Total VAT collected
        """
        total = Decimal("0")
        for inv in invoices:
            if start <= inv.date <= end:
                # Skip reverse charge
                if getattr(inv, "is_reverse_charge", False):
                    continue
                if hasattr(inv, "vat_amount"):
                    total += inv.vat_amount
                else:
                    rate = Decimal(inv.vat_rate.value)
                    total += inv.amount - (inv.amount / (1 + rate))
        return total

    def _get_period_vat_paid(
        self,
        expenses: list[Expense],
        start: date,
        end: date,
    ) -> Decimal:
        """Calculate VAT paid (Vorsteuer) for a period.

        Args:
            expenses: All expenses
            start: Period start
            end: Period end

        Returns:
            Total VAT paid
        """
        total = Decimal("0")
        for exp in expenses:
            if start <= exp.date <= end:
                total += exp.vat_amount
        return total

    def _heuristic_adjustment(
        self,
        days_elapsed: int,
        days_in_quarter: int,
    ) -> Decimal:
        """Heuristic adjustment factor for projection.

        Early in quarter, projections are less reliable.
        Late in quarter, they're more accurate.

        Args:
            days_elapsed: Days into quarter
            days_in_quarter: Total days in quarter

        Returns:
            Adjustment factor
        """
        progress = days_elapsed / days_in_quarter

        if progress < 0.3:
            # First month: reduce projection (historically overestimates)
            return Decimal("0.85")
        elif progress < 0.6:
            # Second month: slight reduction
            return Decimal("0.95")
        else:
            # Third month: projection is reliable
            return Decimal("1.0")

    async def _get_adjustment_factor(
        self,
        days_elapsed: int,
        current_revenue: Decimal,
        as_of_date: date,
    ) -> float:
        """Get ML-based adjustment factor.

        Args:
            days_elapsed: Days into quarter
            current_revenue: Revenue so far
            as_of_date: Current date

        Returns:
            Adjustment factor (typically 0.8 - 1.2)
        """
        if not self._adjustment_model:
            return 1.0

        temporal = extract_temporal_features(as_of_date)
        features = np.array([[
            days_elapsed,
            float(current_revenue),
            temporal["month_sin"],
            temporal["month_cos"],
            temporal["quarter"],
        ]])

        adjustment = self._adjustment_model.predict(features)[0]
        # Clamp to reasonable range
        return max(0.7, min(1.3, adjustment))

    def _generate_recommendation(
        self,
        total_liability: Decimal,
        confidence: float,
        days_elapsed: int,
        days_in_quarter: int,
    ) -> str:
        """Generate recommendation based on estimate.

        Args:
            total_liability: Estimated total tax liability
            confidence: Confidence level
            days_elapsed: Days into quarter
            days_in_quarter: Total days in quarter

        Returns:
            Recommendation string
        """
        progress = days_elapsed / days_in_quarter

        # Suggest setting aside with buffer
        buffer = Decimal("1.2") if progress < 0.5 else Decimal("1.1")
        suggested = (total_liability * buffer).quantize(Decimal("100"))

        if progress < 0.3:
            return (
                f"Früh im Quartal - Schätzung unsicher. "
                f"Empfehlung: €{suggested:,.0f} für Steuern zurücklegen (mit Puffer)."
            )
        elif progress < 0.7:
            return (
                f"Empfehlung: €{suggested:,.0f} für Steuern zurücklegen. "
                f"Schätzung wird genauer gegen Quartalsende."
            )
        else:
            return (
                f"Zuverlässige Schätzung. "
                f"Empfehlung: €{total_liability:,.0f} für Steuern vorbereiten."
            )

    async def train(
        self,
        historical_quarters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Train adjustment model on historical accuracy.

        Args:
            historical_quarters: List of past quarter data with
                actual vs projected values

        Returns:
            Training results
        """
        if len(historical_quarters) < 4:
            return {
                "success": False,
                "error": "Need at least 4 quarters of history",
                "current_quarters": len(historical_quarters),
            }

        # Extract features and labels
        features = []
        labels = []

        for q in historical_quarters:
            if "projected" in q and "actual" in q:
                features.append([
                    q.get("days_elapsed", 45),
                    q.get("revenue_at_projection", 0),
                    q.get("quarter", 1),
                ])
                # Adjustment factor = actual / projected
                if q["projected"] > 0:
                    labels.append(q["actual"] / q["projected"])

        if len(features) < 4:
            return {
                "success": False,
                "error": "Insufficient valid historical data",
            }

        X = np.array(features)
        y = np.array(labels)

        self._adjustment_model = FiscFoxTabPFN.create_regressor()
        self._adjustment_model.fit(X, y)
        self._is_trained = True

        return {
            "success": True,
            "quarters_used": len(features),
            "avg_adjustment": float(np.mean(labels)),
        }


# Singleton instance
_estimator: MidQuarterTaxEstimator | None = None


def get_tax_estimator() -> MidQuarterTaxEstimator:
    """Get or create the tax estimator singleton."""
    global _estimator
    if _estimator is None:
        _estimator = MidQuarterTaxEstimator()
    return _estimator
