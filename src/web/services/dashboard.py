"""Dashboard service for aggregating financial data and tax calculations.

Orchestrates data from repositories and tax calculators to provide
comprehensive dashboard statistics. Includes caching for performance.
"""

import logging
from datetime import date
from decimal import Decimal

from src.core.cache import dashboard_cache, prediction_cache
from src.core.models import (
    DashboardStats,
    QuarterlyPayment,
    TaxDeadline,
    TaxEstimate,
)
from src.core.tax import (
    DeadlineCalculator,
    EinkommensteuerCalculator,
)
from src.core.tax.deadlines import DeadlineConfig, UstFrequency
from src.db.repository import (
    AssetRepository,
    ExpenseRepository,
    GiftExpenseRepository,
    HomeOfficeRepository,
    InvoiceRepository,
    SettingsRepository,
    TravelExpenseRepository,
)

logger = logging.getLogger(__name__)


class DashboardService:
    """Service for dashboard data aggregation.

    Combines data from multiple repositories with tax calculations
    to provide comprehensive financial overview.
    """

    def __init__(
        self,
        expense_repo: ExpenseRepository | None = None,
        invoice_repo: InvoiceRepository | None = None,
        settings_repo: SettingsRepository | None = None,
        asset_repo: AssetRepository | None = None,
        travel_repo: TravelExpenseRepository | None = None,
        gift_repo: GiftExpenseRepository | None = None,
        homeoffice_repo: HomeOfficeRepository | None = None,
    ):
        """Initialize dashboard service.

        Args:
            expense_repo: Expense repository (default: new instance)
            invoice_repo: Invoice repository (default: new instance)
            settings_repo: Settings repository (default: new instance)
            asset_repo: Asset repository (default: new instance)
            travel_repo: Travel expense repository (default: new instance)
            gift_repo: Gift expense repository (default: new instance)
            homeoffice_repo: Home office repository (default: new instance)
        """
        self.expense_repo = expense_repo or ExpenseRepository()
        self.invoice_repo = invoice_repo or InvoiceRepository()
        self.settings_repo = settings_repo or SettingsRepository()
        self.asset_repo = asset_repo or AssetRepository()
        self.travel_repo = travel_repo or TravelExpenseRepository()
        self.gift_repo = gift_repo or GiftExpenseRepository()
        self.homeoffice_repo = homeoffice_repo or HomeOfficeRepository()

    async def get_dashboard_stats(
        self,
        year: int | None = None,
        use_cache: bool = True,
    ) -> DashboardStats:
        """Get comprehensive dashboard statistics.

        Args:
            year: Tax year (default: current year)
            use_cache: Whether to use cached results (default: True)

        Returns:
            DashboardStats with all financial metrics
        """
        year = year or date.today().year

        if use_cache:
            return await dashboard_cache.get_or_compute(
                f"stats_{year}",
                lambda: self._compute_dashboard_stats(year)
            )
        return await self._compute_dashboard_stats(year)

    async def _compute_dashboard_stats(self, year: int) -> DashboardStats:
        """Compute dashboard statistics (uncached).

        Internal method that performs the actual computation.
        """
        from src.web.routes.settings import get_activity_start_date

        logger.debug(f"Computing dashboard stats for year {year}")
        activity_start = get_activity_start_date()

        # Date ranges for current and previous periods
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        today = date.today()

        # Clamp to activity start date if set
        if activity_start and activity_start > year_start:
            year_start = activity_start

        # Previous year range (for year-over-year comparison)
        prev_year_start = date(year - 1, 1, 1)
        prev_year_end = date(year - 1, 12, 31)
        # Also clamp previous year to activity start if applicable
        if activity_start and activity_start > prev_year_start:
            prev_year_start = max(prev_year_start, activity_start)

        # Get revenue data for current year
        revenue_net, revenue_vat, reverse_charge = await self.invoice_repo.get_revenue_by_period(
            year_start, year_end
        )
        total_revenue = revenue_net + revenue_vat

        # Get expense data for current year
        expenses_net, vorsteuer = await self.expense_repo.get_total_by_period(
            year_start, year_end
        )
        # Total expenses is gross (net + VAT paid)
        total_expenses = expenses_net + vorsteuer

        # Previous year revenue (for YoY comparison)
        prev_year_net, prev_year_vat, _ = await self.invoice_repo.get_revenue_by_period(
            prev_year_start, prev_year_end
        )
        prev_year_revenue = prev_year_net + prev_year_vat

        # Previous year expenses (for YoY comparison)
        prev_year_exp_net, prev_year_vorst = await self.expense_repo.get_total_by_period(
            prev_year_start, prev_year_end
        )
        prev_year_expenses = prev_year_exp_net + prev_year_vorst

        # Calculate year-over-year percentage changes
        revenue_change = self._calculate_change(total_revenue, prev_year_revenue)
        expense_change = self._calculate_change(total_expenses, prev_year_expenses)

        # Calculate estimated tax
        taxable_income = revenue_net - expenses_net
        est_calc = EinkommensteuerCalculator(year)
        est_result = est_calc.calculate(taxable_income)

        # Effective tax rate
        effective_rate = (
            (est_result.total_tax / taxable_income * 100).quantize(Decimal("0.1"))
            if taxable_income > 0 else Decimal("0")
        )

        # Get next USt deadline
        deadline_calc = DeadlineCalculator()
        config = DeadlineConfig(
            ust_frequency=UstFrequency.MONTHLY,
            has_eu_clients=reverse_charge > 0,
        )
        deadlines = deadline_calc.get_upcoming_deadlines(year, config, lookahead_days=60)
        ust_deadlines = [d for d in deadlines if d.type == "umsatzsteuer"]
        next_ust_date = ust_deadlines[0].date.strftime("%d.%m.%Y") if ust_deadlines else "—"

        return DashboardStats(
            total_revenue=total_revenue.quantize(Decimal("0.01")),
            total_expenses=total_expenses.quantize(Decimal("0.01")),
            vat_collected=revenue_vat.quantize(Decimal("0.01")),
            estimated_tax=est_result.total_tax.quantize(Decimal("0.01")),
            revenue_change=revenue_change,
            expense_change=expense_change,
            tax_rate=effective_rate,
            next_ust_date=next_ust_date,
        )

    async def get_tax_estimate(
        self,
        year: int | None = None,
        use_cache: bool = True,
    ) -> TaxEstimate:
        """Get comprehensive tax estimate for the year.

        Args:
            year: Tax year (default: current year)
            use_cache: Whether to use cached results (default: True)

        Returns:
            TaxEstimate with detailed breakdown
        """
        year = year or date.today().year

        if use_cache:
            return await prediction_cache.get_or_compute(
                f"tax_estimate_{year}",
                lambda: self._compute_tax_estimate(year)
            )
        return await self._compute_tax_estimate(year)

    async def _compute_tax_estimate(self, year: int) -> TaxEstimate:
        """Compute tax estimate (uncached).

        Internal method that performs the actual computation.
        """
        from src.web.routes.settings import get_activity_start_date

        logger.debug(f"Computing tax estimate for year {year}")
        activity_start = get_activity_start_date()
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        # Clamp to activity start date if set
        if activity_start and activity_start > year_start:
            year_start = activity_start

        # Get financial data
        revenue_net, revenue_vat, _ = await self.invoice_repo.get_revenue_by_period(
            year_start, year_end
        )
        expenses_net, vorsteuer = await self.expense_repo.get_total_by_period(
            year_start, year_end
        )

        # Calculate taxable income
        taxable_income = revenue_net - expenses_net
        taxable_income = max(taxable_income, Decimal("0"))

        # Calculate income tax
        est_calc = EinkommensteuerCalculator(year)
        est_result = est_calc.calculate(taxable_income)

        # Calculate VAT liability (USt - Vorsteuer)
        ust_liability = revenue_vat - vorsteuer

        # Total tax burden
        total_burden = est_result.total_tax + max(ust_liability, Decimal("0"))

        # Effective rate
        total_income = revenue_net + revenue_vat
        effective_rate = (
            (total_burden / total_income * 100).quantize(Decimal("0.1"))
            if total_income > 0 else Decimal("0")
        )

        # Quarterly payment suggestion
        quarterly_payment = est_calc.calculate_quarterly_payment(est_result.einkommensteuer)

        return TaxEstimate(
            estimated_income=revenue_net.quantize(Decimal("0.01")),
            estimated_expenses=expenses_net.quantize(Decimal("0.01")),
            taxable_income=taxable_income.quantize(Decimal("0.01")),
            einkommensteuer=est_result.einkommensteuer.quantize(Decimal("0.01")),
            solidaritaetszuschlag=est_result.solidaritaetszuschlag.quantize(Decimal("0.01")),
            umsatzsteuer_liability=ust_liability.quantize(Decimal("0.01")),
            total_tax_burden=total_burden.quantize(Decimal("0.01")),
            effective_rate=effective_rate,
            quarterly_payment=quarterly_payment.quantize(Decimal("0.01")),
        )

    async def get_upcoming_deadlines(
        self,
        year: int | None = None,
        lookahead_days: int = 90,
    ) -> list[TaxDeadline]:
        """Get upcoming tax deadlines.

        Args:
            year: Tax year (default: current year)
            lookahead_days: How many days ahead to look

        Returns:
            List of TaxDeadline objects sorted by date
        """
        year = year or date.today().year

        # Get settings for deadline configuration from user settings JSON
        from src.web.routes.settings import load_settings
        user_settings = load_settings()

        # Map string to enum
        freq_map = {
            "monthly": UstFrequency.MONTHLY,
            "quarterly": UstFrequency.QUARTERLY,
            "annual": UstFrequency.ANNUAL,
        }
        ust_frequency = freq_map.get(user_settings.ust_frequency, UstFrequency.MONTHLY)

        # Calculate deadlines
        today = date.today()

        config = DeadlineConfig(
            ust_frequency=ust_frequency,
            quarterly_payment_amount=user_settings.quarterly_est_amount,
            is_freiberufler=user_settings.is_freiberufler,
            has_eu_clients=user_settings.has_eu_clients,
        )

        if year < today.year:
            # For past years, generate all deadlines and recalculate days from today
            reference_date = date(year, 1, 1)
            calc = DeadlineCalculator(reference_date=reference_date)
            deadlines = calc.get_upcoming_deadlines(year, config, lookahead_days=365)
            # Recalculate days_until from today (will be negative for past deadlines)
            for d in deadlines:
                d.days_until = (d.date - today).days
        else:
            # For current/future years, use normal calculation from today
            calc = DeadlineCalculator()
            deadlines = calc.get_upcoming_deadlines(year, config, lookahead_days)

        # Mark completed deadlines
        completed = await self.get_completed_deadlines()
        for d in deadlines:
            if d.deadline_id and d.deadline_id in completed:
                d.completed = True

        return deadlines

    async def get_quarterly_payments(
        self,
        year: int | None = None,
    ) -> list[QuarterlyPayment]:
        """Get quarterly tax payment schedule.

        Args:
            year: Tax year (default: current year)

        Returns:
            List of QuarterlyPayment objects
        """
        year = year or date.today().year

        # Get configured quarterly amount from user settings
        from src.web.routes.settings import load_settings
        user_settings = load_settings()
        amount = user_settings.quarterly_est_amount

        # Get paid quarters from settings
        paid_quarters_str = await self.settings_repo.get(f"quarterly_paid_{year}", "")
        paid_quarters = set()
        if paid_quarters_str:
            paid_quarters = {int(q) for q in paid_quarters_str.split(",") if q.strip()}

        calc = DeadlineCalculator()
        payments = calc.get_quarterly_payments(year, amount)

        # Update paid status from stored settings
        for payment in payments:
            payment.paid = payment.quarter in paid_quarters

        return payments

    async def toggle_quarterly_payment(
        self,
        year: int,
        quarter: int,
    ) -> bool:
        """Toggle the paid status of a quarterly payment.

        Args:
            year: Tax year
            quarter: Quarter number (1-4)

        Returns:
            New paid status (True if now paid, False if now unpaid)
        """
        # Get current paid quarters
        paid_quarters_str = await self.settings_repo.get(f"quarterly_paid_{year}", "")
        paid_quarters = set()
        if paid_quarters_str:
            paid_quarters = {int(q) for q in paid_quarters_str.split(",") if q.strip()}

        # Toggle the quarter
        if quarter in paid_quarters:
            paid_quarters.remove(quarter)
            new_status = False
        else:
            paid_quarters.add(quarter)
            new_status = True

        # Save updated paid quarters
        new_value = ",".join(str(q) for q in sorted(paid_quarters))
        await self.settings_repo.set(f"quarterly_paid_{year}", new_value)

        return new_status

    async def toggle_deadline_completion(
        self,
        deadline_id: str,
    ) -> bool:
        """Toggle the completion status of a tax deadline.

        Args:
            deadline_id: Unique deadline identifier (e.g., "ust_2026_01")

        Returns:
            New completion status (True if now completed, False if now pending)
        """
        # Get current completed deadlines
        completed_str = await self.settings_repo.get("completed_deadlines", "")
        completed = set()
        if completed_str:
            completed = {d.strip() for d in completed_str.split(",") if d.strip()}

        # Toggle the deadline
        if deadline_id in completed:
            completed.remove(deadline_id)
            new_status = False
        else:
            completed.add(deadline_id)
            new_status = True

        # Save updated completed deadlines
        new_value = ",".join(sorted(completed))
        await self.settings_repo.set("completed_deadlines", new_value)

        return new_status

    async def get_completed_deadlines(self) -> set[str]:
        """Get set of completed deadline IDs.

        Returns:
            Set of deadline IDs that have been marked as completed
        """
        completed_str = await self.settings_repo.get("completed_deadlines", "")
        if completed_str:
            return {d.strip() for d in completed_str.split(",") if d.strip()}
        return set()

    async def get_income_prediction(
        self,
        year: int | None = None,
        forecast_months: int = 6,
    ) -> dict:
        """Get income prediction with Gaussian Process regression and uncertainty.

        Implements a proper GP-style prediction with RBF kernel behavior,
        smooth mean function, and growing uncertainty bands that model
        epistemic uncertainty for future predictions.

        Shows current year data plus next `forecast_months` months.

        Args:
            year: Tax year (default: current year)
            forecast_months: Number of months to forecast beyond current (default: 6)

        Returns:
            Dictionary with labels, actual, predicted, upper_bound, lower_bound
        """
        import math

        from src.web.routes.settings import get_activity_start_date

        year = year or date.today().year
        today = date.today()
        current_month = today.month if year == today.year else 12
        activity_start = get_activity_start_date()

        # Month labels - current year + forecast months into next year
        month_abbr = [
            "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
            "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"
        ]

        # Calculate total months to display (current year + forecast)
        if year == today.year:
            # Show from Jan to current_month + forecast_months
            total_display_months = min(current_month + forecast_months, 18)
        else:
            # For past years, show 12 months + some forecast
            total_display_months = 12 + forecast_months

        # Build extended labels
        labels = []
        for i in range(total_display_months):
            month_in_year = i % 12
            year_offset = i // 12
            display_year = year + year_offset
            if year_offset > 0:
                labels.append(f"{month_abbr[month_in_year]} '{str(display_year)[-2:]}")
            else:
                labels.append(month_abbr[month_in_year])

        # Get actual monthly revenue from database (current year)
        monthly_data = await self.invoice_repo.get_monthly_revenue(year, activity_start)
        monthly_dict = {month: float(amount) for month, amount in monthly_data}

        # Also get next year data if forecasting into it
        next_year_data = {}
        if total_display_months > 12:
            next_year_monthly = await self.invoice_repo.get_monthly_revenue(year + 1, activity_start)
            next_year_data = {month: float(amount) for month, amount in next_year_monthly}

        # Build arrays and collect known data points
        actual = []
        known_indices = []  # Global index (0-based from Jan of year)
        known_values = []

        for i in range(total_display_months):
            month_num = (i % 12) + 1  # 1-12
            data_year = year + (i // 12)

            # Determine if this month has actual data
            is_past = (
                (data_year < today.year) or
                (data_year == today.year and month_num < today.month)
            )
            is_current = (data_year == today.year and month_num == today.month)

            if is_past or is_current:
                if data_year == year:
                    value = monthly_dict.get(month_num, 0.0)
                else:
                    value = next_year_data.get(month_num, 0.0)
                actual.append(value)
                if value > 0:
                    known_indices.append(i)
                    known_values.append(value)
            else:
                actual.append(None)

        # GP-style prediction with RBF kernel behavior
        predicted = []
        upper_bound = []
        lower_bound = []

        n_known = len(known_values)

        if n_known >= 2:
            # Compute mean and variance of known data
            mean_val = sum(known_values) / n_known
            var_val = sum((v - mean_val) ** 2 for v in known_values) / max(n_known - 1, 1)
            std_val = math.sqrt(var_val) if var_val > 0 else mean_val * 0.2

            # RBF kernel length scale (controls smoothness)
            length_scale = 3.0  # months
            signal_variance = var_val if var_val > 0 else (mean_val * 0.3) ** 2
            noise_variance = (std_val * 0.1) ** 2  # Observation noise

            # GP prediction for each point
            for i in range(total_display_months):
                # Compute kernel weights (RBF kernel)
                weights = []
                total_weight = 0.0
                for j, idx in enumerate(known_indices):
                    dist = abs(i - idx)
                    # RBF: k(x, x') = σ² * exp(-d²/2l²)
                    w = math.exp(-0.5 * (dist / length_scale) ** 2)
                    weights.append((w, known_values[j]))
                    total_weight += w

                if total_weight > 0:
                    # Weighted mean prediction (GP posterior mean approximation)
                    pred = sum(w * v for w, v in weights) / total_weight

                    # Add slight trend component from linear regression
                    # (helps extrapolation be more sensible)
                    sum_x = sum(known_indices)
                    sum_y = sum(known_values)
                    sum_xy = sum(x * y for x, y in zip(known_indices, known_values))
                    sum_xx = sum(x * x for x in known_indices)
                    denom = n_known * sum_xx - sum_x * sum_x
                    if denom != 0:
                        slope = (n_known * sum_xy - sum_x * sum_y) / denom
                        intercept = (sum_y - slope * sum_x) / n_known
                        trend_pred = intercept + slope * i
                        # Blend: more weight to GP near data, more to trend far away
                        blend_factor = min(total_weight, 1.0)
                        pred = blend_factor * pred + (1 - blend_factor) * trend_pred
                else:
                    pred = mean_val

                pred = max(pred, 0)
                predicted.append(round(pred, 2))

                # Compute uncertainty (GP posterior variance approximation)
                # Uncertainty is low near known points, grows with distance
                min_dist = min(abs(i - idx) for idx in known_indices)

                # Base uncertainty from data variance
                base_std = max(std_val, mean_val * 0.1, 500)

                # GP-style uncertainty: grows with distance, saturates at prior
                # σ²_posterior ≈ σ²_prior * (1 - k(x, x_nearest)² / (k + noise))
                nearest_kernel = math.exp(-0.5 * (min_dist / length_scale) ** 2)
                uncertainty_factor = math.sqrt(1 - nearest_kernel ** 2 * 0.8)

                # Additional growth for far future (epistemic uncertainty)
                last_known = max(known_indices)
                if i > last_known:
                    future_dist = i - last_known
                    # Uncertainty grows ~sqrt(distance) beyond last data
                    extra_growth = 1 + 0.15 * math.sqrt(future_dist)
                    uncertainty_factor *= extra_growth

                uncertainty = base_std * max(uncertainty_factor, 0.3)

                # 95% confidence interval
                upper_bound.append(round(pred + 1.96 * uncertainty, 2))
                lower_bound.append(round(max(0, pred - 1.96 * uncertainty), 2))

        elif n_known == 1:
            # Single data point - constant mean with growing uncertainty
            baseline = known_values[0]
            base_std = max(baseline * 0.2, 500)

            for i in range(total_display_months):
                predicted.append(round(baseline, 2))
                dist = abs(i - known_indices[0])
                # Uncertainty grows with distance from single point
                uncertainty = base_std * (1 + 0.2 * math.sqrt(dist))
                upper_bound.append(round(baseline + 1.96 * uncertainty, 2))
                lower_bound.append(round(max(0, baseline - 1.96 * uncertainty), 2))
        else:
            # No data
            for _ in range(total_display_months):
                predicted.append(0)
                upper_bound.append(0)
                lower_bound.append(0)

        # Find transition index (where actual data ends)
        transition_idx = len([a for a in actual if a is not None]) - 1

        return {
            "labels": labels,
            "actual": actual,
            "predicted": predicted,
            "upper_bound": upper_bound,
            "lower_bound": lower_bound,
            "year": year,
            "has_data": n_known > 0,
            "transition_index": transition_idx,
            "forecast_start_label": labels[transition_idx + 1] if transition_idx + 1 < len(labels) else None,
        }

    def _calculate_change(
        self,
        current: Decimal,
        previous: Decimal,
    ) -> Decimal:
        """Calculate percentage change between periods.

        Args:
            current: Current period value
            previous: Previous period value

        Returns:
            Percentage change (e.g., 15.2 for +15.2%)
        """
        if previous == 0:
            if current > 0:
                return Decimal("100")
            return Decimal("0")

        change = ((current - previous) / previous * 100).quantize(Decimal("0.1"))
        return change

    # =========================================================================
    # Tax Optimization Widgets
    # =========================================================================

    async def get_afa_summary(self, year: int | None = None) -> dict:
        """Get AfA (depreciation) summary for dashboard widget.

        Args:
            year: Tax year (default: current year)

        Returns:
            Dict with total_depreciation, active_assets, expiring_soon
        """
        year = year or date.today().year

        # Get total depreciation for year
        total_depreciation = await self.asset_repo.get_annual_depreciation(year)

        # Get all active assets
        active_assets = await self.asset_repo.get_all(active_only=True)

        # Find assets expiring this year (book_value will be 0 after this year)
        expiring_assets = []
        for asset in active_assets:
            # Calculate remaining years based on purchase date and useful life
            purchase_year = asset.purchase_date.year
            end_year = purchase_year + asset.useful_life_years
            if end_year == year:
                expiring_assets.append(asset)

        return {
            "total_depreciation": total_depreciation,
            "active_asset_count": len(active_assets),
            "active_assets": active_assets[:5],  # Top 5 for display
            "expiring_count": len(expiring_assets),
            "expiring_assets": expiring_assets,
        }

    async def get_travel_summary(self, year: int | None = None) -> dict:
        """Get travel expense summary for dashboard widget.

        Args:
            year: Tax year (default: current year)

        Returns:
            Dict with per_diem_total, km_total, total_deduction, trip_count
        """
        year = year or date.today().year

        # Get annual totals from repository
        totals = await self.travel_repo.get_annual_totals(year)

        # Get trip count
        trips = await self.travel_repo.get_all(year=year)

        return {
            "per_diem_total": totals["per_diem_total"],
            "km_total": totals["km_total"],
            "total_deduction": totals["total_deduction"],
            "trip_count": len(trips),
        }

    async def get_gift_warnings(self, year: int | None = None) -> dict:
        """Get gift limit warnings for dashboard widget.

        Args:
            year: Tax year (default: current year)

        Returns:
            Dict with at_risk_recipients, over_limit_count, total_deductible
        """
        from src.core.models import GIFT_LIMIT_PER_RECIPIENT

        year = year or date.today().year

        # Get recipient summaries
        summaries = await self.gift_repo.get_recipient_summaries(year)

        # Categorize recipients
        at_risk = []  # 40-50 EUR (approaching limit)
        over_limit = []  # > 50 EUR (non-deductible)
        total_deductible = Decimal("0")
        total_non_deductible = Decimal("0")

        threshold = GIFT_LIMIT_PER_RECIPIENT * Decimal("0.8")  # 80% = 40 EUR

        for summary in summaries:
            if summary.is_over_limit:
                over_limit.append(summary)
                total_non_deductible += summary.total_amount
            else:
                total_deductible += summary.total_amount
                if summary.total_amount >= threshold:
                    at_risk.append(summary)

        return {
            "at_risk_recipients": at_risk,
            "at_risk_count": len(at_risk),
            "over_limit_recipients": over_limit,
            "over_limit_count": len(over_limit),
            "total_deductible": total_deductible,
            "total_non_deductible": total_non_deductible,
            "recipient_count": len(summaries),
        }

    async def get_homeoffice_summary(self, year: int | None = None) -> dict:
        """Get home office summary for dashboard widget.

        Args:
            year: Tax year (default: current year)

        Returns:
            Dict with days_used, max_days, deduction_amount, percentage
        """
        from src.core.models import (
            HOME_OFFICE_DAILY_RATE,
            HOME_OFFICE_MAX_DAYS,
            HomeOfficeType,
        )

        year = year or date.today().year

        # Get day count
        days_used = await self.homeoffice_repo.get_day_count(year)

        # Get settings to determine method
        settings = await self.homeoffice_repo.get_settings(year)

        # Calculate deduction based on method
        if settings and settings.method_type == HomeOfficeType.ARBEITSZIMMER:
            # Full room deduction - calculate from settings
            if settings.room_sqm and settings.total_sqm and settings.monthly_rent:
                room_ratio = settings.room_sqm / settings.total_sqm
                monthly_costs = settings.monthly_rent + (settings.monthly_utilities or Decimal("0"))
                annual_deduction = (monthly_costs * room_ratio * 12).quantize(Decimal("0.01"))
            else:
                # Use flat rate fallback: 1,260 EUR
                annual_deduction = Decimal("1260.00")
            max_days = None  # No day limit for Arbeitszimmer
            percentage = None
        else:
            # Pauschale method: 6 EUR/day, max 210 days
            capped_days = min(days_used, HOME_OFFICE_MAX_DAYS)
            annual_deduction = (HOME_OFFICE_DAILY_RATE * capped_days).quantize(Decimal("0.01"))
            max_days = HOME_OFFICE_MAX_DAYS
            percentage = (
                (Decimal(days_used) / Decimal(HOME_OFFICE_MAX_DAYS) * 100).quantize(Decimal("0.1"))
                if days_used > 0 else Decimal("0")
            )

        return {
            "days_used": days_used,
            "max_days": max_days,
            "deduction_amount": annual_deduction,
            "percentage": percentage,
            "method": settings.method_type.value if settings else "pauschale",
            "is_arbeitszimmer": settings.method_type == HomeOfficeType.ARBEITSZIMMER if settings else False,
        }


# FastAPI dependency
async def get_dashboard_service() -> DashboardService:
    """FastAPI dependency for DashboardService."""
    return DashboardService()
