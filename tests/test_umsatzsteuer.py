"""Tests for German VAT Calculator (Umsatzsteuer).

Tests verify VAT calculations per UStG.
"""
from datetime import date
from decimal import Decimal

import pytest

from src.core.models import Expense, Invoice, VatRate
from src.core.tax.umsatzsteuer import (
    UmsatzsteuerCalculator,
    UstFrequency,
    calculate_vat_from_gross,
    calculate_vat_liability,
)


class TestUmsatzsteuerCalculator:
    """Test suite for UmsatzsteuerCalculator."""

    @pytest.fixture
    def calc(self) -> UmsatzsteuerCalculator:
        """Create calculator for 2026."""
        return UmsatzsteuerCalculator(2026)

    def test_calculate_vat_standard_rate(self, calc: UmsatzsteuerCalculator) -> None:
        """Standard rate should be 19%."""
        vat = calc.calculate_vat(Decimal("100"), VatRate.STANDARD)
        assert vat == Decimal("19.00")

    def test_calculate_vat_reduced_rate(self, calc: UmsatzsteuerCalculator) -> None:
        """Reduced rate should be 7%."""
        vat = calc.calculate_vat(Decimal("100"), VatRate.REDUCED)
        assert vat == Decimal("7.00")

    def test_calculate_vat_zero_rate(self, calc: UmsatzsteuerCalculator) -> None:
        """Zero rate should be 0%."""
        vat = calc.calculate_vat(Decimal("100"), VatRate.ZERO)
        assert vat == Decimal("0.00")

    def test_extract_vat_from_gross_standard(self, calc: UmsatzsteuerCalculator) -> None:
        """Should correctly extract net and VAT from gross amount."""
        net, vat = calc.extract_vat_from_gross(Decimal("119.00"), VatRate.STANDARD)
        assert net == Decimal("100.00")
        assert vat == Decimal("19.00")

    def test_extract_vat_from_gross_reduced(self, calc: UmsatzsteuerCalculator) -> None:
        """Should correctly extract net and VAT for reduced rate."""
        net, vat = calc.extract_vat_from_gross(Decimal("107.00"), VatRate.REDUCED)
        assert net == Decimal("100.00")
        assert vat == Decimal("7.00")


class TestVatLiabilityCalculation:
    """Test VAT liability (Zahllast) calculation."""

    @pytest.fixture
    def calc(self) -> UmsatzsteuerCalculator:
        """Create calculator for 2026."""
        return UmsatzsteuerCalculator(2026)

    def test_zahllast_positive_when_ust_exceeds_vorsteuer(
        self, calc: UmsatzsteuerCalculator, sample_invoices: list[Invoice], sample_expenses: list[Expense]
    ) -> None:
        """Zahllast should be positive when USt collected > Vorsteuer."""
        result = calc.calculate_period_liability(sample_invoices, sample_expenses, "2026-01")
        # USt collected: 190 + 35 = 225
        # Vorsteuer: 19 + 3.50 = 22.50
        # Zahllast: 225 - 22.50 = 202.50
        assert result.zahllast > Decimal("0")

    def test_zahllast_negative_when_vorsteuer_exceeds_ust(
        self, calc: UmsatzsteuerCalculator, sample_expenses: list[Expense]
    ) -> None:
        """Zahllast should be negative when Vorsteuer > USt collected."""
        # No invoices, only expenses
        result = calc.calculate_period_liability([], sample_expenses, "2026-01")
        assert result.zahllast < Decimal("0")  # Credit from Vorsteuer

    def test_nullmeldung_for_reverse_charge_only(self, calc: UmsatzsteuerCalculator) -> None:
        """Nullmeldung should be True when only Reverse Charge invoices."""
        reverse_charge_invoice = Invoice(
            id=1,
            invoice_number="RE-2026-001",
            client="EU Client",
            description="Services",
            amount=Decimal("5000.00"),
            vat_rate=VatRate.ZERO,
            date=date(2026, 1, 15),
        )
        result = calc.calculate_period_liability([reverse_charge_invoice], [], "2026-01")
        assert result.is_nullmeldung is True
        assert result.umsatzsteuer_collected == Decimal("0.00")

    def test_empty_period_has_zero_liability(self, calc: UmsatzsteuerCalculator) -> None:
        """Empty period should have zero liability."""
        result = calc.calculate_period_liability([], [], "2026-01")
        assert result.zahllast == Decimal("0.00")
        assert result.umsatzsteuer_collected == Decimal("0.00")
        assert result.vorsteuer_paid == Decimal("0.00")


class TestKleinunternehmerRegelung:
    """Test Kleinunternehmerregelung (§ 19 UStG)."""

    @pytest.fixture
    def calc(self) -> UmsatzsteuerCalculator:
        """Create calculator for 2026."""
        return UmsatzsteuerCalculator(2026)

    def test_eligible_below_thresholds(self, calc: UmsatzsteuerCalculator) -> None:
        """Should be eligible when below both thresholds."""
        eligible, reason = calc.check_kleinunternehmer_eligibility(
            revenue_prior_year=Decimal("20000"),
            revenue_current_year=Decimal("50000"),
        )
        assert eligible is True
        assert reason is None

    def test_not_eligible_prior_year_exceeds(self, calc: UmsatzsteuerCalculator) -> None:
        """Should not be eligible when prior year exceeds threshold."""
        eligible, reason = calc.check_kleinunternehmer_eligibility(
            revenue_prior_year=Decimal("30000"),  # Exceeds €25,000
            revenue_current_year=Decimal("50000"),
        )
        assert eligible is False
        assert reason is not None
        assert "Vorjahresumsatz" in reason

    def test_not_eligible_current_year_exceeds(self, calc: UmsatzsteuerCalculator) -> None:
        """Should not be eligible when current year exceeds threshold."""
        eligible, reason = calc.check_kleinunternehmer_eligibility(
            revenue_prior_year=Decimal("20000"),
            revenue_current_year=Decimal("110000"),  # Exceeds €100,000
        )
        assert eligible is False
        assert reason is not None
        assert "SOFORTIGE" in reason


class TestFilingFrequency:
    """Test USt-Voranmeldung filing frequency determination."""

    @pytest.fixture
    def calc(self) -> UmsatzsteuerCalculator:
        """Create calculator for 2026."""
        return UmsatzsteuerCalculator(2026)

    def test_new_business_always_monthly(self, calc: UmsatzsteuerCalculator) -> None:
        """New businesses should file monthly."""
        frequency = calc.determine_filing_frequency(
            prior_year_vat_liability=Decimal("1000"),
            is_new_business=True,
        )
        assert frequency == UstFrequency.MONTHLY

    def test_high_liability_monthly(self, calc: UmsatzsteuerCalculator) -> None:
        """High liability (>€7,500) should file monthly."""
        frequency = calc.determine_filing_frequency(
            prior_year_vat_liability=Decimal("10000"),
            is_new_business=False,
        )
        assert frequency == UstFrequency.MONTHLY

    def test_medium_liability_quarterly(self, calc: UmsatzsteuerCalculator) -> None:
        """Medium liability (€2,000-€7,500) should file quarterly."""
        frequency = calc.determine_filing_frequency(
            prior_year_vat_liability=Decimal("5000"),
            is_new_business=False,
        )
        assert frequency == UstFrequency.QUARTERLY

    def test_low_liability_annual(self, calc: UmsatzsteuerCalculator) -> None:
        """Low liability (<€2,000) should file annually."""
        frequency = calc.determine_filing_frequency(
            prior_year_vat_liability=Decimal("1000"),
            is_new_business=False,
        )
        assert frequency == UstFrequency.ANNUAL


class TestReverseCharge:
    """Test Reverse Charge calculation for EU B2B."""

    @pytest.fixture
    def calc(self) -> UmsatzsteuerCalculator:
        """Create calculator for 2026."""
        return UmsatzsteuerCalculator(2026)

    def test_reverse_charge_total(
        self, calc: UmsatzsteuerCalculator, sample_invoices: list[Invoice]
    ) -> None:
        """Should calculate total Reverse Charge revenue."""
        total = calc.calculate_reverse_charge_total(sample_invoices)
        # Sample invoices has one €5000 Reverse Charge invoice
        assert total == Decimal("5000.00")

    def test_no_reverse_charge_returns_zero(self, calc: UmsatzsteuerCalculator) -> None:
        """Should return zero when no Reverse Charge invoices."""
        standard_invoice = Invoice(
            id=1,
            invoice_number="RE-2026-001",
            client="German Client",
            description="Services",
            amount=Decimal("1190.00"),
            vat_rate=VatRate.STANDARD,
            date=date(2026, 1, 15),
        )
        total = calc.calculate_reverse_charge_total([standard_invoice])
        assert total == Decimal("0.00")


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_calculate_vat_from_gross_function(self) -> None:
        """Convenience function should extract net and VAT."""
        net, vat = calculate_vat_from_gross(Decimal("119.00"), VatRate.STANDARD)
        assert net == Decimal("100.00")
        assert vat == Decimal("19.00")

    def test_calculate_vat_liability_function(
        self, sample_invoices: list[Invoice], sample_expenses: list[Expense]
    ) -> None:
        """Convenience function should calculate liability."""
        result = calculate_vat_liability(sample_invoices, sample_expenses, "2026-01")
        assert result.period == "2026-01"
        assert result.zahllast is not None
