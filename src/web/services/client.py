"""Client service for client management.

Handles client CRUD operations, dropdown data, and income statistics
for Scheinselbständigkeit detection (§ 7 SGB IV).
"""

from decimal import Decimal

from src.core.models import (
    SCHEINSELBSTAENDIG_THRESHOLD,
    Client,
    ClientInput,
    ClientStats,
    IncomeDistribution,
)
from src.db.repository import ClientRepository, InvoiceRepository


class ClientService:
    """Service for client operations.

    Orchestrates client CRUD operations, provides data for forms,
    and calculates income distribution for Scheinselbständigkeit detection.
    """

    def __init__(
        self,
        client_repo: ClientRepository | None = None,
        invoice_repo: InvoiceRepository | None = None,
    ):
        """Initialize client service.

        Args:
            client_repo: Client repository (default: new instance)
            invoice_repo: Invoice repository for statistics (default: new instance)
        """
        self.client_repo = client_repo or ClientRepository()
        self.invoice_repo = invoice_repo or InvoiceRepository()

    async def create_client(self, client: ClientInput) -> Client:
        """Create a new client.

        Args:
            client: ClientInput data

        Returns:
            Created Client with ID
        """
        return await self.client_repo.create(client)

    async def get_client(self, client_id: int) -> Client | None:
        """Get client by ID.

        Args:
            client_id: Client ID

        Returns:
            Client or None
        """
        return await self.client_repo.get_by_id(client_id)

    async def get_all_clients(self, limit: int = 100) -> list[Client]:
        """Get all clients.

        Args:
            limit: Max results

        Returns:
            List of Client objects
        """
        return await self.client_repo.get_all(limit=limit)

    async def get_clients_for_dropdown(self) -> list[dict]:
        """Get clients for dropdown selection.

        Returns:
            List of dicts with id, name, city, country, vat_id
        """
        return await self.client_repo.get_for_dropdown()

    async def update_client(
        self,
        client_id: int,
        client: ClientInput,
    ) -> Client | None:
        """Update a client.

        Args:
            client_id: Client ID
            client: New data

        Returns:
            Updated Client or None
        """
        return await self.client_repo.update(client_id, client)

    async def delete_client(self, client_id: int) -> bool:
        """Soft delete a client.

        Args:
            client_id: Client ID

        Returns:
            True if deleted
        """
        return await self.client_repo.delete(client_id)

    async def search_clients(
        self,
        query: str,
        limit: int = 10,
    ) -> list[Client]:
        """Search clients by name, city, or email.

        Args:
            query: Search string
            limit: Max results

        Returns:
            List of matching Client objects
        """
        return await self.client_repo.search(query, limit)

    # =========================================================================
    # Income Distribution & Scheinselbständigkeit Detection
    # =========================================================================

    async def get_income_distribution(
        self,
        year: int | None = None,
    ) -> IncomeDistribution:
        """Analyze income distribution for Scheinselbständigkeit detection.

        Calculates the percentage of income from each client to detect
        potential false self-employment risk (>83% from single client).

        Args:
            year: Optional year filter (default: all time)

        Returns:
            IncomeDistribution with client breakdown and warnings
        """
        # Get all clients
        clients = await self.client_repo.get_all(limit=1000)

        # Get invoice statistics grouped by client
        invoice_stats = await self.invoice_repo.get_stats_by_client(year=year)

        # Build a lookup dict: client_id -> stats
        stats_lookup: dict[int, dict] = {
            stat["client_id"]: stat for stat in invoice_stats if stat["client_id"]
        }

        # Calculate total income across all clients
        total_income = Decimal("0.00")
        for stat in invoice_stats:
            total_income += Decimal(str(stat["total_net"]))

        # Build ClientStats for each client
        client_breakdown: list[ClientStats] = []
        clients_at_risk = 0
        max_concentration = Decimal("0.00")

        for client in clients:
            stat = stats_lookup.get(client.id, {})

            total_invoiced = Decimal(str(stat.get("total_net", "0.00")))
            total_paid = Decimal(str(stat.get("paid_net", "0.00")))
            invoice_count = stat.get("invoice_count", 0)
            paid_invoice_count = stat.get("paid_count", 0)

            # Calculate income percentage
            if total_income > Decimal("0"):
                income_percentage = (total_invoiced / total_income).quantize(
                    Decimal("0.0001")
                )
            else:
                income_percentage = Decimal("0.00")

            # Check Scheinselbständigkeit risk
            is_risk = income_percentage >= SCHEINSELBSTAENDIG_THRESHOLD
            if is_risk:
                clients_at_risk += 1

            max_concentration = max(max_concentration, income_percentage)

            client_stats = ClientStats(
                client=client,
                invoice_count=invoice_count,
                paid_invoice_count=paid_invoice_count,
                total_invoiced=total_invoiced,
                total_paid=total_paid,
                outstanding=(total_invoiced - total_paid).quantize(Decimal("0.01")),
                income_percentage=income_percentage,
                is_scheinselbstaendig_risk=is_risk,
            )
            client_breakdown.append(client_stats)

        # Sort by income percentage descending
        client_breakdown.sort(key=lambda x: x.income_percentage, reverse=True)

        return IncomeDistribution(
            total_income=total_income,
            client_breakdown=client_breakdown,
            max_concentration=max_concentration,
            scheinselbstaendig_warning=clients_at_risk > 0,
            clients_at_risk=clients_at_risk,
        )

    async def get_client_stats(
        self,
        client_id: int,
        year: int | None = None,
    ) -> ClientStats | None:
        """Get detailed statistics for a single client.

        Args:
            client_id: Client ID
            year: Optional year filter

        Returns:
            ClientStats or None if client not found
        """
        client = await self.client_repo.get_by_id(client_id)
        if not client:
            return None

        # Get this client's invoice stats
        stats = await self.invoice_repo.get_stats_for_client(client_id, year=year)

        # Get total income for percentage calculation
        all_stats = await self.invoice_repo.get_stats_by_client(year=year)
        total_income = sum(
            Decimal(str(s["total_net"])) for s in all_stats if s["client_id"]
        )

        total_invoiced = Decimal(str(stats.get("total_net", "0.00")))
        total_paid = Decimal(str(stats.get("paid_net", "0.00")))

        if total_income > Decimal("0"):
            income_percentage = (total_invoiced / total_income).quantize(
                Decimal("0.0001")
            )
        else:
            income_percentage = Decimal("0.00")

        return ClientStats(
            client=client,
            invoice_count=stats.get("invoice_count", 0),
            paid_invoice_count=stats.get("paid_count", 0),
            total_invoiced=total_invoiced,
            total_paid=total_paid,
            outstanding=(total_invoiced - total_paid).quantize(Decimal("0.01")),
            income_percentage=income_percentage,
            is_scheinselbstaendig_risk=income_percentage >= SCHEINSELBSTAENDIG_THRESHOLD,
        )


# FastAPI dependency
async def get_client_service() -> ClientService:
    """FastAPI dependency for ClientService."""
    return ClientService()
