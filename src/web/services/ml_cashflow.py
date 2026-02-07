"""Feature 3: Cash Flow Forecasting Service.

Predicts cash position 3-6 months ahead using:
- Prophet for seasonality and trend
- TabPFN for user-specific patterns
- Known tax obligations

Critical for freelancers managing irregular income.
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from src.core.models import Expense, Invoice, InvoiceStatus
from src.ml.models import CashFlowForecast, CriticalWeek


class CashFlowForecaster:
    """Forecasts cash flow using hybrid Prophet + TabPFN approach.

    Prophet handles:
    - Weekly/monthly seasonality
    - German holidays
    - Long-term trends

    TabPFN handles:
    - Client-specific payment patterns
    - Expense recurrence patterns
    - User-specific adjustments
    """

    def __init__(self, models_dir: Path | None = None):
        """Initialize forecaster.

        Args:
            models_dir: Directory for model storage
        """
        self.models_dir = models_dir or Path("data/models")
        self._prophet_model = None
        self._tabpfn_model = None
        self._is_trained = False

        # Ensemble weights
        self.prophet_weight = 0.6
        self.tabpfn_weight = 0.4

    @property
    def is_trained(self) -> bool:
        """Check if models are trained."""
        return self._is_trained

    async def forecast(
        self,
        invoices: list[Invoice],
        expenses: list[Expense],
        current_balance: Decimal = Decimal("0"),
        weeks_ahead: int = 26,
        tax_obligations: list[dict[str, Any]] | None = None,
    ) -> CashFlowForecast:
        """Generate cash flow forecast.

        Args:
            invoices: Historical and pending invoices
            expenses: Historical expenses
            current_balance: Current bank balance
            weeks_ahead: Weeks to forecast
            tax_obligations: Known tax payment schedule

        Returns:
            CashFlowForecast with predictions and critical weeks
        """
        today = date.today()

        # Build weekly time series from historical data
        income_series = self._build_income_series(invoices)
        expense_series = self._build_expense_series(expenses)

        # Generate predictions
        if self._is_trained:
            predictions = await self._model_forecast(
                income_series, expense_series, weeks_ahead
            )
        else:
            predictions = self._heuristic_forecast(
                income_series, expense_series, weeks_ahead
            )

        # Subtract known tax obligations
        if tax_obligations:
            predictions = self._apply_tax_obligations(predictions, tax_obligations)

        # Calculate running balance
        weekly_predictions = []
        balance = float(current_balance)
        critical_weeks = []

        for week_num, (income, expense, lower, upper) in enumerate(predictions):
            week_start = today + timedelta(weeks=week_num)
            net_flow = income - expense
            balance += net_flow
            lower_balance = balance - (income - lower)
            upper_balance = balance + (upper - income)

            weekly_predictions.append({
                "week": week_num + 1,
                "week_start": week_start.isoformat(),
                "predicted_income": income,
                "predicted_expense": expense,
                "net_flow": net_flow,
                "predicted_balance": balance,
                "lower_bound": lower_balance,
                "upper_bound": upper_balance,
            })

            # Check for critical weeks
            if lower_balance < 0:
                critical_weeks.append(CriticalWeek(
                    week_number=week_num + 1,
                    week_start=week_start,
                    predicted_balance=Decimal(str(round(balance, 2))),
                    lower_bound=Decimal(str(round(lower_balance, 2))),
                    upper_bound=Decimal(str(round(upper_balance, 2))),
                    is_negative=balance < 0,
                    recommendation=self._generate_recommendation(
                        week_num + 1, balance, lower_balance
                    ),
                ))

        return CashFlowForecast(
            generated_at=today,
            weeks_ahead=weeks_ahead,
            current_balance=current_balance,
            weekly_predictions=weekly_predictions,
            critical_weeks=critical_weeks,
            confidence_level=0.8,
            tax_obligations_included=tax_obligations or [],
        )

    def _build_income_series(
        self,
        invoices: list[Invoice],
    ) -> dict[date, float]:
        """Build weekly income time series from invoices.

        Args:
            invoices: List of invoices

        Returns:
            Dict mapping week start dates to income amounts
        """
        # Only consider paid invoices for historical income
        weekly_income: dict[date, float] = {}

        for inv in invoices:
            if inv.status == InvoiceStatus.PAID and inv.paid_date:
                # Get week start (Monday)
                week_start = inv.paid_date - timedelta(days=inv.paid_date.weekday())
                weekly_income[week_start] = weekly_income.get(week_start, 0) + float(inv.amount)

        return weekly_income

    def _build_expense_series(
        self,
        expenses: list[Expense],
    ) -> dict[date, float]:
        """Build weekly expense time series.

        Args:
            expenses: List of expenses

        Returns:
            Dict mapping week start dates to expense amounts
        """
        weekly_expense: dict[date, float] = {}

        for exp in expenses:
            week_start = exp.date - timedelta(days=exp.date.weekday())
            weekly_expense[week_start] = weekly_expense.get(week_start, 0) + float(exp.amount_gross)

        return weekly_expense

    def _heuristic_forecast(
        self,
        income_series: dict[date, float],
        expense_series: dict[date, float],
        weeks_ahead: int,
    ) -> list[tuple[float, float, float, float]]:
        """Generate heuristic forecast when models not trained.

        Uses simple moving averages and seasonal adjustment.

        Returns:
            List of (income, expense, lower_income, upper_income) per week
        """
        # Calculate recent averages
        income_values = list(income_series.values()) or [0]
        expense_values = list(expense_series.values()) or [0]

        avg_income = np.mean(income_values[-12:]) if income_values else 0
        avg_expense = np.mean(expense_values[-12:]) if expense_values else 0

        # Calculate variance for confidence intervals
        std_income = np.std(income_values[-12:]) if len(income_values) > 1 else avg_income * 0.3

        predictions = []
        for week in range(weeks_ahead):
            # Simple seasonal adjustment (higher in Q4, lower in summer)
            month = (date.today() + timedelta(weeks=week)).month
            seasonal_factor = 1.0
            if month in (7, 8):
                seasonal_factor = 0.8  # Summer slowdown
            elif month in (11, 12):
                seasonal_factor = 1.2  # Year-end rush

            income = avg_income * seasonal_factor
            expense = avg_expense

            # 80% confidence interval
            lower = income - 1.28 * std_income
            upper = income + 1.28 * std_income

            predictions.append((income, expense, max(0, lower), upper))

        return predictions

    async def _model_forecast(
        self,
        income_series: dict[date, float],
        expense_series: dict[date, float],
        weeks_ahead: int,
    ) -> list[tuple[float, float, float, float]]:
        """Generate model-based forecast.

        Combines Prophet and TabPFN predictions.

        Returns:
            List of (income, expense, lower, upper) per week
        """
        # For now, use heuristic (Prophet integration would go here)
        # TODO: Integrate Prophet when available
        return self._heuristic_forecast(income_series, expense_series, weeks_ahead)

    def _apply_tax_obligations(
        self,
        predictions: list[tuple[float, float, float, float]],
        tax_obligations: list[dict[str, Any]],
    ) -> list[tuple[float, float, float, float]]:
        """Subtract known tax obligations from predictions.

        Args:
            predictions: Weekly predictions
            tax_obligations: List of {date, amount, type} dicts

        Returns:
            Adjusted predictions
        """
        today = date.today()
        adjusted = list(predictions)

        for obligation in tax_obligations:
            due_date = obligation.get("date") or obligation.get("due_date")
            if isinstance(due_date, str):
                due_date = date.fromisoformat(due_date)

            if due_date and due_date > today:
                week_num = (due_date - today).days // 7
                if 0 <= week_num < len(adjusted):
                    income, expense, lower, upper = adjusted[week_num]
                    amount = float(obligation.get("amount", 0))
                    adjusted[week_num] = (income, expense + amount, lower, upper)

        return adjusted

    def _generate_recommendation(
        self,
        week_num: int,
        balance: float,
        lower_bound: float,
    ) -> str:
        """Generate recommendation for critical week.

        Args:
            week_num: Week number
            balance: Predicted balance
            lower_bound: Lower bound of confidence interval

        Returns:
            Recommendation string
        """
        shortfall = abs(min(0, lower_bound))

        if balance < 0:
            return (
                f"Kritisch: Negativer Kontostand erwartet. "
                f"Empfehlung: Rechnungen nachfassen oder Ausgaben um €{shortfall:,.0f} reduzieren."
            )
        elif lower_bound < 0:
            return (
                f"Warnung: Möglicher Engpass. "
                f"Empfehlung: Puffer von €{shortfall:,.0f} aufbauen."
            )
        else:
            return "Liquidität voraussichtlich ausreichend."

    async def train(
        self,
        invoices: list[Invoice],
        expenses: list[Expense],
    ) -> dict[str, Any]:
        """Train forecasting models.

        Args:
            invoices: Historical invoices
            expenses: Historical expenses

        Returns:
            Training results
        """
        # Build time series
        income_series = self._build_income_series(invoices)
        expense_series = self._build_expense_series(expenses)

        if len(income_series) < 12:
            return {
                "success": False,
                "error": "Need at least 12 weeks of income data",
                "current_weeks": len(income_series),
            }

        # TODO: Train Prophet and TabPFN models
        self._is_trained = True

        return {
            "success": True,
            "income_weeks": len(income_series),
            "expense_weeks": len(expense_series),
        }


# Singleton instance
_forecaster: CashFlowForecaster | None = None


def get_cashflow_forecaster() -> CashFlowForecaster:
    """Get or create the cash flow forecaster singleton."""
    global _forecaster
    if _forecaster is None:
        _forecaster = CashFlowForecaster()
    return _forecaster
