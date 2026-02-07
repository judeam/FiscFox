"""Tests for core models.

Tests verify Pydantic models and enums work correctly.
"""
from datetime import date
from decimal import Decimal

import pytest

from src.core.models import (
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceStatus,
    TaxYearConfig,
    UserSettings,
    VatRate,
    get_tax_config,
)


class TestVatRate:
    """Test VatRate enum."""

    def test_standard_rate_value(self) -> None:
        """Standard rate should be 0.19."""
        assert VatRate.STANDARD.value == "0.19"

    def test_reduced_rate_value(self) -> None:
        """Reduced rate should be 0.07."""
        assert VatRate.REDUCED.value == "0.07"

    def test_zero_rate_value(self) -> None:
        """Zero rate should be 0.00."""
        assert VatRate.ZERO.value == "0.00"

    def test_can_convert_to_decimal(self) -> None:
        """Should be convertible to Decimal."""
        rate = Decimal(VatRate.STANDARD.value)
        assert rate == Decimal("0.19")


class TestExpenseCategory:
    """Test ExpenseCategory enum."""

    def test_all_categories_exist(self) -> None:
        """All expected categories should exist."""
        expected = [
            "BUERO",
            "SOFTWARE",
            "HARDWARE",
            "REISE",
            "KOMMUNIKATION",
            "VERSICHERUNG",
            "FORTBILDUNG",
            "SONSTIGES",
        ]
        actual = [cat.name for cat in ExpenseCategory]
        for exp in expected:
            assert exp in actual


class TestInvoiceStatus:
    """Test InvoiceStatus enum."""

    def test_statuses_exist(self) -> None:
        """All invoice statuses should exist."""
        assert InvoiceStatus.PENDING is not None
        assert InvoiceStatus.PAID is not None
        assert InvoiceStatus.OVERDUE is not None


class TestInvoice:
    """Test Invoice model."""

    def test_invoice_creation(self) -> None:
        """Should create invoice with valid data."""
        invoice = Invoice(
            id=1,
            invoice_number="RE-2026-001",
            client="Test Client",
            description="Services",
            amount=Decimal("1190.00"),
            vat_rate=VatRate.STANDARD,
            date=date(2026, 1, 15),
            due_date=date(2026, 2, 15),
            status=InvoiceStatus.PENDING,
        )
        assert invoice.amount == Decimal("1190.00")
        assert invoice.vat_rate == VatRate.STANDARD
        # Computed fields
        assert invoice.amount_net == Decimal("1000.00")
        assert invoice.vat_amount == Decimal("190.00")

    def test_invoice_defaults(self) -> None:
        """Should use default values correctly."""
        invoice = Invoice(
            id=1,
            invoice_number="RE-2026-001",
            client="Test Client",
            description="Services",
            amount=Decimal("1190.00"),
            date=date(2026, 1, 15),
        )
        assert invoice.status == InvoiceStatus.PENDING
        assert invoice.vat_rate == VatRate.STANDARD


class TestExpense:
    """Test Expense model."""

    def test_expense_creation(self) -> None:
        """Should create expense with valid data."""
        expense = Expense(
            id=1,
            date=date(2026, 1, 10),
            vendor="Office Supply Co",
            description="Office Supplies",
            category=ExpenseCategory.BUERO,
            amount_gross=Decimal("119.00"),
            vat_rate=VatRate.STANDARD,
        )
        assert expense.amount_gross == Decimal("119.00")
        assert expense.category == ExpenseCategory.BUERO
        # Computed fields
        assert expense.amount_net == Decimal("100.00")
        assert expense.vat_amount == Decimal("19.00")


class TestTaxYearConfig:
    """Test TaxYearConfig model."""

    def test_config_2026_exists(self) -> None:
        """2026 config should exist."""
        config = get_tax_config(2026)
        assert config is not None
        assert config.year == 2026

    def test_config_2025_exists(self) -> None:
        """2025 config should exist."""
        config = get_tax_config(2025)
        assert config is not None
        assert config.year == 2025

    def test_grundfreibetrag_increases_over_time(self) -> None:
        """Grundfreibetrag should increase from 2025 to 2026."""
        config_2025 = get_tax_config(2025)
        config_2026 = get_tax_config(2026)
        assert config_2026.grundfreibetrag >= config_2025.grundfreibetrag

    def test_invalid_year_raises_error(self) -> None:
        """Invalid year should raise InvalidTaxYearError."""
        from src.core.exceptions import InvalidTaxYearError
        with pytest.raises(InvalidTaxYearError):
            get_tax_config(2000)  # Year not supported


class TestUserSettings:
    """Test UserSettings model."""

    def test_default_settings(self) -> None:
        """Should have sensible defaults."""
        settings = UserSettings()
        assert settings.language == "de"  # Default is German

    def test_sender_info_generation(self) -> None:
        """Should generate sender info from settings."""
        settings = UserSettings(
            business_name="Test GmbH",
            street="Teststr. 1",
            zip_code="12345",
            city="Berlin",
            country="DE",
            vat_id="DE123456789",
            email="test@example.com",
            phone="+49 30 12345",
        )
        sender = settings.to_sender_info()
        assert sender.name == "Test GmbH"
        assert sender.city == "Berlin"
