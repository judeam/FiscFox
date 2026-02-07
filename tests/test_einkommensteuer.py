"""Tests for German Income Tax Calculator (Einkommensteuer).

Tests verify the progressive tax formula per § 32a EStG.
"""
from decimal import Decimal

import pytest

from src.core.tax.einkommensteuer import (
    EinkommensteuerCalculator,
    calculate_einkommensteuer,
)


class TestEinkommensteuerCalculator:
    """Test suite for EinkommensteuerCalculator."""

    @pytest.fixture
    def calc(self) -> EinkommensteuerCalculator:
        """Create calculator for 2026."""
        return EinkommensteuerCalculator(2026)

    def test_zone0_no_tax_below_grundfreibetrag(self, calc: EinkommensteuerCalculator) -> None:
        """Income below Grundfreibetrag should have 0% tax."""
        result = calc.calculate(Decimal("10000"))
        assert result.einkommensteuer == Decimal("0")
        assert result.effective_rate == Decimal("0")
        assert result.marginal_rate == Decimal("0")

    def test_zone0_exactly_at_grundfreibetrag(self, calc: EinkommensteuerCalculator) -> None:
        """Income exactly at Grundfreibetrag should have 0% tax."""
        result = calc.calculate(calc.config.grundfreibetrag)
        assert result.einkommensteuer == Decimal("0")

    def test_zone1_progressive_tax(self, calc: EinkommensteuerCalculator) -> None:
        """Zone 1 should apply progressive tax from 14% to 24%."""
        # Just above Grundfreibetrag
        result = calc.calculate(calc.config.grundfreibetrag + Decimal("1000"))
        assert result.einkommensteuer > Decimal("0")
        # Marginal rate should be around 14% at start of zone 1
        assert result.marginal_rate > Decimal("14")
        assert result.marginal_rate < Decimal("24")

    def test_zone2_progressive_tax(self, calc: EinkommensteuerCalculator) -> None:
        """Zone 2 should apply progressive tax from 24% to 42%."""
        result = calc.calculate(Decimal("50000"))
        assert result.einkommensteuer > Decimal("0")
        assert result.marginal_rate > Decimal("24")
        assert result.marginal_rate < Decimal("42")

    def test_zone3_flat_42_percent(self, calc: EinkommensteuerCalculator) -> None:
        """Zone 3 should apply flat 42% marginal rate."""
        result = calc.calculate(Decimal("100000"))
        assert result.marginal_rate == Decimal("42.00")

    def test_zone4_reichensteuer_45_percent(self, calc: EinkommensteuerCalculator) -> None:
        """Zone 4 should apply 45% Reichensteuer."""
        result = calc.calculate(Decimal("300000"))
        assert result.marginal_rate == Decimal("45.00")

    def test_negative_income_treated_as_zero(self, calc: EinkommensteuerCalculator) -> None:
        """Negative income should be treated as 0."""
        result = calc.calculate(Decimal("-10000"))
        assert result.einkommensteuer == Decimal("0")
        assert result.zu_versteuerndes_einkommen == Decimal("0")

    def test_effective_rate_increases_with_income(self, calc: EinkommensteuerCalculator) -> None:
        """Effective rate should increase as income increases."""
        result_low = calc.calculate(Decimal("30000"))
        result_high = calc.calculate(Decimal("100000"))
        assert result_high.effective_rate > result_low.effective_rate

    def test_solidaritaetszuschlag_exempt_below_threshold(self, calc: EinkommensteuerCalculator) -> None:
        """Soli should be 0 below threshold."""
        # Low income should have no Soli
        result = calc.calculate(Decimal("30000"))
        assert result.solidaritaetszuschlag == Decimal("0")

    def test_solidaritaetszuschlag_applies_above_threshold(self, calc: EinkommensteuerCalculator) -> None:
        """Soli should apply above threshold."""
        # Very high income should have Soli
        result = calc.calculate(Decimal("500000"))
        assert result.solidaritaetszuschlag > Decimal("0")

    def test_total_tax_includes_soli(self, calc: EinkommensteuerCalculator) -> None:
        """Total tax should equal ESt + Soli."""
        result = calc.calculate(Decimal("500000"))
        assert result.total_tax == result.einkommensteuer + result.solidaritaetszuschlag

    def test_quarterly_payment_is_one_quarter(self, calc: EinkommensteuerCalculator) -> None:
        """Quarterly payment should be 1/4 of annual estimate."""
        annual = Decimal("10000")
        quarterly = calc.calculate_quarterly_payment(annual)
        assert quarterly == Decimal("2500")

    def test_result_contains_year(self, calc: EinkommensteuerCalculator) -> None:
        """Result should contain the tax year."""
        result = calc.calculate(Decimal("50000"))
        assert result.year == 2026


class TestEinkommensteuerConvenienceFunction:
    """Test the convenience function."""

    def test_convenience_function_works(self) -> None:
        """Convenience function should return same result as calculator."""
        result = calculate_einkommensteuer(Decimal("50000"), 2026)
        assert result.einkommensteuer > Decimal("0")
        assert result.year == 2026

    def test_default_year_is_2026(self) -> None:
        """Default year should be 2026."""
        result = calculate_einkommensteuer(Decimal("50000"))
        assert result.year == 2026


class TestEinkommensteuerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_income(self) -> None:
        """Zero income should result in zero tax."""
        result = calculate_einkommensteuer(Decimal("0"))
        assert result.einkommensteuer == Decimal("0")
        assert result.total_tax == Decimal("0")

    def test_very_large_income(self) -> None:
        """Very large income should be handled correctly."""
        result = calculate_einkommensteuer(Decimal("10000000"))
        assert result.einkommensteuer > Decimal("0")
        assert result.marginal_rate == Decimal("45.00")

    def test_decimal_precision_maintained(self) -> None:
        """Decimal precision should be maintained in calculations."""
        result = calculate_einkommensteuer(Decimal("12345.67"))
        # Result should be Decimal, not float
        assert isinstance(result.einkommensteuer, Decimal)
        assert isinstance(result.effective_rate, Decimal)

    def test_tax_zones_are_continuous(self) -> None:
        """Tax amount should increase continuously across zone boundaries."""
        calc = EinkommensteuerCalculator(2026)

        # Test around zone 1 -> zone 2 boundary
        just_below = calc.calculate(calc.config.zone1_end - Decimal("1"))
        at_boundary = calc.calculate(calc.config.zone1_end)
        just_above = calc.calculate(calc.config.zone1_end + Decimal("1"))

        assert just_below.einkommensteuer <= at_boundary.einkommensteuer
        assert at_boundary.einkommensteuer <= just_above.einkommensteuer
