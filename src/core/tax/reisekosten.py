"""Travel expense calculator (Reisekosten).

Implements German travel expense deductions:
- Per diem (Verpflegungsmehraufwand) - § 9 Abs. 4a EStG
- Km allowance (Entfernungspauschale) - § 9 Abs. 1 Nr. 4 EStG
- Meal reductions for provided meals
- Foreign per diem rates (BMF annual publication)

All monetary values use Decimal for precision.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.core.models import (
    KM_RATE_BEYOND_20,
    KM_RATE_FIRST_20,
    MEAL_REDUCTION_RATES,
    PER_DIEM_RATES_DOMESTIC,
    PER_DIEM_RATES_FOREIGN,
    TravelExpense,
    TravelExpenseInput,
)

# Extended km threshold
KM_THRESHOLD = Decimal("20")

# Minimum absence for per diem (hours)
MIN_ABSENCE_HOURS = Decimal("8")


@dataclass
class PerDiemResult:
    """Result of per diem calculation."""
    base_rate: Decimal           # Rate before meal reductions
    meal_reduction: Decimal      # Total reduction for provided meals
    final_amount: Decimal        # Net per diem after reductions
    rate_type: str               # "8+", "24", or "travel_day"
    country: str                 # Country code


@dataclass
class KmAllowanceResult:
    """Result of km allowance calculation."""
    total_km: Decimal
    rate_applied: Decimal        # Weighted average rate
    deduction: Decimal           # Total km deduction
    breakdown: str               # Explanation of calculation


@dataclass
class TravelDeductionResult:
    """Complete travel expense deduction result."""
    per_diem: PerDiemResult
    km_allowance: KmAllowanceResult
    total_deduction: Decimal
    notes: list[str]


class ReisekostenCalculator:
    """Travel expense calculator for German tax law.

    Usage:
        calculator = ReisekostenCalculator()

        # Calculate per diem for domestic trip
        per_diem = calculator.calculate_per_diem(
            absence_hours=Decimal("10"),
            country_code="DE",
            breakfast_provided=True
        )

        # Calculate km allowance
        km = calculator.calculate_km_allowance(Decimal("150"))

        # Calculate complete deduction
        result = calculator.calculate_travel_deduction(travel_input)
    """

    def calculate_per_diem(
        self,
        absence_hours: Decimal,
        country_code: str = "DE",
        is_travel_day: bool = False,
        is_overnight: bool = False,
        breakfast_provided: bool = False,
        lunch_provided: bool = False,
        dinner_provided: bool = False,
    ) -> PerDiemResult:
        """Calculate per diem (Verpflegungsmehraufwand).

        Rates for 2024/2025:
        - < 8 hours: 0 EUR
        - > 8 hours: 14 EUR (domestic)
        - 24 hours: 28 EUR (domestic)
        - Travel day: 14 EUR (arrival/departure)

        Meal reductions (from full 24h rate):
        - Breakfast: -20% (5.60 EUR)
        - Lunch: -40% (11.20 EUR)
        - Dinner: -40% (11.20 EUR)

        Args:
            absence_hours: Total hours absent from regular workplace
            country_code: ISO country code for foreign rates
            is_travel_day: True if this is arrival/departure day
            is_overnight: True if overnight stay
            breakfast_provided: True if breakfast included
            lunch_provided: True if lunch included
            dinner_provided: True if dinner included

        Returns:
            PerDiemResult with base rate, reductions, and final amount
        """
        # Determine rate type
        if is_travel_day:
            rate_type = "travel_day"
        elif is_overnight or absence_hours >= Decimal("24"):
            rate_type = "24"
        elif absence_hours >= MIN_ABSENCE_HOURS:
            rate_type = "8+"
        else:
            # No per diem for < 8 hours
            return PerDiemResult(
                base_rate=Decimal("0"),
                meal_reduction=Decimal("0"),
                final_amount=Decimal("0"),
                rate_type="none",
                country=country_code,
            )

        # Get base rate for country
        if country_code == "DE":
            base_rate = PER_DIEM_RATES_DOMESTIC.get(rate_type, Decimal("0"))
            full_day_rate = PER_DIEM_RATES_DOMESTIC["24"]
        else:
            rates = PER_DIEM_RATES_FOREIGN.get(country_code, PER_DIEM_RATES_DOMESTIC)
            base_rate = rates.get(rate_type, rates.get("8+", Decimal("14")))
            full_day_rate = rates.get("24", Decimal("28"))

        # Calculate meal reductions (always from full day rate)
        meal_reduction = Decimal("0")
        if breakfast_provided:
            meal_reduction += (full_day_rate * MEAL_REDUCTION_RATES["breakfast"]).quantize(Decimal("0.01"))
        if lunch_provided:
            meal_reduction += (full_day_rate * MEAL_REDUCTION_RATES["lunch"]).quantize(Decimal("0.01"))
        if dinner_provided:
            meal_reduction += (full_day_rate * MEAL_REDUCTION_RATES["dinner"]).quantize(Decimal("0.01"))

        # Final amount (never negative)
        final_amount = max(base_rate - meal_reduction, Decimal("0"))

        return PerDiemResult(
            base_rate=base_rate,
            meal_reduction=meal_reduction,
            final_amount=final_amount.quantize(Decimal("0.01")),
            rate_type=rate_type,
            country=country_code,
        )

    def calculate_km_allowance(
        self,
        km_driven: Decimal,
        is_commute: bool = False,
    ) -> KmAllowanceResult:
        """Calculate km allowance (Entfernungspauschale).

        Rates (§ 9 Abs. 1 Nr. 4 EStG):
        - First 20 km: 0.30 EUR/km
        - Beyond 20 km: 0.38 EUR/km

        Note: For commutes (Entfernung Wohnung-Arbeitsstätte), only one-way
        distance is counted. For business trips, round-trip applies.

        Args:
            km_driven: Total kilometers driven
            is_commute: True if this is a regular commute (one-way only)

        Returns:
            KmAllowanceResult with calculation breakdown
        """
        if km_driven <= Decimal("0"):
            return KmAllowanceResult(
                total_km=Decimal("0"),
                rate_applied=Decimal("0"),
                deduction=Decimal("0"),
                breakdown="Keine Kilometer angegeben",
            )

        # For commutes, only count one-way distance
        effective_km = km_driven

        if effective_km <= KM_THRESHOLD:
            # All at lower rate
            deduction = (effective_km * KM_RATE_FIRST_20).quantize(Decimal("0.01"))
            breakdown = f"{effective_km} km x {KM_RATE_FIRST_20} EUR = {deduction} EUR"
            rate_applied = KM_RATE_FIRST_20
        else:
            # First 20 km at lower rate, rest at higher rate
            first_20 = (KM_THRESHOLD * KM_RATE_FIRST_20).quantize(Decimal("0.01"))
            beyond_20_km = effective_km - KM_THRESHOLD
            beyond_20 = (beyond_20_km * KM_RATE_BEYOND_20).quantize(Decimal("0.01"))
            deduction = first_20 + beyond_20

            # Weighted average rate
            rate_applied = (deduction / effective_km).quantize(Decimal("0.0001"))

            breakdown = (
                f"Erste 20 km: 20 x {KM_RATE_FIRST_20} EUR = {first_20} EUR, "
                f"weitere {beyond_20_km} km: {beyond_20_km} x {KM_RATE_BEYOND_20} EUR = {beyond_20} EUR"
            )

        return KmAllowanceResult(
            total_km=effective_km,
            rate_applied=rate_applied,
            deduction=deduction,
            breakdown=breakdown,
        )

    def calculate_travel_deduction(
        self,
        travel_input: TravelExpenseInput,
    ) -> TravelDeductionResult:
        """Calculate complete travel expense deduction.

        Combines per diem and km allowance calculations.

        Args:
            travel_input: Travel expense input data

        Returns:
            TravelDeductionResult with all calculated deductions
        """
        notes = []

        # Calculate per diem
        per_diem = self.calculate_per_diem(
            absence_hours=travel_input.absence_hours,
            country_code=travel_input.country_code,
            is_travel_day=travel_input.is_travel_day,
            is_overnight=travel_input.is_overnight,
            breakfast_provided=travel_input.breakfast_provided,
            lunch_provided=travel_input.lunch_provided,
            dinner_provided=travel_input.dinner_provided,
        )

        if per_diem.meal_reduction > Decimal("0"):
            notes.append(
                f"Kürzung für Mahlzeiten: -{per_diem.meal_reduction} EUR"
            )

        # Calculate km allowance
        km_allowance = self.calculate_km_allowance(travel_input.km_driven)

        if km_allowance.total_km > Decimal("0"):
            notes.append(km_allowance.breakdown)

        # Total deduction
        total = (per_diem.final_amount + km_allowance.deduction).quantize(Decimal("0.01"))

        return TravelDeductionResult(
            per_diem=per_diem,
            km_allowance=km_allowance,
            total_deduction=total,
            notes=notes,
        )

    def calculate_absence_hours(
        self,
        departure: datetime | str,
        return_time: datetime | str,
    ) -> Decimal:
        """Calculate absence hours from departure and return times.

        Args:
            departure: Departure datetime or HH:MM string
            return_time: Return datetime or HH:MM string

        Returns:
            Total absence in hours (Decimal)
        """
        if isinstance(departure, str):
            departure = datetime.strptime(departure, "%H:%M")
        if isinstance(return_time, str):
            return_time = datetime.strptime(return_time, "%H:%M")

        # Handle overnight trips (return time before departure)
        if return_time < departure:
            # Assume next day
            delta = (
                datetime.combine(date.min, return_time.time()) -
                datetime.combine(date.min, departure.time())
            )
            # Add 24 hours for next day
            hours = Decimal(str((delta.total_seconds() + 86400) / 3600))
        else:
            delta = return_time - departure
            hours = Decimal(str(delta.total_seconds() / 3600))

        return hours.quantize(Decimal("0.01"))

    def create_travel_expense(
        self,
        travel_input: TravelExpenseInput,
    ) -> TravelExpense:
        """Create a complete TravelExpense with all calculated fields.

        Args:
            travel_input: Input data from form

        Returns:
            TravelExpense with all deductions calculated
        """
        result = self.calculate_travel_deduction(travel_input)

        return TravelExpense(
            id=0,  # Will be assigned by DB
            date=travel_input.date,
            destination=travel_input.destination,
            purpose=travel_input.purpose,
            departure_time=travel_input.departure_time,
            return_time=travel_input.return_time,
            absence_hours=travel_input.absence_hours,
            is_overnight=travel_input.is_overnight,
            is_travel_day=travel_input.is_travel_day,
            km_driven=travel_input.km_driven,
            km_rate=result.km_allowance.rate_applied,
            km_deduction=result.km_allowance.deduction,
            country_code=travel_input.country_code,
            per_diem_rate=result.per_diem.base_rate,
            meal_reduction=result.per_diem.meal_reduction,
            per_diem_deduction=result.per_diem.final_amount,
            total_deduction=result.total_deduction,
            breakfast_provided=travel_input.breakfast_provided,
            lunch_provided=travel_input.lunch_provided,
            dinner_provided=travel_input.dinner_provided,
        )

    def get_foreign_rate(
        self,
        country_code: str,
        rate_type: str = "24",
    ) -> Decimal:
        """Get per diem rate for a foreign country.

        Args:
            country_code: ISO 2-letter country code
            rate_type: "8+" or "24"

        Returns:
            Per diem rate (Decimal)
        """
        rates = PER_DIEM_RATES_FOREIGN.get(country_code)
        if rates:
            return rates.get(rate_type, rates.get("8+", Decimal("14")))

        # Default to domestic rates if country not found
        return PER_DIEM_RATES_DOMESTIC.get(rate_type, Decimal("14"))

    def list_supported_countries(self) -> list[tuple[str, Decimal, Decimal]]:
        """List all supported countries with their per diem rates.

        Returns:
            List of (country_code, 8+ rate, 24h rate) tuples
        """
        countries = [("DE", PER_DIEM_RATES_DOMESTIC["8+"], PER_DIEM_RATES_DOMESTIC["24"])]

        for code, rates in sorted(PER_DIEM_RATES_FOREIGN.items()):
            countries.append((code, rates["8+"], rates["24"]))

        return countries


# Module-level calculator instance
reisekosten_calculator = ReisekostenCalculator()
