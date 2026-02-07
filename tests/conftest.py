"""Pytest fixtures for FiscFox tests."""
import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.models import (
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceStatus,
    TaxYearConfig,
    VatRate,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for testing API routes."""
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def tax_config_2026() -> TaxYearConfig:
    """Tax configuration for 2026."""
    from src.core.models import get_tax_config
    return get_tax_config(2026)


@pytest.fixture
def sample_invoices() -> list[Invoice]:
    """Sample invoices for testing."""
    return [
        Invoice(
            id=1,
            invoice_number="RE-2026-001",
            client="Test Client GmbH",
            description="Consulting Services",
            amount=Decimal("1190.00"),  # Gross amount
            vat_rate=VatRate.STANDARD,
            date=date(2026, 1, 15),
            due_date=date(2026, 2, 15),
            status=InvoiceStatus.PENDING,
        ),
        Invoice(
            id=2,
            invoice_number="RE-2026-002",
            client="EU Client B.V.",
            description="Software Development",
            amount=Decimal("5000.00"),  # Reverse Charge - no VAT
            vat_rate=VatRate.ZERO,
            date=date(2026, 1, 20),
            due_date=date(2026, 2, 20),
            status=InvoiceStatus.PENDING,
        ),
        Invoice(
            id=3,
            invoice_number="RE-2026-003",
            client="Small Business AG",
            description="Workshop",
            amount=Decimal("535.00"),  # Reduced rate
            vat_rate=VatRate.REDUCED,
            date=date(2026, 2, 1),
            due_date=date(2026, 3, 1),
            status=InvoiceStatus.PAID,
        ),
    ]


@pytest.fixture
def sample_expenses() -> list[Expense]:
    """Sample expenses for testing."""
    return [
        Expense(
            id=1,
            date=date(2026, 1, 10),
            vendor="Office Supply Co",
            description="Office Supplies",
            category=ExpenseCategory.BUERO,
            amount_gross=Decimal("119.00"),
            vat_rate=VatRate.STANDARD,
        ),
        Expense(
            id=2,
            date=date(2026, 1, 15),
            vendor="Book Store",
            description="Professional Books",
            category=ExpenseCategory.FORTBILDUNG,
            amount_gross=Decimal("53.50"),
            vat_rate=VatRate.REDUCED,
        ),
        Expense(
            id=3,
            date=date(2026, 1, 20),
            vendor="Insurance GmbH",
            description="Business Insurance",
            category=ExpenseCategory.VERSICHERUNG,
            amount_gross=Decimal("200.00"),
            vat_rate=VatRate.ZERO,  # No VAT on insurance
        ),
    ]


@pytest.fixture
def high_income() -> Decimal:
    """High taxable income for testing top tax brackets."""
    return Decimal("300000")


@pytest.fixture
def medium_income() -> Decimal:
    """Medium taxable income for testing middle brackets."""
    return Decimal("50000")


@pytest.fixture
def low_income() -> Decimal:
    """Low taxable income below Grundfreibetrag."""
    return Decimal("10000")
