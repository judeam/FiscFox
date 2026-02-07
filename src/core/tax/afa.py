"""Asset depreciation calculator (AfA - Absetzung für Abnutzung).

Implements German depreciation rules:
- GWG (Geringwertige Wirtschaftsgüter) - § 6 Abs. 2 EStG
- Sammelposten (Pool) - § 6 Abs. 2a EStG
- Linear depreciation - § 7 Abs. 1 EStG
- Degressive depreciation - § 7 Abs. 2 EStG (Wachstumschancengesetz 2024)
- Digital AfA - BMF 2021-02-26 (1-year for IT assets)

All monetary values use Decimal for precision.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.core.models import (
    AFA_USEFUL_LIFE,
    Asset,
    AssetCategory,
    AssetInput,
    DepreciationMethod,
    DepreciationRecord,
)

# Threshold values (net amounts)
TRIVIAL_THRESHOLD = Decimal("250")      # Direct expense, not tracked
GWG_THRESHOLD = Decimal("800")          # Immediate write-off (§ 6 Abs. 2 EStG)
POOL_THRESHOLD = Decimal("1000")        # Pool option ceiling (§ 6 Abs. 2a EStG)

# Pool depreciation: 5 years at 20% per year
POOL_YEARS = 5
POOL_RATE = Decimal("0.20")

# Degressive depreciation limits (Wachstumschancengesetz 2024)
DEGRESSIVE_MULTIPLIER = Decimal("2.5")  # Up to 2.5x linear rate
DEGRESSIVE_MAX_RATE = Decimal("0.25")   # Max 25%

# Degressive eligibility window (Wachstumschancengesetz)
DEGRESSIVE_START_DATE = date(2024, 4, 1)
DEGRESSIVE_END_DATE = date(2024, 12, 31)


@dataclass
class DepreciationSuggestion:
    """Suggestion for depreciation method with explanation."""
    method: DepreciationMethod
    useful_life_years: int
    first_year_depreciation: Decimal
    explanation: str
    alternative_method: DepreciationMethod | None = None
    alternative_explanation: str = ""


class AfaCalculator:
    """Depreciation calculator for German tax law.

    Usage:
        calculator = AfaCalculator()

        # Get method suggestion for new asset
        suggestion = calculator.suggest_method(
            cost=Decimal("750"),
            category=AssetCategory.OFFICE
        )

        # Calculate annual depreciation
        amount = calculator.calculate_annual(
            asset=asset,
            year=2026
        )

        # Generate full depreciation schedule
        schedule = calculator.generate_schedule(asset)
    """

    def suggest_method(
        self,
        cost: Decimal,
        category: AssetCategory,
        purchase_date: date | None = None,
    ) -> DepreciationSuggestion:
        """Suggest optimal depreciation method based on asset value and type.

        Decision tree:
        1. < 250 EUR: Trivial - book as direct expense
        2. 250-800 EUR: GWG immediate write-off
        3. IT assets (any value): Digital AfA (1 year)
        4. 250-1000 EUR: Compare Pool (5 years) vs Linear
        5. > 1000 EUR: Linear (or Degressive if eligible)

        Args:
            cost: Net acquisition cost
            category: Asset category
            purchase_date: For degressive eligibility check

        Returns:
            DepreciationSuggestion with recommended method and explanation
        """
        useful_life = AFA_USEFUL_LIFE.get(category, 10)

        # Trivial expense (not tracked as asset)
        if cost < TRIVIAL_THRESHOLD:
            return DepreciationSuggestion(
                method=DepreciationMethod.IMMEDIATE,
                useful_life_years=1,
                first_year_depreciation=cost,
                explanation=(
                    f"Betrag unter {TRIVIAL_THRESHOLD} EUR: "
                    "Sofort als Betriebsausgabe absetzbar (kein Anlagegut)"
                ),
            )

        # GWG immediate write-off (250-800 EUR)
        if cost <= GWG_THRESHOLD:
            return DepreciationSuggestion(
                method=DepreciationMethod.IMMEDIATE,
                useful_life_years=1,
                first_year_depreciation=cost,
                explanation=(
                    f"GWG bis {GWG_THRESHOLD} EUR: "
                    "Sofortabzug im Jahr der Anschaffung (§ 6 Abs. 2 EStG)"
                ),
                alternative_method=DepreciationMethod.POOL if cost > TRIVIAL_THRESHOLD else None,
                alternative_explanation=(
                    "Alternative: Sammelposten (5 Jahre, 20% p.a.)"
                    if cost > TRIVIAL_THRESHOLD else ""
                ),
            )

        # Digital AfA for IT assets (any value)
        if category in (AssetCategory.COMPUTER, AssetCategory.SOFTWARE):
            return DepreciationSuggestion(
                method=DepreciationMethod.DIGITAL,
                useful_life_years=1,
                first_year_depreciation=cost,
                explanation=(
                    "Digital-AfA: 1-Jahres-Abschreibung für IT-Geräte "
                    "(BMF 2021-02-26)"
                ),
            )

        # Pool option for 250-1000 EUR
        if cost <= POOL_THRESHOLD:
            pool_annual = (cost * POOL_RATE).quantize(Decimal("0.01"))
            linear_annual = (cost / Decimal(useful_life)).quantize(Decimal("0.01"))

            # Compare: Pool (5 years) vs Linear (useful life)
            if useful_life > POOL_YEARS:
                return DepreciationSuggestion(
                    method=DepreciationMethod.POOL,
                    useful_life_years=POOL_YEARS,
                    first_year_depreciation=pool_annual,
                    explanation=(
                        f"Sammelposten: 5 Jahre (20% p.a.) günstiger als "
                        f"lineare AfA über {useful_life} Jahre (§ 6 Abs. 2a EStG)"
                    ),
                    alternative_method=DepreciationMethod.LINEAR,
                    alternative_explanation=f"Linear: {linear_annual} EUR/Jahr über {useful_life} Jahre",
                )
            else:
                return DepreciationSuggestion(
                    method=DepreciationMethod.LINEAR,
                    useful_life_years=useful_life,
                    first_year_depreciation=linear_annual,
                    explanation=(
                        f"Lineare AfA über {useful_life} Jahre günstiger als "
                        "Sammelposten (5 Jahre)"
                    ),
                    alternative_method=DepreciationMethod.POOL,
                    alternative_explanation="Alternative: Sammelposten (5 Jahre, 20% p.a.)",
                )

        # Standard assets > 1000 EUR
        linear_annual = (cost / Decimal(useful_life)).quantize(Decimal("0.01"))

        # Check degressive eligibility
        if purchase_date and self._is_degressive_eligible(purchase_date):
            degressive_rate = min(
                (Decimal("1") / Decimal(useful_life)) * DEGRESSIVE_MULTIPLIER,
                DEGRESSIVE_MAX_RATE,
            )
            degressive_annual = (cost * degressive_rate).quantize(Decimal("0.01"))

            return DepreciationSuggestion(
                method=DepreciationMethod.DEGRESSIVE,
                useful_life_years=useful_life,
                first_year_depreciation=degressive_annual,
                explanation=(
                    f"Degressive AfA: {degressive_rate * 100:.1f}% vom Restwert "
                    "(Wachstumschancengesetz 2024)"
                ),
                alternative_method=DepreciationMethod.LINEAR,
                alternative_explanation=f"Linear: {linear_annual} EUR/Jahr über {useful_life} Jahre",
            )

        return DepreciationSuggestion(
            method=DepreciationMethod.LINEAR,
            useful_life_years=useful_life,
            first_year_depreciation=linear_annual,
            explanation=(
                f"Lineare AfA über {useful_life} Jahre "
                f"({linear_annual} EUR/Jahr, § 7 Abs. 1 EStG)"
            ),
        )

    def _is_degressive_eligible(self, purchase_date: date) -> bool:
        """Check if asset qualifies for degressive depreciation.

        Wachstumschancengesetz allows degressive AfA for movable assets
        acquired between April 1, 2024 and December 31, 2024.
        """
        return DEGRESSIVE_START_DATE <= purchase_date <= DEGRESSIVE_END_DATE

    def calculate_annual(
        self,
        asset: Asset,
        year: int,
        months: int = 12,
    ) -> Decimal:
        """Calculate depreciation amount for a specific year.

        Handles:
        - Pro-rata temporis for partial years
        - Method-specific calculations
        - Switchover from degressive to linear

        Args:
            asset: Asset with depreciation method set
            year: Tax year
            months: Months of ownership in this year (1-12)

        Returns:
            Depreciation amount for the year
        """
        if asset.depreciation_complete:
            return Decimal("0")

        if asset.current_book_value <= Decimal("0"):
            return Decimal("0")

        method = asset.depreciation_method
        cost = asset.acquisition_cost
        book_value = asset.current_book_value
        useful_life = asset.useful_life_years

        # Pro-rata factor
        pro_rata = Decimal(months) / Decimal("12")

        if method == DepreciationMethod.IMMEDIATE:
            # Full amount in first year
            return cost

        if method == DepreciationMethod.DIGITAL:
            # Full amount in first year (no pro-rata for Digital AfA)
            return cost

        if method == DepreciationMethod.POOL:
            # 20% per year, no pro-rata
            return (cost * POOL_RATE).quantize(Decimal("0.01"))

        if method == DepreciationMethod.LINEAR:
            annual = (cost / Decimal(useful_life)).quantize(Decimal("0.01"))
            # Apply pro-rata for partial year
            return (annual * pro_rata).quantize(Decimal("0.01"))

        if method == DepreciationMethod.DEGRESSIVE:
            # Calculate degressive rate
            linear_rate = Decimal("1") / Decimal(useful_life)
            degressive_rate = min(linear_rate * DEGRESSIVE_MULTIPLIER, DEGRESSIVE_MAX_RATE)

            degressive_amount = (book_value * degressive_rate).quantize(Decimal("0.01"))
            linear_amount = (cost / Decimal(useful_life)).quantize(Decimal("0.01"))

            # Switch to linear when linear becomes more advantageous
            if linear_amount > degressive_amount:
                return (linear_amount * pro_rata).quantize(Decimal("0.01"))

            return (degressive_amount * pro_rata).quantize(Decimal("0.01"))

        return Decimal("0")

    def generate_schedule(
        self,
        asset: AssetInput,
        start_year: int | None = None,
    ) -> list[DepreciationRecord]:
        """Generate full depreciation schedule for an asset.

        Args:
            asset: Asset input (method will be suggested if not set)
            start_year: First depreciation year (defaults to purchase year)

        Returns:
            List of annual depreciation records
        """
        if start_year is None:
            start_year = asset.purchase_date.year

        # Get suggestion if method not set
        method = asset.depreciation_method
        if method is None:
            suggestion = self.suggest_method(
                asset.acquisition_cost,
                asset.category,
                asset.purchase_date,
            )
            method = suggestion.method
            useful_life = suggestion.useful_life_years
        else:
            useful_life = asset.useful_life_years

        records: list[DepreciationRecord] = []
        book_value = asset.acquisition_cost
        total_depreciated = Decimal("0")

        # Calculate months in first year (purchase month to December)
        first_year_months = 12 - asset.purchase_date.month + 1

        # Immediate/Digital: single year
        if method in (DepreciationMethod.IMMEDIATE, DepreciationMethod.DIGITAL):
            records.append(DepreciationRecord(
                id=0,  # Will be assigned by DB
                asset_id=0,
                year=start_year,
                depreciation_amount=asset.acquisition_cost,
                book_value_start=asset.acquisition_cost,
                book_value_end=Decimal("0"),
                method_applied=method,
                months_applicable=first_year_months,
                notes="Sofortabzug" if method == DepreciationMethod.IMMEDIATE else "Digital-AfA",
            ))
            return records

        # Pool: 5 years at 20%
        if method == DepreciationMethod.POOL:
            for year_offset in range(POOL_YEARS):
                year = start_year + year_offset
                annual = (asset.acquisition_cost * POOL_RATE).quantize(Decimal("0.01"))
                new_book_value = (book_value - annual).quantize(Decimal("0.01"))

                records.append(DepreciationRecord(
                    id=0,
                    asset_id=0,
                    year=year,
                    depreciation_amount=annual,
                    book_value_start=book_value,
                    book_value_end=max(new_book_value, Decimal("0")),
                    method_applied=DepreciationMethod.POOL,
                    months_applicable=12 if year_offset > 0 else first_year_months,
                    notes=f"Sammelposten Jahr {year_offset + 1}/5",
                ))
                book_value = new_book_value

            return records

        # Linear/Degressive: full schedule
        year = start_year
        while book_value > Decimal("0.01"):
            months = first_year_months if year == start_year else 12

            if method == DepreciationMethod.LINEAR:
                annual = (asset.acquisition_cost / Decimal(useful_life)).quantize(Decimal("0.01"))
                pro_rata_annual = (annual * Decimal(months) / Decimal("12")).quantize(Decimal("0.01"))
            else:  # DEGRESSIVE
                linear_rate = Decimal("1") / Decimal(useful_life)
                degressive_rate = min(linear_rate * DEGRESSIVE_MULTIPLIER, DEGRESSIVE_MAX_RATE)

                degressive_amount = (book_value * degressive_rate).quantize(Decimal("0.01"))
                linear_amount = (asset.acquisition_cost / Decimal(useful_life)).quantize(Decimal("0.01"))

                # Switch to linear when more advantageous
                if linear_amount > degressive_amount:
                    pro_rata_annual = (linear_amount * Decimal(months) / Decimal("12")).quantize(Decimal("0.01"))
                    method = DepreciationMethod.LINEAR  # Track switchover
                else:
                    pro_rata_annual = (degressive_amount * Decimal(months) / Decimal("12")).quantize(Decimal("0.01"))

            # Don't depreciate below zero
            pro_rata_annual = min(pro_rata_annual, book_value)

            new_book_value = (book_value - pro_rata_annual).quantize(Decimal("0.01"))

            records.append(DepreciationRecord(
                id=0,
                asset_id=0,
                year=year,
                depreciation_amount=pro_rata_annual,
                book_value_start=book_value,
                book_value_end=new_book_value,
                method_applied=method,
                months_applicable=months,
            ))

            book_value = new_book_value
            total_depreciated += pro_rata_annual
            year += 1

            # Safety limit
            if year > start_year + useful_life + 5:
                break

        return records

    def calculate_book_value(
        self,
        acquisition_cost: Decimal,
        total_depreciated: Decimal,
    ) -> Decimal:
        """Calculate current book value (Restbuchwert).

        Args:
            acquisition_cost: Original net purchase price
            total_depreciated: Sum of all depreciation to date

        Returns:
            Current book value (never negative)
        """
        return max(
            (acquisition_cost - total_depreciated).quantize(Decimal("0.01")),
            Decimal("0"),
        )

    def calculate_disposal_gain(
        self,
        book_value: Decimal,
        disposal_amount: Decimal,
    ) -> Decimal:
        """Calculate gain/loss on asset disposal.

        Positive = taxable gain
        Negative = deductible loss

        Args:
            book_value: Current book value at disposal
            disposal_amount: Sale price

        Returns:
            Gain (positive) or loss (negative)
        """
        return (disposal_amount - book_value).quantize(Decimal("0.01"))


# Module-level calculator instance
afa_calculator = AfaCalculator()
