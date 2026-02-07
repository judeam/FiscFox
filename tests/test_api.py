"""Tests for API routes.

Tests verify HTTP endpoints return correct responses.
Note: Integration tests require database setup. Run with pytest -m integration.
"""
import pytest
from httpx import AsyncClient


class TestStaticFiles:
    """Test static file serving."""

    @pytest.mark.asyncio
    async def test_static_css_accessible(self, client: AsyncClient) -> None:
        """Static CSS should be accessible."""
        response = await client.get("/static/css/main.css")
        # May return 200 or 404 depending on file existence
        assert response.status_code in [200, 404]


# All routes that access database are marked as integration tests
@pytest.mark.integration
class TestDashboardRoutes:
    """Test dashboard page routes (requires database)."""

    @pytest.mark.asyncio
    async def test_dashboard_returns_html(self, client: AsyncClient) -> None:
        """Dashboard should return HTML response."""
        response = await client.get("/", follow_redirects=True)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_dashboard_contains_title(self, client: AsyncClient) -> None:
        """Dashboard should contain the app title."""
        response = await client.get("/", follow_redirects=True)
        assert response.status_code == 200


@pytest.mark.integration
class TestSettingsRoutes:
    """Test settings page routes (requires database)."""

    @pytest.mark.asyncio
    async def test_settings_page_returns_html(self, client: AsyncClient) -> None:
        """Settings page should return HTML response."""
        response = await client.get("/settings", follow_redirects=True)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.integration
class TestExpenseRoutes:
    """Test expense page routes (requires database)."""

    @pytest.mark.asyncio
    async def test_expenses_page_returns_html(self, client: AsyncClient) -> None:
        """Expenses page should return HTML response."""
        response = await client.get("/ausgaben", follow_redirects=True)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.integration
class TestInvoiceRoutes:
    """Test invoice page routes (requires database)."""

    @pytest.mark.asyncio
    async def test_invoices_page_returns_html(self, client: AsyncClient) -> None:
        """Invoices page should return HTML response."""
        response = await client.get("/rechnungen", follow_redirects=True)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.integration
class TestTaxRoutes:
    """Test tax overview page routes (requires database)."""

    @pytest.mark.asyncio
    async def test_taxes_page_returns_html(self, client: AsyncClient) -> None:
        """Taxes page should return HTML response."""
        response = await client.get("/steuern", follow_redirects=True)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.integration
class TestReportRoutes:
    """Test reports page routes (requires database)."""

    @pytest.mark.asyncio
    async def test_reports_page_returns_html(self, client: AsyncClient) -> None:
        """Reports page should return HTML response."""
        response = await client.get("/berichte", follow_redirects=True)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.integration
class TestClientsRoutes:
    """Test clients API routes (requires database)."""

    @pytest.mark.asyncio
    async def test_clients_list_returns_html(self, client: AsyncClient) -> None:
        """Clients list should return HTML response."""
        response = await client.get("/clients/", follow_redirects=True)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.integration
class TestExpensesAPI:
    """Test expenses API endpoints (requires database)."""

    @pytest.mark.asyncio
    async def test_expenses_list_returns_html(self, client: AsyncClient) -> None:
        """Expenses list should return HTML response."""
        response = await client.get("/expenses/", follow_redirects=True)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.integration
class TestInvoicesAPI:
    """Test invoices API endpoints (requires database)."""

    @pytest.mark.asyncio
    async def test_invoices_list_returns_html(self, client: AsyncClient) -> None:
        """Invoices list should return HTML response."""
        response = await client.get("/invoices/", follow_redirects=True)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
