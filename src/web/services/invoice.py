"""Invoice service for client invoice management.

Handles invoice creation, payment tracking, and revenue calculations.
"""

from datetime import date
from decimal import Decimal

from src.core.cache import invalidate_financial_caches
from src.core.models import (
    Invoice,
    InvoiceInput,
    InvoiceStatus,
    VatRate,
)
from src.db.repository import InvoiceRepository, UploadedDocumentRepository


class InvoiceService:
    """Service for invoice operations.

    Orchestrates invoice creation, status updates, and revenue tracking.
    """

    def __init__(
        self,
        invoice_repo: InvoiceRepository | None = None,
        uploaded_doc_repo: UploadedDocumentRepository | None = None,
    ):
        """Initialize invoice service.

        Args:
            invoice_repo: Invoice repository (default: new instance)
            uploaded_doc_repo: Uploaded document repository (default: new instance)
        """
        self.invoice_repo = invoice_repo or InvoiceRepository()
        self.uploaded_doc_repo = uploaded_doc_repo or UploadedDocumentRepository()

    async def create_invoice(
        self,
        invoice: InvoiceInput,
        client_id: int | None = None,
    ) -> Invoice:
        """Create a new invoice.

        Args:
            invoice: InvoiceInput data
            client_id: Optional client ID to link invoice to client

        Returns:
            Created Invoice with ID
        """
        result = await self.invoice_repo.create(invoice, client_id=client_id)
        await invalidate_financial_caches()
        return result

    async def create_invoice_auto_number(
        self,
        client: str,
        amount: Decimal,
        description: str,
        invoice_date: date | None = None,
        due_date: date | None = None,
        vat_rate: VatRate = VatRate.ZERO,  # Default: Reverse Charge
    ) -> Invoice:
        """Create invoice with auto-generated number.

        Args:
            client: Client name
            amount: Invoice amount
            description: Service description
            invoice_date: Invoice date (default: today)
            due_date: Due date (default: +30 days)
            vat_rate: VAT rate (default: 0% for international)

        Returns:
            Created Invoice
        """
        invoice_date = invoice_date or date.today()
        due_date = due_date or date(
            invoice_date.year,
            invoice_date.month + 1 if invoice_date.month < 12 else 1,
            invoice_date.day,
        )

        # Generate invoice number
        invoice_number = await self.invoice_repo.get_next_invoice_number(
            invoice_date.year
        )

        invoice_input = InvoiceInput(
            client=client,
            invoice_number=invoice_number,
            date=invoice_date,
            due_date=due_date,
            amount=amount,
            vat_rate=vat_rate,
            description=description,
        )

        return await self.invoice_repo.create(invoice_input)

    async def get_invoice(self, invoice_id: int) -> Invoice | None:
        """Get invoice by ID.

        Args:
            invoice_id: Invoice ID

        Returns:
            Invoice or None
        """
        return await self.invoice_repo.get_by_id(invoice_id)

    async def get_invoices(
        self,
        status: InvoiceStatus | None = None,
        limit: int = 100,
    ) -> list[Invoice]:
        """Get invoices with optional status filter.

        Args:
            status: Filter by status (None for all)
            limit: Max results

        Returns:
            List of Invoice objects
        """
        return await self.invoice_repo.get_by_status(status, limit)

    async def get_invoices_by_period(
        self,
        start_date: date,
        end_date: date,
    ) -> list[Invoice]:
        """Get invoices within date range.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of Invoice objects
        """
        return await self.invoice_repo.get_by_period(start_date, end_date)

    async def mark_paid(
        self,
        invoice_id: int,
        paid_date: date | None = None,
    ) -> Invoice | None:
        """Mark invoice as paid.

        Args:
            invoice_id: Invoice ID
            paid_date: Payment date (default: today)

        Returns:
            Updated Invoice or None
        """
        paid_date = paid_date or date.today()
        result = await self.invoice_repo.mark_paid(invoice_id, paid_date)
        if result:
            await invalidate_financial_caches()
        return result

    async def delete_invoice(self, invoice_id: int) -> bool:
        """Soft delete an invoice and its linked uploaded documents.

        Args:
            invoice_id: Invoice ID

        Returns:
            True if deleted
        """
        # Delete linked uploaded documents first
        await self.uploaded_doc_repo.delete_by_invoice_id(invoice_id)
        # Then delete the invoice
        result = await self.invoice_repo.delete(invoice_id)
        if result:
            await invalidate_financial_caches()
        return result

    async def update_invoice(
        self,
        invoice_id: int,
        client: str,
        invoice_number: str,
        date: date,
        due_date: date | None,
        amount: Decimal,
        vat_rate: VatRate,
        description: str,
        status: InvoiceStatus,
    ) -> Invoice | None:
        """Update an existing invoice.

        Args:
            invoice_id: Invoice ID
            client: Client name
            invoice_number: Invoice number
            date: Invoice date
            due_date: Due date
            amount: Net amount
            vat_rate: VAT rate
            description: Description
            status: Invoice status

        Returns:
            Updated Invoice or None
        """
        result = await self.invoice_repo.update(
            invoice_id=invoice_id,
            client=client,
            invoice_number=invoice_number,
            invoice_date=date,
            due_date=due_date,
            amount=amount,
            vat_rate=vat_rate,
            description=description,
            status=status,
        )
        if result:
            await invalidate_financial_caches()
        return result

    async def update_overdue_status(self) -> int:
        """Update status of overdue invoices.

        Checks all pending invoices and marks as overdue if past due date.

        Returns:
            Number of invoices marked overdue
        """
        return await self.invoice_repo.update_overdue()

    async def get_pending_invoices(self) -> list[Invoice]:
        """Get all pending (unpaid) invoices.

        Returns:
            List of pending invoices
        """
        return await self.invoice_repo.get_by_status(InvoiceStatus.PENDING)

    async def get_overdue_invoices(self) -> list[Invoice]:
        """Get all overdue invoices.

        Returns:
            List of overdue invoices
        """
        # First update overdue status
        await self.update_overdue_status()
        return await self.invoice_repo.get_by_status(InvoiceStatus.OVERDUE)

    async def get_revenue_summary(
        self,
        year: int | None = None,
    ) -> dict[str, Decimal]:
        """Get revenue summary for the year.

        Args:
            year: Tax year (default: current year)

        Returns:
            Dictionary with revenue breakdown
        """
        from src.web.routes.settings import get_activity_start_date

        year = year or date.today().year
        activity_start = get_activity_start_date()
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        # Clamp to activity start date if set
        if activity_start and activity_start > year_start:
            year_start = activity_start

        total_net, total_vat, reverse_charge = await self.invoice_repo.get_revenue_by_period(
            year_start, year_end
        )

        return {
            "total_net": total_net,
            "total_vat": total_vat,
            "total_gross": total_net + total_vat,
            "reverse_charge": reverse_charge,
            "domestic": total_net - reverse_charge,
        }

    async def get_monthly_revenue(
        self,
        year: int | None = None,
    ) -> dict[str, Decimal]:
        """Get monthly revenue totals.

        Args:
            year: Tax year

        Returns:
            Dictionary mapping month (YYYY-MM) to total net revenue
        """
        from src.web.routes.settings import get_activity_start_date

        year = year or date.today().year
        activity_start = get_activity_start_date()

        # Use repository's efficient monthly revenue query
        monthly_data = await self.invoice_repo.get_monthly_revenue(year, activity_start)

        # Convert to dict format expected by callers
        monthly: dict[str, Decimal] = {}
        for month_num, amount in monthly_data:
            month_key = f"{year}-{month_num:02d}"
            monthly[month_key] = amount

        return monthly

    async def get_client_summary(
        self,
        year: int | None = None,
    ) -> dict[str, Decimal]:
        """Get revenue by client.

        Args:
            year: Tax year

        Returns:
            Dictionary mapping client name to total revenue
        """
        from src.web.routes.settings import get_activity_start_date

        year = year or date.today().year
        activity_start = get_activity_start_date()

        # Use repository's stats_by_client with activity start date
        stats = await self.invoice_repo.get_stats_by_client(year, activity_start)

        # Convert to simple client name -> total revenue mapping
        # Note: This uses client_id, we'd need to look up client names
        # For now, return stats with client IDs
        by_client: dict[str, Decimal] = {}
        for stat in stats:
            client_id = str(stat.get("client_id", "Unknown"))
            by_client[client_id] = Decimal(stat.get("total_net", "0"))

        return by_client

    async def get_recent_invoices(self, limit: int = 5) -> list[Invoice]:
        """Get most recent invoices.

        Args:
            limit: Max results

        Returns:
            List of recent invoices
        """
        return await self.invoice_repo.get_by_status(limit=limit)

    async def get_revenue_by_client(
        self,
        year: int | None = None,
    ) -> dict[str, Decimal]:
        """Get revenue grouped by client name for Scheinselbständigkeit analysis.

        Args:
            year: Tax year (default: current year)

        Returns:
            Dictionary mapping client name to total net revenue
        """
        from src.web.routes.settings import get_activity_start_date

        year = year or date.today().year
        activity_start = get_activity_start_date()
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        # Clamp to activity start date if set
        if activity_start and activity_start > year_start:
            year_start = activity_start

        # Get all paid invoices for the year
        invoices = await self.invoice_repo.get_by_period(year_start, year_end)

        # Aggregate by client name
        by_client: dict[str, Decimal] = {}
        for inv in invoices:
            # Only count paid invoices for actual revenue
            if inv.status == InvoiceStatus.PAID:
                client_name = inv.client or "Unbekannt"
                current = by_client.get(client_name, Decimal("0"))
                # Use net amount (without VAT)
                net_amount = inv.amount / (1 + Decimal(str(inv.vat_rate.value)))
                by_client[client_name] = current + net_amount.quantize(Decimal("0.01"))

        return by_client


# FastAPI dependency
async def get_invoice_service() -> InvoiceService:
    """FastAPI dependency for InvoiceService."""
    return InvoiceService()
