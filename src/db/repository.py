"""Database repository layer for FiscFox.

Provides async CRUD operations for expenses, invoices, and tax data.
Uses aiosqlite for async SQLite access with WAL mode.

All monetary values are stored as TEXT (Decimal strings) and converted
to Decimal on retrieval for precision.
"""

import os
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

import aiosqlite

from src.core.models import (
    Asset,
    AssetCategory,
    AssetInput,
    BusinessMeal,
    BusinessMealInput,
    Client,
    ClientInput,
    CoverageType,
    DepreciationMethod,
    DepreciationRecord,
    Expense,
    ExpenseCategory,
    ExpenseInput,
    GiftExpense,
    GiftRecipientSummary,
    HealthInsurance,
    HealthInsuranceInput,
    HealthInsuranceProvider,
    HomeOfficeDay,
    HomeOfficeDayInput,
    HomeOfficeSettings,
    HomeOfficeType,
    InsuranceType,
    Invoice,
    InvoiceInput,
    InvoiceStatus,
    TravelExpense,
    TravelExpenseInput,
    VatRate,
)

# Database file path (configurable via environment variable for Docker)
DB_PATH = Path(os.environ.get("DATABASE_PATH", Path(__file__).parent / "FiscFox.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class DatabaseManager:
    """Manages database connection and initialization."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Initialize database with schema."""
        async with aiosqlite.connect(self.db_path) as db:
            # Enable WAL mode for better concurrency
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA foreign_keys = ON")

            # Run migrations first (for existing databases)
            await self._run_migrations(db)

            # Read and execute schema (for new databases)
            if SCHEMA_PATH.exists():
                schema = SCHEMA_PATH.read_text()
                await db.executescript(schema)
                await db.commit()

    async def _run_migrations(self, db: aiosqlite.Connection) -> None:
        """Run database migrations for schema updates."""
        # Check if clients table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clients'"
        )
        clients_exists = await cursor.fetchone()

        if not clients_exists:
            # Create clients table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL CHECK (length(name) >= 1 AND length(name) <= 200),
                    street TEXT DEFAULT '',
                    address_details TEXT DEFAULT '',
                    zip_code TEXT DEFAULT '',
                    city TEXT DEFAULT '',
                    country TEXT DEFAULT 'DE' CHECK (length(country) = 2),
                    email TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    vat_id TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP DEFAULT NULL
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_clients_country ON clients(country)")

        # Check if invoices table has client_id column
        cursor = await db.execute("PRAGMA table_info(invoices)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "client_id" not in column_names and "invoices" in [
            row[0] for row in (await (await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='invoices'"
            )).fetchall())
        ]:
            # Add client_id column to invoices table
            await db.execute(
                "ALTER TABLE invoices ADD COLUMN client_id INTEGER REFERENCES clients(id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_invoices_client_id ON invoices(client_id)"
            )

        await db.commit()

        # Check if uploaded_documents table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='uploaded_documents'"
        )
        uploaded_docs_exists = await cursor.fetchone()

        if not uploaded_docs_exists:
            # Create uploaded_documents table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS uploaded_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL CHECK (length(filename) >= 1 AND length(filename) <= 255),
                    stored_filename TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL CHECK (file_size > 0),
                    content_hash TEXT NOT NULL,
                    mime_type TEXT DEFAULT 'application/pdf',
                    extraction_status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (extraction_status IN ('pending', 'processing', 'completed', 'failed', 'manual')),
                    extraction_confidence REAL CHECK (extraction_confidence IS NULL OR (extraction_confidence >= 0.0 AND extraction_confidence <= 1.0)),
                    extraction_method TEXT CHECK (extraction_method IS NULL OR extraction_method IN ('text', 'ocr', 'ai', 'manual')),
                    extracted_data TEXT,
                    extraction_errors TEXT,
                    invoice_id INTEGER REFERENCES invoices(id),
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    confirmed_at TIMESTAMP,
                    deleted_at TIMESTAMP DEFAULT NULL
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_uploaded_docs_status ON uploaded_documents(extraction_status)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_uploaded_docs_invoice ON uploaded_documents(invoice_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_uploaded_docs_hash ON uploaded_documents(content_hash)"
            )
            await db.commit()

        # Check if invoices table has uploaded_document_id column
        cursor = await db.execute("PRAGMA table_info(invoices)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "uploaded_document_id" not in column_names and "invoices" in [
            row[0] for row in (await (await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='invoices'"
            )).fetchall())
        ]:
            # Add uploaded_document_id column to invoices table
            await db.execute(
                "ALTER TABLE invoices ADD COLUMN uploaded_document_id INTEGER REFERENCES uploaded_documents(id)"
            )
            await db.commit()

    @asynccontextmanager
    async def get_connection(self):
        """Get database connection context manager."""
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        try:
            yield db
        finally:
            await db.close()


# Global database manager
db_manager = DatabaseManager()


class ExpenseRepository:
    """Repository for expense operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    async def create(self, expense: ExpenseInput) -> Expense:
        """Create a new expense.

        Args:
            expense: ExpenseInput data

        Returns:
            Created Expense with ID
        """
        # Calculate net and VAT
        rate = Decimal(expense.vat_rate.value)
        amount_net = (expense.amount_gross / (1 + rate)).quantize(Decimal("0.01"))
        vat_amount = (expense.amount_gross - amount_net).quantize(Decimal("0.01"))

        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO expenses (
                    date, vendor, description, amount_gross,
                    amount_net, vat_amount, vat_rate, category
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expense.date.isoformat(),
                    expense.vendor,
                    expense.description,
                    str(expense.amount_gross),
                    str(amount_net),
                    str(vat_amount),
                    expense.vat_rate.value,
                    expense.category.value,
                )
            )
            await db.commit()

            return Expense(
                id=cursor.lastrowid,
                **expense.model_dump()
            )

    async def get_by_id(self, expense_id: int) -> Expense | None:
        """Get expense by ID.

        Args:
            expense_id: Expense ID

        Returns:
            Expense or None if not found
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, date, vendor, description, amount_gross,
                       vat_rate, category
                FROM expenses
                WHERE id = ? AND deleted_at IS NULL AND is_storno = FALSE
                """,
                (expense_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return self._row_to_expense(row)

    async def get_all(
        self,
        year: int | None = None,
        category: ExpenseCategory | None = None,
        limit: int = 100,
        offset: int = 0,
        activity_start_date: date | None = None,
    ) -> list[Expense]:
        """Get all expenses with optional filters.

        Args:
            year: Filter by year
            category: Filter by category
            limit: Max results
            offset: Result offset
            activity_start_date: Exclude data before this date

        Returns:
            List of Expense objects
        """
        query = """
            SELECT id, date, vendor, description, amount_gross,
                   vat_rate, category
            FROM expenses
            WHERE deleted_at IS NULL AND is_storno = FALSE
        """
        params: list = []

        if year:
            query += " AND strftime('%Y', date) = ?"
            params.append(str(year))

        if category:
            query += " AND category = ?"
            params.append(category.value)

        if activity_start_date:
            query += " AND date >= ?"
            params.append(activity_start_date.isoformat())

        query += " ORDER BY date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            return [self._row_to_expense(row) for row in rows]

    async def get_by_period(
        self,
        start_date: date,
        end_date: date,
    ) -> list[Expense]:
        """Get expenses within a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of Expense objects
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, date, vendor, description, amount_gross,
                       vat_rate, category
                FROM expenses
                WHERE deleted_at IS NULL AND is_storno = FALSE
                  AND date >= ? AND date <= ?
                ORDER BY date DESC
                """,
                (start_date.isoformat(), end_date.isoformat())
            )
            rows = await cursor.fetchall()

            return [self._row_to_expense(row) for row in rows]

    async def update(self, expense_id: int, expense: ExpenseInput) -> Expense | None:
        """Update an expense.

        Note: For booked transactions, use storno instead.

        Args:
            expense_id: ID to update
            expense: New data

        Returns:
            Updated Expense or None
        """
        rate = Decimal(expense.vat_rate.value)
        amount_net = (expense.amount_gross / (1 + rate)).quantize(Decimal("0.01"))
        vat_amount = (expense.amount_gross - amount_net).quantize(Decimal("0.01"))

        async with self.db.get_connection() as db:
            await db.execute(
                """
                UPDATE expenses SET
                    date = ?, vendor = ?, description = ?,
                    amount_gross = ?, amount_net = ?, vat_amount = ?,
                    vat_rate = ?, category = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    expense.date.isoformat(),
                    expense.vendor,
                    expense.description,
                    str(expense.amount_gross),
                    str(amount_net),
                    str(vat_amount),
                    expense.vat_rate.value,
                    expense.category.value,
                    expense_id,
                )
            )
            await db.commit()

        return await self.get_by_id(expense_id)

    async def delete(self, expense_id: int) -> bool:
        """Soft delete an expense.

        Args:
            expense_id: ID to delete

        Returns:
            True if deleted
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE expenses SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (expense_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_total_by_period(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[Decimal, Decimal]:
        """Get total expenses and Vorsteuer for a period.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Tuple of (total_net, total_vorsteuer)
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT
                    COALESCE(SUM(CAST(amount_net AS REAL)), 0) as total_net,
                    COALESCE(SUM(CAST(vat_amount AS REAL)), 0) as total_vorsteuer
                FROM expenses
                WHERE deleted_at IS NULL AND is_storno = FALSE
                  AND date >= ? AND date <= ?
                """,
                (start_date.isoformat(), end_date.isoformat())
            )
            row = await cursor.fetchone()

            return (
                Decimal(str(row["total_net"])).quantize(Decimal("0.01")),
                Decimal(str(row["total_vorsteuer"])).quantize(Decimal("0.01")),
            )

    def _row_to_expense(self, row) -> Expense:
        """Convert database row to Expense object."""
        return Expense(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            vendor=row["vendor"],
            description=row["description"],
            amount_gross=Decimal(row["amount_gross"]),
            vat_rate=VatRate(row["vat_rate"]),
            category=ExpenseCategory(row["category"]),
        )


class ClientRepository:
    """Repository for client operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    async def create(self, client: ClientInput) -> Client:
        """Create a new client.

        Args:
            client: ClientInput data

        Returns:
            Created Client with ID
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO clients (
                    name, street, address_details, zip_code, city, country,
                    email, phone, vat_id, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client.name,
                    client.street,
                    client.address_details,
                    client.zip_code,
                    client.city,
                    client.country,
                    client.email,
                    client.phone,
                    client.vat_id,
                    client.notes,
                )
            )
            await db.commit()

            return Client(
                id=cursor.lastrowid,
                **client.model_dump()
            )

    async def get_by_id(self, client_id: int) -> Client | None:
        """Get client by ID."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, name, street, address_details, zip_code, city, country,
                       email, phone, vat_id, notes
                FROM clients
                WHERE id = ? AND deleted_at IS NULL
                """,
                (client_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return self._row_to_client(row)

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[Client]:
        """Get all clients.

        Args:
            limit: Max results
            offset: Result offset

        Returns:
            List of Client objects
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, name, street, address_details, zip_code, city, country,
                       email, phone, vat_id, notes
                FROM clients
                WHERE deleted_at IS NULL
                ORDER BY name ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
            rows = await cursor.fetchall()

            return [self._row_to_client(row) for row in rows]

    async def get_for_dropdown(self) -> list[dict]:
        """Get clients for dropdown selection (minimal data).

        Returns:
            List of dicts with id, name, country, vat_id
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, name, city, country, vat_id
                FROM clients
                WHERE deleted_at IS NULL
                ORDER BY name ASC
                """
            )
            rows = await cursor.fetchall()

            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "city": row["city"],
                    "country": row["country"],
                    "vat_id": row["vat_id"],
                }
                for row in rows
            ]

    async def update(self, client_id: int, client: ClientInput) -> Client | None:
        """Update a client.

        Args:
            client_id: ID to update
            client: New data

        Returns:
            Updated Client or None
        """
        async with self.db.get_connection() as db:
            await db.execute(
                """
                UPDATE clients SET
                    name = ?, street = ?, address_details = ?, zip_code = ?,
                    city = ?, country = ?, email = ?, phone = ?, vat_id = ?, notes = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    client.name,
                    client.street,
                    client.address_details,
                    client.zip_code,
                    client.city,
                    client.country,
                    client.email,
                    client.phone,
                    client.vat_id,
                    client.notes,
                    client_id,
                )
            )
            await db.commit()

        return await self.get_by_id(client_id)

    async def delete(self, client_id: int) -> bool:
        """Soft delete a client.

        Args:
            client_id: ID to delete

        Returns:
            True if deleted
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE clients SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (client_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def search(self, query: str, limit: int = 10) -> list[Client]:
        """Search clients by name or city.

        Args:
            query: Search string
            limit: Max results

        Returns:
            List of matching Client objects
        """
        search_pattern = f"%{query}%"
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, name, street, address_details, zip_code, city, country,
                       email, phone, vat_id, notes
                FROM clients
                WHERE deleted_at IS NULL
                  AND (name LIKE ? OR city LIKE ? OR email LIKE ?)
                ORDER BY name ASC
                LIMIT ?
                """,
                (search_pattern, search_pattern, search_pattern, limit)
            )
            rows = await cursor.fetchall()

            return [self._row_to_client(row) for row in rows]

    async def find_by_vat_id(self, vat_id: str) -> Client | None:
        """Find client by VAT ID (exact match).

        Args:
            vat_id: VAT ID to search for (normalized, no spaces)

        Returns:
            Client if found, None otherwise
        """
        # Normalize VAT ID for comparison
        vat_normalized = vat_id.replace(" ", "").upper()
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, name, street, address_details, zip_code, city, country,
                       email, phone, vat_id, notes
                FROM clients
                WHERE deleted_at IS NULL
                  AND UPPER(REPLACE(vat_id, ' ', '')) = ?
                LIMIT 1
                """,
                (vat_normalized,)
            )
            row = await cursor.fetchone()
            return self._row_to_client(row) if row else None

    async def find_matches(
        self,
        name: str | None = None,
        vat_id: str | None = None,
        city: str | None = None,
        limit: int = 5
    ) -> list[tuple[Client, float]]:
        """Find potential client matches with confidence scores.

        Searches by multiple criteria and returns matches with confidence.
        VAT ID match = highest confidence (exact match)
        Name match = high confidence
        City match = lower confidence

        Args:
            name: Client name to match
            vat_id: VAT ID to match
            city: City to match
            limit: Max results

        Returns:
            List of (Client, confidence) tuples, sorted by confidence desc
        """
        matches: dict[int, tuple[Client, float]] = {}

        # Highest priority: VAT ID match (exact)
        if vat_id:
            vat_client = await self.find_by_vat_id(vat_id)
            if vat_client:
                matches[vat_client.id] = (vat_client, 1.0)  # Perfect match

        # High priority: Name match
        if name:
            name_clients = await self.search(name, limit=limit)
            for client in name_clients:
                if client.id not in matches:
                    # Calculate name similarity
                    confidence = self._calculate_name_similarity(name, client.name)
                    if confidence > 0.5:  # Only include reasonable matches
                        matches[client.id] = (client, confidence)
                else:
                    # Already matched by VAT, keep higher confidence
                    pass

        # Lower priority: City match (only if no other matches)
        if city and len(matches) == 0:
            city_clients = await self.search(city, limit=limit)
            for client in city_clients:
                if client.id not in matches:
                    matches[client.id] = (client, 0.3)  # Low confidence

        # Sort by confidence and return
        sorted_matches = sorted(matches.values(), key=lambda x: x[1], reverse=True)
        return sorted_matches[:limit]

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two company names.

        Uses simple word overlap comparison.
        """
        # Normalize names
        words1 = set(name1.lower().split())
        words2 = set(name2.lower().split())

        # Remove common suffixes for comparison
        common_suffixes = {"ltd", "ltd.", "limited", "inc", "inc.", "gmbh", "ag", "ug", "llc", "corp", "corp."}
        words1 = words1 - common_suffixes
        words2 = words2 - common_suffixes

        if not words1 or not words2:
            return 0.0

        # Calculate Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        if union == 0:
            return 0.0

        return intersection / union

    def _row_to_client(self, row) -> Client:
        """Convert database row to Client object."""
        return Client(
            id=row["id"],
            name=row["name"],
            street=row["street"] or "",
            address_details=row["address_details"] or "",
            zip_code=row["zip_code"] or "",
            city=row["city"] or "",
            country=row["country"] or "DE",
            email=row["email"] or "",
            phone=row["phone"] or "",
            vat_id=row["vat_id"] or "",
            notes=row["notes"] or "",
        )


class InvoiceRepository:
    """Repository for invoice operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    async def create(
        self,
        invoice: InvoiceInput,
        client_id: int | None = None,
        uploaded_document_id: int | None = None,
    ) -> Invoice:
        """Create a new invoice.

        Args:
            invoice: InvoiceInput data
            client_id: Optional client ID to link invoice to client
            uploaded_document_id: Optional uploaded document ID to link

        Returns:
            Created Invoice with ID
        """
        # Calculate net and VAT
        rate = Decimal(invoice.vat_rate.value)
        amount_net = (invoice.amount / (1 + rate)).quantize(Decimal("0.01"))
        vat_amount = (invoice.amount - amount_net).quantize(Decimal("0.01"))
        is_reverse_charge = invoice.vat_rate == VatRate.ZERO

        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO invoices (
                    client_id, client, invoice_number, date, due_date, amount,
                    amount_net, vat_amount, vat_rate, description,
                    is_reverse_charge, uploaded_document_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    invoice.client,
                    invoice.invoice_number,
                    invoice.date.isoformat(),
                    invoice.due_date.isoformat() if invoice.due_date else None,
                    str(invoice.amount),
                    str(amount_net),
                    str(vat_amount),
                    invoice.vat_rate.value,
                    invoice.description,
                    is_reverse_charge,
                    uploaded_document_id,
                )
            )
            await db.commit()

            return Invoice(
                id=cursor.lastrowid,
                status=InvoiceStatus.PENDING,
                **invoice.model_dump()
            )

    async def get_by_id(self, invoice_id: int) -> Invoice | None:
        """Get invoice by ID."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT i.id, i.client, i.invoice_number, i.date, i.due_date, i.amount,
                       i.vat_rate, i.description, i.status, i.paid_date,
                       ud.file_path as pdf_path
                FROM invoices i
                LEFT JOIN uploaded_documents ud ON ud.invoice_id = i.id AND ud.deleted_at IS NULL
                WHERE i.id = ? AND i.deleted_at IS NULL AND i.is_storno = FALSE
                """,
                (invoice_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return self._row_to_invoice(row)

    async def get_by_status(
        self,
        status: InvoiceStatus | None = None,
        limit: int = 100,
    ) -> list[Invoice]:
        """Get invoices by status.

        Args:
            status: Filter by status (None for all)
            limit: Max results

        Returns:
            List of Invoice objects
        """
        query = """
            SELECT i.id, i.client, i.invoice_number, i.date, i.due_date, i.amount,
                   i.vat_rate, i.description, i.status, i.paid_date,
                   ud.file_path as pdf_path
            FROM invoices i
            LEFT JOIN uploaded_documents ud ON ud.invoice_id = i.id AND ud.deleted_at IS NULL
            WHERE i.deleted_at IS NULL AND i.is_storno = FALSE
        """
        params: list = []

        if status:
            query += " AND i.status = ?"
            params.append(status.value)

        query += " ORDER BY i.date DESC LIMIT ?"
        params.append(limit)

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            return [self._row_to_invoice(row) for row in rows]

    async def get_by_period(
        self,
        start_date: date,
        end_date: date,
    ) -> list[Invoice]:
        """Get invoices within a date range."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT i.id, i.client, i.invoice_number, i.date, i.due_date, i.amount,
                       i.vat_rate, i.description, i.status, i.paid_date,
                       ud.file_path as pdf_path
                FROM invoices i
                LEFT JOIN uploaded_documents ud ON ud.invoice_id = i.id AND ud.deleted_at IS NULL
                WHERE i.deleted_at IS NULL AND i.is_storno = FALSE
                  AND i.date >= ? AND i.date <= ?
                ORDER BY i.date DESC
                """,
                (start_date.isoformat(), end_date.isoformat())
            )
            rows = await cursor.fetchall()

            return [self._row_to_invoice(row) for row in rows]

    async def mark_paid(
        self,
        invoice_id: int,
        paid_date: date,
    ) -> Invoice | None:
        """Mark invoice as paid.

        Args:
            invoice_id: Invoice ID
            paid_date: Date payment received

        Returns:
            Updated Invoice
        """
        async with self.db.get_connection() as db:
            await db.execute(
                """
                UPDATE invoices SET
                    status = 'paid',
                    paid_date = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (paid_date.isoformat(), invoice_id)
            )
            await db.commit()

        return await self.get_by_id(invoice_id)

    async def update(
        self,
        invoice_id: int,
        client: str,
        invoice_number: str,
        invoice_date: date,
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
            invoice_date: Invoice date
            due_date: Due date
            amount: Net amount
            vat_rate: VAT rate
            description: Description
            status: Invoice status

        Returns:
            Updated Invoice or None
        """
        # Calculate gross and VAT from net amount
        rate = Decimal(vat_rate.value)
        vat_amount = (amount * rate).quantize(Decimal("0.01"))
        amount_gross = amount + vat_amount
        is_reverse_charge = vat_rate == VatRate.ZERO

        async with self.db.get_connection() as db:
            await db.execute(
                """
                UPDATE invoices SET
                    client = ?,
                    invoice_number = ?,
                    date = ?,
                    due_date = ?,
                    amount = ?,
                    amount_net = ?,
                    vat_amount = ?,
                    vat_rate = ?,
                    description = ?,
                    status = ?,
                    is_reverse_charge = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    client,
                    invoice_number,
                    invoice_date.isoformat(),
                    due_date.isoformat() if due_date else None,
                    str(amount_gross),
                    str(amount),
                    str(vat_amount),
                    vat_rate.value,
                    description,
                    status.value,
                    is_reverse_charge,
                    invoice_id,
                )
            )
            await db.commit()

        return await self.get_by_id(invoice_id)

    async def update_overdue(self) -> int:
        """Update status of overdue invoices.

        Returns:
            Number of invoices marked overdue
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE invoices SET status = 'overdue'
                WHERE status = 'pending'
                  AND due_date < date('now')
                  AND deleted_at IS NULL
                """
            )
            await db.commit()
            return cursor.rowcount

    async def get_revenue_by_period(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Get revenue totals for a period.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            Tuple of (total_net, total_vat, reverse_charge_total)
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT
                    COALESCE(SUM(CAST(amount_net AS REAL)), 0) as total_net,
                    COALESCE(SUM(CAST(vat_amount AS REAL)), 0) as total_vat,
                    COALESCE(SUM(CASE WHEN is_reverse_charge
                                 THEN CAST(amount_net AS REAL) ELSE 0 END), 0) as rc_total
                FROM invoices
                WHERE deleted_at IS NULL AND is_storno = FALSE
                  AND date >= ? AND date <= ?
                """,
                (start_date.isoformat(), end_date.isoformat())
            )
            row = await cursor.fetchone()

            return (
                Decimal(str(row["total_net"])).quantize(Decimal("0.01")),
                Decimal(str(row["total_vat"])).quantize(Decimal("0.01")),
                Decimal(str(row["rc_total"])).quantize(Decimal("0.01")),
            )

    async def get_monthly_revenue(
        self,
        year: int,
        activity_start_date: date | None = None,
    ) -> list[tuple[int, Decimal]]:
        """Get monthly net revenue for a year.

        Args:
            year: Year to get revenue for
            activity_start_date: Exclude data before this date

        Returns:
            List of (month, net_revenue) tuples for months with data
        """
        query = """
            SELECT
                CAST(strftime('%m', date) AS INTEGER) as month,
                COALESCE(SUM(CAST(amount_net AS REAL)), 0) as monthly_net
            FROM invoices
            WHERE deleted_at IS NULL AND is_storno = FALSE
              AND strftime('%Y', date) = ?
        """
        params: list = [str(year)]

        if activity_start_date:
            query += " AND date >= ?"
            params.append(activity_start_date.isoformat())

        query += " GROUP BY strftime('%m', date) ORDER BY month ASC"

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, tuple(params))
            rows = await cursor.fetchall()

            return [
                (row["month"], Decimal(str(row["monthly_net"])).quantize(Decimal("0.01")))
                for row in rows
            ]

    async def get_next_invoice_number(self, year: int) -> str:
        """Generate next invoice number for year.

        Format: YYYY-NNN (e.g., 2026-001)

        Args:
            year: Invoice year

        Returns:
            Next invoice number
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT MAX(CAST(SUBSTR(invoice_number, 6) AS INTEGER)) as max_num
                FROM invoices
                WHERE invoice_number LIKE ?
                """,
                (f"{year}-%",)
            )
            row = await cursor.fetchone()
            next_num = (row["max_num"] or 0) + 1

            return f"{year}-{next_num:03d}"

    async def delete(self, invoice_id: int) -> bool:
        """Hard delete an invoice.

        Note: Uses hard delete to free up invoice_number for reuse.
        Audit log captures the deletion event for compliance.

        Args:
            invoice_id: ID to delete

        Returns:
            True if deleted
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM invoices WHERE id = ?",
                (invoice_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    # =========================================================================
    # Client Statistics (for Scheinselbständigkeit detection)
    # =========================================================================

    async def get_stats_by_client(
        self,
        year: int | None = None,
        activity_start_date: date | None = None,
    ) -> list[dict]:
        """Get invoice statistics grouped by client.

        Used for income distribution analysis and Scheinselbständigkeit
        detection (§ 7 SGB IV).

        Args:
            year: Optional year filter
            activity_start_date: Exclude data before this date

        Returns:
            List of dicts with client_id, invoice_count, paid_count,
            total_net, paid_net
        """
        query = """
            SELECT
                client_id,
                COUNT(*) as invoice_count,
                SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) as paid_count,
                COALESCE(SUM(CAST(amount_net AS REAL)), 0) as total_net,
                COALESCE(SUM(CASE WHEN status = 'paid'
                             THEN CAST(amount_net AS REAL) ELSE 0 END), 0) as paid_net
            FROM invoices
            WHERE deleted_at IS NULL AND is_storno = FALSE
        """
        params: list = []

        if year:
            query += " AND strftime('%Y', date) = ?"
            params.append(str(year))

        if activity_start_date:
            query += " AND date >= ?"
            params.append(activity_start_date.isoformat())

        query += " GROUP BY client_id"

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            return [
                {
                    "client_id": row["client_id"],
                    "invoice_count": row["invoice_count"],
                    "paid_count": row["paid_count"],
                    "total_net": str(row["total_net"]),
                    "paid_net": str(row["paid_net"]),
                }
                for row in rows
            ]

    async def get_stats_for_client(
        self,
        client_id: int,
        year: int | None = None,
        activity_start_date: date | None = None,
    ) -> dict:
        """Get invoice statistics for a specific client.

        Args:
            client_id: Client ID
            year: Optional year filter
            activity_start_date: Exclude data before this date

        Returns:
            Dict with invoice_count, paid_count, total_net, paid_net
        """
        query = """
            SELECT
                COUNT(*) as invoice_count,
                SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) as paid_count,
                COALESCE(SUM(CAST(amount_net AS REAL)), 0) as total_net,
                COALESCE(SUM(CASE WHEN status = 'paid'
                             THEN CAST(amount_net AS REAL) ELSE 0 END), 0) as paid_net
            FROM invoices
            WHERE client_id = ? AND deleted_at IS NULL AND is_storno = FALSE
        """
        params: list = [client_id]

        if year:
            query += " AND strftime('%Y', date) = ?"
            params.append(str(year))

        if activity_start_date:
            query += " AND date >= ?"
            params.append(activity_start_date.isoformat())

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()

            return {
                "invoice_count": row["invoice_count"] if row else 0,
                "paid_count": row["paid_count"] if row else 0,
                "total_net": str(row["total_net"]) if row else "0.00",
                "paid_net": str(row["paid_net"]) if row else "0.00",
            }

    def _row_to_invoice(self, row) -> Invoice:
        """Convert database row to Invoice object."""
        return Invoice(
            id=row["id"],
            client=row["client"],
            invoice_number=row["invoice_number"],
            date=date.fromisoformat(row["date"]),
            due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
            amount=Decimal(row["amount"]),
            vat_rate=VatRate(row["vat_rate"]),
            description=row["description"],
            status=InvoiceStatus(row["status"]),
            paid_date=date.fromisoformat(row["paid_date"]) if row["paid_date"] else None,
            pdf_path=row["pdf_path"] if "pdf_path" in row.keys() and row["pdf_path"] else None,
        )


class UploadedDocumentRepository:
    """Repository for uploaded document operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    async def create(
        self,
        filename: str,
        stored_filename: str,
        file_path: str,
        file_size: int,
        content_hash: str,
        mime_type: str = "application/pdf",
    ) -> int:
        """Create a new uploaded document record.

        Args:
            filename: Original filename
            stored_filename: UUID-based storage name
            file_path: Relative path in uploads directory
            file_size: Size in bytes
            content_hash: SHA-256 hash for deduplication
            mime_type: MIME type of the file

        Returns:
            Created document ID
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO uploaded_documents (
                    filename, stored_filename, file_path, file_size,
                    content_hash, mime_type, extraction_status
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (filename, stored_filename, file_path, file_size, content_hash, mime_type)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_by_id(self, doc_id: int) -> dict | None:
        """Get uploaded document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document dict or None if not found
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, filename, stored_filename, file_path, file_size,
                       content_hash, mime_type, extraction_status, extraction_confidence,
                       extraction_method, extracted_data, extraction_errors, invoice_id,
                       uploaded_at, processed_at, confirmed_at
                FROM uploaded_documents
                WHERE id = ? AND deleted_at IS NULL
                """,
                (doc_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return dict(row)

    async def get_by_hash(self, content_hash: str) -> dict | None:
        """Get uploaded document by content hash (for deduplication).

        Args:
            content_hash: SHA-256 hash

        Returns:
            Document dict or None if not found
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, filename, stored_filename, file_path, file_size,
                       content_hash, mime_type, extraction_status, extraction_confidence,
                       extraction_method, extracted_data, invoice_id,
                       uploaded_at, processed_at, confirmed_at
                FROM uploaded_documents
                WHERE content_hash = ? AND deleted_at IS NULL
                """,
                (content_hash,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return dict(row)

    async def update_extraction(
        self,
        doc_id: int,
        status: str,
        confidence: float | None,
        method: str,
        extracted_data: str,
        errors: str | None = None,
    ) -> bool:
        """Update extraction results for a document.

        Args:
            doc_id: Document ID
            status: Extraction status (completed, failed, manual)
            confidence: Overall confidence score (0.0-1.0)
            method: Extraction method used (text, ocr, ai, manual)
            extracted_data: JSON string of extracted data
            errors: JSON string of extraction errors/warnings

        Returns:
            True if updated successfully
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE uploaded_documents SET
                    extraction_status = ?,
                    extraction_confidence = ?,
                    extraction_method = ?,
                    extracted_data = ?,
                    extraction_errors = ?,
                    processed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (status, confidence, method, extracted_data, errors, doc_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def link_to_invoice(self, doc_id: int, invoice_id: int) -> bool:
        """Link uploaded document to created invoice.

        Args:
            doc_id: Document ID
            invoice_id: Invoice ID

        Returns:
            True if linked successfully
        """
        async with self.db.get_connection() as db:
            # Update the document with invoice ID
            cursor = await db.execute(
                """
                UPDATE uploaded_documents SET
                    invoice_id = ?,
                    extraction_status = 'completed',
                    confirmed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (invoice_id, doc_id)
            )

            # Also update the invoice with document ID (reverse link)
            await db.execute(
                """
                UPDATE invoices SET uploaded_document_id = ?
                WHERE id = ?
                """,
                (doc_id, invoice_id)
            )

            await db.commit()
            return cursor.rowcount > 0

    async def get_pending(self, limit: int = 10) -> list[dict]:
        """Get pending documents awaiting processing.

        Args:
            limit: Maximum number of documents to return

        Returns:
            List of document dicts
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, filename, stored_filename, file_path, file_size,
                       content_hash, mime_type, extraction_status,
                       uploaded_at
                FROM uploaded_documents
                WHERE extraction_status = 'pending' AND deleted_at IS NULL
                ORDER BY uploaded_at ASC
                LIMIT ?
                """,
                (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_unconfirmed(self, limit: int = 20) -> list[dict]:
        """Get extracted but unconfirmed documents.

        Args:
            limit: Maximum number of documents to return

        Returns:
            List of document dicts
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, filename, stored_filename, file_path, file_size,
                       content_hash, extraction_status, extraction_confidence,
                       extraction_method, extracted_data, uploaded_at, processed_at
                FROM uploaded_documents
                WHERE extraction_status IN ('completed', 'failed', 'manual')
                  AND invoice_id IS NULL
                  AND deleted_at IS NULL
                ORDER BY processed_at DESC
                LIMIT ?
                """,
                (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def delete(self, doc_id: int) -> bool:
        """Soft delete an uploaded document.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE uploaded_documents SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (doc_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_by_invoice_id(self, invoice_id: int) -> bool:
        """Hard delete uploaded documents linked to an invoice.

        Note: Uses hard delete to allow re-uploading the same file.

        Args:
            invoice_id: Invoice ID

        Returns:
            True if any documents were deleted
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM uploaded_documents WHERE invoice_id = ?",
                (invoice_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def hard_delete(self, doc_id: int) -> str | None:
        """Hard delete a document and return its file path for cleanup.

        Only use this for documents that were never linked to an invoice.

        Args:
            doc_id: Document ID

        Returns:
            File path of deleted document, or None if not found
        """
        async with self.db.get_connection() as db:
            # First get the file path
            cursor = await db.execute(
                """
                SELECT file_path FROM uploaded_documents
                WHERE id = ? AND invoice_id IS NULL
                """,
                (doc_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            file_path = row["file_path"]

            # Delete the record
            await db.execute(
                "DELETE FROM uploaded_documents WHERE id = ? AND invoice_id IS NULL",
                (doc_id,)
            )
            await db.commit()

            return file_path

    async def get_by_invoice_id(self, invoice_id: int) -> dict | None:
        """Get uploaded document by linked invoice ID.

        Args:
            invoice_id: Invoice ID

        Returns:
            Document dict or None if no document is linked
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, filename, stored_filename, file_path, file_size,
                       content_hash, mime_type, extraction_status, extraction_confidence,
                       extraction_method, extracted_data, extraction_errors, invoice_id,
                       uploaded_at, processed_at, confirmed_at
                FROM uploaded_documents
                WHERE invoice_id = ? AND deleted_at IS NULL
                """,
                (invoice_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return dict(row)


class SettingsRepository:
    """Repository for application settings."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    async def get(self, key: str, default: str | None = None) -> str | None:
        """Get setting value by key."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,)
            )
            row = await cursor.fetchone()
            return row["value"] if row else default

    async def set(self, key: str, value: str) -> None:
        """Set or update a setting."""
        async with self.db.get_connection() as db:
            await db.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
                """,
                (key, value, value)
            )
            await db.commit()

    async def get_all(self) -> dict[str, str]:
        """Get all settings as dictionary."""
        async with self.db.get_connection() as db:
            cursor = await db.execute("SELECT key, value FROM settings")
            rows = await cursor.fetchall()
            return {row["key"]: row["value"] for row in rows}


class AssetRepository:
    """Repository for fixed asset (Anlagevermögen) operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    async def create(self, asset: AssetInput) -> Asset:
        """Create a new asset with depreciation schedule.

        Args:
            asset: AssetInput data

        Returns:
            Created Asset with ID
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO assets (
                    name, purchase_date, acquisition_cost, vat_amount, vat_rate,
                    category, useful_life_years, depreciation_method,
                    current_book_value, private_use_percent, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.name,
                    asset.purchase_date.isoformat(),
                    str(asset.acquisition_cost),
                    str(asset.vat_amount),
                    asset.vat_rate.value,
                    asset.category.value,
                    asset.useful_life_years,
                    asset.depreciation_method.value if asset.depreciation_method else "linear",
                    str(asset.acquisition_cost),  # Initial book value = acquisition cost
                    str(asset.private_use_percent),
                    asset.description or "",
                )
            )
            await db.commit()
            asset_id = cursor.lastrowid

            return Asset(
                id=asset_id,
                name=asset.name,
                purchase_date=asset.purchase_date,
                acquisition_cost=asset.acquisition_cost,
                vat_amount=asset.vat_amount,
                vat_rate=asset.vat_rate,
                category=asset.category,
                useful_life_years=asset.useful_life_years,
                depreciation_method=asset.depreciation_method or DepreciationMethod.LINEAR,
                current_book_value=asset.acquisition_cost,
                private_use_percent=asset.private_use_percent,
                description=asset.description,
                depreciation_complete=False,
            )

    async def get_by_id(self, asset_id: int) -> Asset | None:
        """Get asset by ID."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, name, purchase_date, acquisition_cost, vat_amount, vat_rate,
                       category, useful_life_years, depreciation_method, current_book_value,
                       private_use_percent, description, disposal_date, disposal_amount,
                       depreciation_complete
                FROM assets
                WHERE id = ? AND deleted_at IS NULL
                """,
                (asset_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return self._row_to_asset(row)

    async def get_all(
        self,
        year: int | None = None,
        category: AssetCategory | None = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Asset]:
        """Get all assets with optional filters.

        Args:
            year: Filter by purchase year
            category: Filter by category
            active_only: Exclude disposed/fully depreciated assets
            limit: Max results
            offset: Result offset

        Returns:
            List of Asset objects
        """
        query = """
            SELECT id, name, purchase_date, acquisition_cost, vat_amount, vat_rate,
                   category, useful_life_years, depreciation_method, current_book_value,
                   private_use_percent, description, disposal_date, disposal_amount,
                   depreciation_complete
            FROM assets
            WHERE deleted_at IS NULL
        """
        params: list = []

        if year:
            query += " AND strftime('%Y', purchase_date) = ?"
            params.append(str(year))

        if category:
            query += " AND category = ?"
            params.append(category.value)

        if active_only:
            query += " AND disposal_date IS NULL AND depreciation_complete = FALSE"

        query += " ORDER BY purchase_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            return [self._row_to_asset(row) for row in rows]

    async def update_book_value(
        self,
        asset_id: int,
        new_book_value: Decimal,
        depreciation_complete: bool = False,
    ) -> bool:
        """Update asset book value after depreciation.

        Args:
            asset_id: Asset ID
            new_book_value: New book value after depreciation
            depreciation_complete: True if fully depreciated

        Returns:
            True if updated
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE assets SET
                    current_book_value = ?,
                    depreciation_complete = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (str(new_book_value), depreciation_complete, asset_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def dispose(
        self,
        asset_id: int,
        disposal_date: date,
        disposal_amount: Decimal,
    ) -> Asset | None:
        """Record asset disposal.

        Args:
            asset_id: Asset ID
            disposal_date: Date of disposal
            disposal_amount: Sale proceeds

        Returns:
            Updated Asset
        """
        async with self.db.get_connection() as db:
            await db.execute(
                """
                UPDATE assets SET
                    disposal_date = ?,
                    disposal_amount = ?,
                    depreciation_complete = TRUE
                WHERE id = ? AND deleted_at IS NULL
                """,
                (disposal_date.isoformat(), str(disposal_amount), asset_id)
            )
            await db.commit()

        return await self.get_by_id(asset_id)

    async def create_depreciation_record(
        self,
        record: DepreciationRecord,
    ) -> DepreciationRecord:
        """Create a depreciation record for an asset.

        Args:
            record: DepreciationRecord data

        Returns:
            Created record with ID
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO depreciation_records (
                    asset_id, year, depreciation_amount, book_value_start,
                    book_value_end, method_applied, months_applicable, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.asset_id,
                    record.year,
                    str(record.depreciation_amount),
                    str(record.book_value_start),
                    str(record.book_value_end),
                    record.method_applied.value,
                    record.months_applicable,
                    record.notes or "",
                )
            )
            await db.commit()

            return DepreciationRecord(
                id=cursor.lastrowid,
                asset_id=record.asset_id,
                year=record.year,
                depreciation_amount=record.depreciation_amount,
                book_value_start=record.book_value_start,
                book_value_end=record.book_value_end,
                method_applied=record.method_applied,
                months_applicable=record.months_applicable,
                notes=record.notes,
            )

    async def get_depreciation_records(
        self,
        asset_id: int,
    ) -> list[DepreciationRecord]:
        """Get all depreciation records for an asset.

        Args:
            asset_id: Asset ID

        Returns:
            List of DepreciationRecord objects
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, asset_id, year, depreciation_amount, book_value_start,
                       book_value_end, method_applied, months_applicable, notes
                FROM depreciation_records
                WHERE asset_id = ?
                ORDER BY year ASC
                """,
                (asset_id,)
            )
            rows = await cursor.fetchall()

            return [
                DepreciationRecord(
                    id=row["id"],
                    asset_id=row["asset_id"],
                    year=row["year"],
                    depreciation_amount=Decimal(row["depreciation_amount"]),
                    book_value_start=Decimal(row["book_value_start"]),
                    book_value_end=Decimal(row["book_value_end"]),
                    method_applied=DepreciationMethod(row["method_applied"]),
                    months_applicable=row["months_applicable"],
                    notes=row["notes"] or None,
                )
                for row in rows
            ]

    async def get_annual_depreciation(
        self,
        year: int,
    ) -> Decimal:
        """Get total depreciation for a year across all assets.

        Args:
            year: Tax year

        Returns:
            Total depreciation amount
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(CAST(depreciation_amount AS REAL)), 0) as total
                FROM depreciation_records
                WHERE year = ?
                """,
                (year,)
            )
            row = await cursor.fetchone()
            return Decimal(str(row["total"])).quantize(Decimal("0.01"))

    async def delete(self, asset_id: int) -> bool:
        """Soft delete an asset.

        Args:
            asset_id: ID to delete

        Returns:
            True if deleted
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE assets SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (asset_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    def _row_to_asset(self, row) -> Asset:
        """Convert database row to Asset object."""
        return Asset(
            id=row["id"],
            name=row["name"],
            purchase_date=date.fromisoformat(row["purchase_date"]),
            acquisition_cost=Decimal(row["acquisition_cost"]),
            vat_amount=Decimal(row["vat_amount"]),
            vat_rate=VatRate(row["vat_rate"]),
            category=AssetCategory(row["category"]),
            useful_life_years=row["useful_life_years"],
            depreciation_method=DepreciationMethod(row["depreciation_method"]),
            current_book_value=Decimal(row["current_book_value"]),
            private_use_percent=Decimal(row["private_use_percent"]),
            description=row["description"] or None,
            disposal_date=date.fromisoformat(row["disposal_date"]) if row["disposal_date"] else None,
            disposal_amount=Decimal(row["disposal_amount"]) if row["disposal_amount"] else None,
            depreciation_complete=bool(row["depreciation_complete"]),
        )


class TravelExpenseRepository:
    """Repository for travel expense (Reisekosten) operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    async def create(self, travel: TravelExpenseInput, calculated: TravelExpense) -> TravelExpense:
        """Create a new travel expense with calculated deductions.

        Args:
            travel: TravelExpenseInput data
            calculated: Pre-calculated TravelExpense with deductions

        Returns:
            Created TravelExpense with ID
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO travel_expenses (
                    date, destination, purpose, departure_time, return_time,
                    absence_hours, is_overnight, is_travel_day, km_driven,
                    km_rate, km_deduction, country_code, per_diem_rate,
                    meal_reduction, per_diem_deduction, total_deduction,
                    breakfast_provided, lunch_provided, dinner_provided
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    travel.date.isoformat(),
                    travel.destination,
                    travel.purpose,
                    travel.departure_time,
                    travel.return_time,
                    str(travel.absence_hours),
                    travel.is_overnight,
                    travel.is_travel_day,
                    str(travel.km_driven),
                    str(calculated.km_rate),
                    str(calculated.km_deduction),
                    travel.country_code,
                    str(calculated.per_diem_rate),
                    str(calculated.meal_reduction),
                    str(calculated.per_diem_deduction),
                    str(calculated.total_deduction),
                    travel.breakfast_provided,
                    travel.lunch_provided,
                    travel.dinner_provided,
                )
            )
            await db.commit()

            return TravelExpense(
                id=cursor.lastrowid,
                date=travel.date,
                destination=travel.destination,
                purpose=travel.purpose,
                departure_time=travel.departure_time,
                return_time=travel.return_time,
                absence_hours=travel.absence_hours,
                is_overnight=travel.is_overnight,
                is_travel_day=travel.is_travel_day,
                km_driven=travel.km_driven,
                km_rate=calculated.km_rate,
                km_deduction=calculated.km_deduction,
                country_code=travel.country_code,
                per_diem_rate=calculated.per_diem_rate,
                meal_reduction=calculated.meal_reduction,
                per_diem_deduction=calculated.per_diem_deduction,
                total_deduction=calculated.total_deduction,
                breakfast_provided=travel.breakfast_provided,
                lunch_provided=travel.lunch_provided,
                dinner_provided=travel.dinner_provided,
            )

    async def get_by_id(self, travel_id: int) -> TravelExpense | None:
        """Get travel expense by ID."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, date, destination, purpose, departure_time, return_time,
                       absence_hours, is_overnight, is_travel_day, km_driven,
                       km_rate, km_deduction, country_code, per_diem_rate,
                       meal_reduction, per_diem_deduction, total_deduction,
                       breakfast_provided, lunch_provided, dinner_provided
                FROM travel_expenses
                WHERE id = ? AND deleted_at IS NULL
                """,
                (travel_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return self._row_to_travel_expense(row)

    async def get_all(
        self,
        year: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TravelExpense]:
        """Get all travel expenses with optional filters.

        Args:
            year: Filter by year
            limit: Max results
            offset: Result offset

        Returns:
            List of TravelExpense objects
        """
        query = """
            SELECT id, date, destination, purpose, departure_time, return_time,
                   absence_hours, is_overnight, is_travel_day, km_driven,
                   km_rate, km_deduction, country_code, per_diem_rate,
                   meal_reduction, per_diem_deduction, total_deduction,
                   breakfast_provided, lunch_provided, dinner_provided
            FROM travel_expenses
            WHERE deleted_at IS NULL
        """
        params: list = []

        if year:
            query += " AND strftime('%Y', date) = ?"
            params.append(str(year))

        query += " ORDER BY date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            return [self._row_to_travel_expense(row) for row in rows]

    async def get_by_period(
        self,
        start_date: date,
        end_date: date,
    ) -> list[TravelExpense]:
        """Get travel expenses within a date range."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, date, destination, purpose, departure_time, return_time,
                       absence_hours, is_overnight, is_travel_day, km_driven,
                       km_rate, km_deduction, country_code, per_diem_rate,
                       meal_reduction, per_diem_deduction, total_deduction,
                       breakfast_provided, lunch_provided, dinner_provided
                FROM travel_expenses
                WHERE deleted_at IS NULL AND date >= ? AND date <= ?
                ORDER BY date DESC
                """,
                (start_date.isoformat(), end_date.isoformat())
            )
            rows = await cursor.fetchall()

            return [self._row_to_travel_expense(row) for row in rows]

    async def get_annual_totals(
        self,
        year: int,
    ) -> dict:
        """Get annual travel expense totals.

        Args:
            year: Tax year

        Returns:
            Dict with per_diem_total, km_total, total_deduction
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT
                    COALESCE(SUM(CAST(per_diem_deduction AS REAL)), 0) as per_diem_total,
                    COALESCE(SUM(CAST(km_deduction AS REAL)), 0) as km_total,
                    COALESCE(SUM(CAST(total_deduction AS REAL)), 0) as total
                FROM travel_expenses
                WHERE deleted_at IS NULL AND strftime('%Y', date) = ?
                """,
                (str(year),)
            )
            row = await cursor.fetchone()

            return {
                "per_diem_total": Decimal(str(row["per_diem_total"])).quantize(Decimal("0.01")),
                "km_total": Decimal(str(row["km_total"])).quantize(Decimal("0.01")),
                "total_deduction": Decimal(str(row["total"])).quantize(Decimal("0.01")),
            }

    async def delete(self, travel_id: int) -> bool:
        """Soft delete a travel expense."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE travel_expenses SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (travel_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    def _row_to_travel_expense(self, row) -> TravelExpense:
        """Convert database row to TravelExpense object."""
        return TravelExpense(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            destination=row["destination"],
            purpose=row["purpose"],
            departure_time=row["departure_time"],
            return_time=row["return_time"],
            absence_hours=Decimal(row["absence_hours"]),
            is_overnight=bool(row["is_overnight"]),
            is_travel_day=bool(row["is_travel_day"]),
            km_driven=Decimal(row["km_driven"]),
            km_rate=Decimal(row["km_rate"]),
            km_deduction=Decimal(row["km_deduction"]),
            country_code=row["country_code"],
            per_diem_rate=Decimal(row["per_diem_rate"]),
            meal_reduction=Decimal(row["meal_reduction"]),
            per_diem_deduction=Decimal(row["per_diem_deduction"]),
            total_deduction=Decimal(row["total_deduction"]),
            breakfast_provided=bool(row["breakfast_provided"]),
            lunch_provided=bool(row["lunch_provided"]),
            dinner_provided=bool(row["dinner_provided"]),
        )


class GiftExpenseRepository:
    """Repository for gift expense (Geschenke) operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    async def create(self, gift: GiftExpense) -> GiftExpense:
        """Create a new gift expense.

        Args:
            gift: GiftExpense with calculated deductibility

        Returns:
            Created GiftExpense with ID
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO gift_expenses (
                    date, recipient_name, recipient_company, description,
                    amount_net, vat_rate, flat_tax_paid, is_deductible,
                    cumulative_year_total, expense_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gift.date.isoformat(),
                    gift.recipient_name,
                    gift.recipient_company or "",
                    gift.description,
                    str(gift.amount_net),
                    gift.vat_rate.value,
                    gift.flat_tax_paid,
                    gift.is_deductible,
                    str(gift.cumulative_year_total),
                    gift.expense_id,
                )
            )
            await db.commit()

            return GiftExpense(
                id=cursor.lastrowid,
                date=gift.date,
                recipient_name=gift.recipient_name,
                recipient_company=gift.recipient_company,
                description=gift.description,
                amount_net=gift.amount_net,
                vat_rate=gift.vat_rate,
                flat_tax_paid=gift.flat_tax_paid,
                is_deductible=gift.is_deductible,
                cumulative_year_total=gift.cumulative_year_total,
                expense_id=gift.expense_id,
            )

    async def get_by_id(self, gift_id: int) -> GiftExpense | None:
        """Get gift expense by ID."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, date, recipient_name, recipient_company, description,
                       amount_net, vat_rate, flat_tax_paid, is_deductible,
                       cumulative_year_total, expense_id
                FROM gift_expenses
                WHERE id = ? AND deleted_at IS NULL
                """,
                (gift_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return self._row_to_gift_expense(row)

    async def get_all(
        self,
        year: int | None = None,
        recipient_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GiftExpense]:
        """Get all gift expenses with optional filters.

        Args:
            year: Filter by year
            recipient_name: Filter by recipient
            limit: Max results
            offset: Result offset

        Returns:
            List of GiftExpense objects
        """
        query = """
            SELECT id, date, recipient_name, recipient_company, description,
                   amount_net, vat_rate, flat_tax_paid, is_deductible,
                   cumulative_year_total, expense_id
            FROM gift_expenses
            WHERE deleted_at IS NULL
        """
        params: list = []

        if year:
            query += " AND strftime('%Y', date) = ?"
            params.append(str(year))

        if recipient_name:
            query += " AND LOWER(recipient_name) = LOWER(?)"
            params.append(recipient_name)

        query += " ORDER BY date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            return [self._row_to_gift_expense(row) for row in rows]

    async def get_recipient_total(
        self,
        recipient_name: str,
        year: int,
    ) -> Decimal:
        """Get total gifts to a recipient for a year.

        Args:
            recipient_name: Recipient name (case-insensitive)
            year: Tax year

        Returns:
            Total net gift amount
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(CAST(amount_net AS REAL)), 0) as total
                FROM gift_expenses
                WHERE deleted_at IS NULL
                  AND LOWER(recipient_name) = LOWER(?)
                  AND strftime('%Y', date) = ?
                """,
                (recipient_name, str(year))
            )
            row = await cursor.fetchone()
            return Decimal(str(row["total"])).quantize(Decimal("0.01"))

    async def get_gifts_to_recipient(
        self,
        recipient_name: str,
        year: int,
    ) -> list[GiftExpense]:
        """Get all gifts to a specific recipient in a year.

        Args:
            recipient_name: Recipient name
            year: Tax year

        Returns:
            List of GiftExpense objects sorted by date
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, date, recipient_name, recipient_company, description,
                       amount_net, vat_rate, flat_tax_paid, is_deductible,
                       cumulative_year_total, expense_id
                FROM gift_expenses
                WHERE deleted_at IS NULL
                  AND LOWER(recipient_name) = LOWER(?)
                  AND strftime('%Y', date) = ?
                ORDER BY date ASC
                """,
                (recipient_name, str(year))
            )
            rows = await cursor.fetchall()

            return [self._row_to_gift_expense(row) for row in rows]

    async def get_recipient_summaries(
        self,
        year: int,
    ) -> list[GiftRecipientSummary]:
        """Get gift summaries grouped by recipient for a year.

        Args:
            year: Tax year

        Returns:
            List of GiftRecipientSummary objects
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT
                    recipient_name,
                    recipient_company,
                    COUNT(*) as gift_count,
                    SUM(CAST(amount_net AS REAL)) as total_net
                FROM gift_expenses
                WHERE deleted_at IS NULL AND strftime('%Y', date) = ?
                GROUP BY LOWER(recipient_name)
                ORDER BY total_net DESC
                """,
                (str(year),)
            )
            rows = await cursor.fetchall()

            from src.core.models import GIFT_LIMIT_PER_RECIPIENT

            summaries = []
            for row in rows:
                total = Decimal(str(row["total_net"])).quantize(Decimal("0.01"))
                is_over = total > GIFT_LIMIT_PER_RECIPIENT
                remaining = max(GIFT_LIMIT_PER_RECIPIENT - total, Decimal("0"))

                summaries.append(GiftRecipientSummary(
                    recipient_name=row["recipient_name"],
                    recipient_company=row["recipient_company"] or None,
                    year=year,
                    gift_count=row["gift_count"],
                    total_net=total,
                    is_over_limit=is_over,
                    remaining_allowance=remaining,
                ))

            return summaries

    async def update_deductibility(
        self,
        gift_id: int,
        is_deductible: bool,
        cumulative_total: Decimal,
    ) -> bool:
        """Update gift deductibility (for retroactive cliff effect).

        Args:
            gift_id: Gift ID
            is_deductible: New deductibility status
            cumulative_total: New cumulative total

        Returns:
            True if updated
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE gift_expenses SET
                    is_deductible = ?,
                    cumulative_year_total = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (is_deductible, str(cumulative_total), gift_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_unique_recipients(self) -> list[str]:
        """Get list of unique recipient names for autocomplete.

        Returns:
            List of unique recipient names
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT DISTINCT recipient_name
                FROM gift_expenses
                WHERE deleted_at IS NULL
                ORDER BY recipient_name ASC
                """
            )
            rows = await cursor.fetchall()
            return [row["recipient_name"] for row in rows]

    async def delete(self, gift_id: int) -> bool:
        """Soft delete a gift expense."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE gift_expenses SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (gift_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    def _row_to_gift_expense(self, row) -> GiftExpense:
        """Convert database row to GiftExpense object."""
        return GiftExpense(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            recipient_name=row["recipient_name"],
            recipient_company=row["recipient_company"] or None,
            description=row["description"],
            amount_net=Decimal(row["amount_net"]),
            vat_rate=VatRate(row["vat_rate"]),
            flat_tax_paid=bool(row["flat_tax_paid"]),
            is_deductible=bool(row["is_deductible"]),
            cumulative_year_total=Decimal(row["cumulative_year_total"]),
            expense_id=row["expense_id"],
        )


class HomeOfficeRepository:
    """Repository for home office (Homeoffice) operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    # =========================================================================
    # Settings Management
    # =========================================================================

    async def get_settings(self, year: int) -> HomeOfficeSettings | None:
        """Get home office settings for a year.

        Args:
            year: Tax year

        Returns:
            HomeOfficeSettings or None if not configured
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, year, method_type, room_sqm, total_sqm,
                       monthly_rent, monthly_utilities
                FROM home_office_settings
                WHERE year = ?
                """,
                (year,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return HomeOfficeSettings(
                id=row["id"],
                year=row["year"],
                method_type=HomeOfficeType(row["method_type"]),
                room_sqm=Decimal(row["room_sqm"]) if row["room_sqm"] else None,
                total_sqm=Decimal(row["total_sqm"]) if row["total_sqm"] else None,
                monthly_rent=Decimal(row["monthly_rent"]) if row["monthly_rent"] else None,
                monthly_utilities=Decimal(row["monthly_utilities"]) if row["monthly_utilities"] else None,
            )

    async def save_settings(self, settings: HomeOfficeSettings) -> HomeOfficeSettings:
        """Save or update home office settings.

        Args:
            settings: HomeOfficeSettings data

        Returns:
            Saved settings with ID
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO home_office_settings (
                    year, method_type, room_sqm, total_sqm,
                    monthly_rent, monthly_utilities
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(year) DO UPDATE SET
                    method_type = excluded.method_type,
                    room_sqm = excluded.room_sqm,
                    total_sqm = excluded.total_sqm,
                    monthly_rent = excluded.monthly_rent,
                    monthly_utilities = excluded.monthly_utilities,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    settings.year,
                    settings.method_type.value,
                    str(settings.room_sqm) if settings.room_sqm else None,
                    str(settings.total_sqm) if settings.total_sqm else None,
                    str(settings.monthly_rent) if settings.monthly_rent else None,
                    str(settings.monthly_utilities) if settings.monthly_utilities else None,
                )
            )
            await db.commit()

            # Get the ID
            cursor = await db.execute(
                "SELECT id FROM home_office_settings WHERE year = ?",
                (settings.year,)
            )
            row = await cursor.fetchone()

            return HomeOfficeSettings(
                id=row["id"],
                year=settings.year,
                method_type=settings.method_type,
                room_sqm=settings.room_sqm,
                total_sqm=settings.total_sqm,
                monthly_rent=settings.monthly_rent,
                monthly_utilities=settings.monthly_utilities,
            )

    # =========================================================================
    # Day Tracking
    # =========================================================================

    async def add_day(self, day: HomeOfficeDayInput) -> HomeOfficeDay:
        """Add a home office day.

        Args:
            day: HomeOfficeDayInput data

        Returns:
            Created HomeOfficeDay with ID
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO home_office_days (date, hours, notes)
                VALUES (?, ?, ?)
                """,
                (
                    day.date.isoformat(),
                    str(day.hours) if day.hours else None,
                    day.notes or "",
                )
            )
            await db.commit()

            return HomeOfficeDay(
                id=cursor.lastrowid,
                date=day.date,
                hours=day.hours,
                notes=day.notes,
            )

    async def get_day(self, day_date: date) -> HomeOfficeDay | None:
        """Get home office day by date.

        Args:
            day_date: Date to look up

        Returns:
            HomeOfficeDay or None
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, date, hours, notes
                FROM home_office_days
                WHERE date = ? AND deleted_at IS NULL
                """,
                (day_date.isoformat(),)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return HomeOfficeDay(
                id=row["id"],
                date=date.fromisoformat(row["date"]),
                hours=Decimal(row["hours"]) if row["hours"] else None,
                notes=row["notes"] or None,
            )

    async def get_days_by_month(
        self,
        year: int,
        month: int,
    ) -> list[HomeOfficeDay]:
        """Get all home office days for a month.

        Args:
            year: Year
            month: Month (1-12)

        Returns:
            List of HomeOfficeDay objects
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, date, hours, notes
                FROM home_office_days
                WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
                  AND deleted_at IS NULL
                ORDER BY date ASC
                """,
                (str(year), f"{month:02d}")
            )
            rows = await cursor.fetchall()

            return [
                HomeOfficeDay(
                    id=row["id"],
                    date=date.fromisoformat(row["date"]),
                    hours=Decimal(row["hours"]) if row["hours"] else None,
                    notes=row["notes"] or None,
                )
                for row in rows
            ]

    async def get_day_count(self, year: int) -> int:
        """Get total home office days for a year.

        Args:
            year: Tax year

        Returns:
            Number of days
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM home_office_days
                WHERE strftime('%Y', date) = ? AND deleted_at IS NULL
                """,
                (str(year),)
            )
            row = await cursor.fetchone()
            return row["count"]

    async def delete_day(self, day_date: date) -> bool:
        """Soft delete a home office day.

        Args:
            day_date: Date to delete

        Returns:
            True if deleted
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE home_office_days SET deleted_at = CURRENT_TIMESTAMP
                WHERE date = ? AND deleted_at IS NULL
                """,
                (day_date.isoformat(),)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def has_commute_on_date(self, check_date: date) -> bool:
        """Check if there's a commute expense on a given date.

        Used to prevent claiming both home office and commute on same day.

        Args:
            check_date: Date to check

        Returns:
            True if commute expense exists
        """
        async with self.db.get_connection() as db:
            # Check travel expenses for commutes on this date
            cursor = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM travel_expenses
                WHERE date = ? AND deleted_at IS NULL
                  AND destination LIKE '%→%'
                """,
                (check_date.isoformat(),)
            )
            row = await cursor.fetchone()
            return row["count"] > 0


class BusinessMealRepository:
    """Repository for business meal (Bewirtungskosten) operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    async def create(self, meal: BusinessMealInput) -> BusinessMeal:
        """Create a new business meal expense.

        Args:
            meal: BusinessMealInput data

        Returns:
            Created BusinessMeal with ID
        """
        # Calculate deductible amount
        # External guests: 70% deductible
        # Internal only: 100% but capped at 110 EUR per person
        attendee_count = len(meal.attendees.split(",")) if meal.attendees else 1

        if meal.is_internal:
            # Staff event: 100% up to 110 EUR per person
            cap = Decimal("110") * attendee_count
            deductible = min(meal.amount_gross, cap)
            deduction_rate = Decimal("1.00")
        else:
            # Client entertainment: 70%
            deductible = (meal.amount_gross * Decimal("0.70")).quantize(Decimal("0.01"))
            deduction_rate = Decimal("0.70")

        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO business_meals (
                    date, restaurant, amount_gross, vat_rate, attendees,
                    business_purpose, is_internal, deductible_amount, expense_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meal.date.isoformat(),
                    meal.restaurant,
                    str(meal.amount_gross),
                    meal.vat_rate.value,
                    meal.attendees,
                    meal.business_purpose,
                    meal.is_internal,
                    str(deductible),
                    meal.expense_id,
                )
            )
            await db.commit()

            return BusinessMeal(
                id=cursor.lastrowid,
                date=meal.date,
                restaurant=meal.restaurant,
                amount_gross=meal.amount_gross,
                vat_rate=meal.vat_rate,
                attendees=meal.attendees,
                business_purpose=meal.business_purpose,
                is_internal=meal.is_internal,
                deductible_amount=deductible,
                expense_id=meal.expense_id,
            )

    async def get_by_id(self, meal_id: int) -> BusinessMeal | None:
        """Get business meal by ID."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, date, restaurant, amount_gross, vat_rate, attendees,
                       business_purpose, is_internal, deductible_amount, expense_id
                FROM business_meals
                WHERE id = ? AND deleted_at IS NULL
                """,
                (meal_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return self._row_to_business_meal(row)

    async def get_all(
        self,
        year: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BusinessMeal]:
        """Get all business meals with optional filters.

        Args:
            year: Filter by year
            limit: Max results
            offset: Result offset

        Returns:
            List of BusinessMeal objects
        """
        query = """
            SELECT id, date, restaurant, amount_gross, vat_rate, attendees,
                   business_purpose, is_internal, deductible_amount, expense_id
            FROM business_meals
            WHERE deleted_at IS NULL
        """
        params: list = []

        if year:
            query += " AND strftime('%Y', date) = ?"
            params.append(str(year))

        query += " ORDER BY date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            return [self._row_to_business_meal(row) for row in rows]

    async def get_annual_totals(
        self,
        year: int,
    ) -> dict:
        """Get annual business meal totals.

        Args:
            year: Tax year

        Returns:
            Dict with total_gross, total_deductible, internal_count, external_count
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT
                    COALESCE(SUM(CAST(amount_gross AS REAL)), 0) as total_gross,
                    COALESCE(SUM(CAST(deductible_amount AS REAL)), 0) as total_deductible,
                    SUM(CASE WHEN is_internal THEN 1 ELSE 0 END) as internal_count,
                    SUM(CASE WHEN NOT is_internal THEN 1 ELSE 0 END) as external_count
                FROM business_meals
                WHERE deleted_at IS NULL AND strftime('%Y', date) = ?
                """,
                (str(year),)
            )
            row = await cursor.fetchone()

            return {
                "total_gross": Decimal(str(row["total_gross"])).quantize(Decimal("0.01")),
                "total_deductible": Decimal(str(row["total_deductible"])).quantize(Decimal("0.01")),
                "internal_count": row["internal_count"] or 0,
                "external_count": row["external_count"] or 0,
            }

    async def delete(self, meal_id: int) -> bool:
        """Soft delete a business meal."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE business_meals SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (meal_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    def _row_to_business_meal(self, row) -> BusinessMeal:
        """Convert database row to BusinessMeal object."""
        return BusinessMeal(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            restaurant=row["restaurant"],
            amount_gross=Decimal(row["amount_gross"]),
            vat_rate=VatRate(row["vat_rate"]),
            attendees=row["attendees"],
            business_purpose=row["business_purpose"],
            is_internal=bool(row["is_internal"]),
            deductible_amount=Decimal(row["deductible_amount"]),
            expense_id=row["expense_id"],
        )


class HealthInsuranceProviderRepository:
    """Repository for health insurance provider (static data) operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager

    async def get_all(
        self,
        type_filter: InsuranceType | None = None,
        search: str | None = None,
    ) -> list[HealthInsuranceProvider]:
        """Get all insurance providers with optional filters.

        Args:
            type_filter: Filter by GKV or PKV
            search: Search by name

        Returns:
            List of HealthInsuranceProvider objects
        """
        query = "SELECT * FROM health_insurance_providers WHERE 1=1"
        params: list = []

        if type_filter:
            query += " AND type = ?"
            params.append(type_filter.value)

        if search:
            query += " AND (name LIKE ? OR short_name LIKE ?)"
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])

        query += " ORDER BY type, name"

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            return [self._row_to_provider(row) for row in rows]

    async def get_by_id(self, provider_id: int) -> HealthInsuranceProvider | None:
        """Get provider by ID."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM health_insurance_providers WHERE id = ?",
                (provider_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return self._row_to_provider(row)

    async def get_by_type(
        self,
        insurance_type: InsuranceType,
    ) -> list[HealthInsuranceProvider]:
        """Get providers by type (GKV or PKV)."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT * FROM health_insurance_providers
                WHERE type = ?
                ORDER BY name
                """,
                (insurance_type.value,)
            )
            rows = await cursor.fetchall()

            return [self._row_to_provider(row) for row in rows]

    def _row_to_provider(self, row) -> HealthInsuranceProvider:
        """Convert database row to HealthInsuranceProvider object."""
        return HealthInsuranceProvider(
            id=row["id"],
            name=row["name"],
            short_name=row["short_name"],
            type=InsuranceType(row["type"]),
            logo_filename=row["logo_filename"],
            website=row["website"],
            is_nationwide=bool(row["is_nationwide"]),
        )


class HealthInsuranceRepository:
    """Repository for health insurance payment (Krankenversicherungsbeiträge) operations."""

    def __init__(self, db_manager: DatabaseManager = db_manager):
        self.db = db_manager
        self.provider_repo = HealthInsuranceProviderRepository(db_manager)

    async def create(self, payment: HealthInsuranceInput) -> HealthInsurance:
        """Create a new health insurance payment record.

        Args:
            payment: HealthInsuranceInput data

        Returns:
            Created HealthInsurance with ID
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO health_insurance (
                    date, provider_id, insurance_type, coverage_type,
                    amount, has_krankengeld, policy_number, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payment.date.isoformat(),
                    payment.provider_id,
                    payment.insurance_type.value,
                    payment.coverage_type.value,
                    str(payment.amount),
                    payment.has_krankengeld,
                    payment.policy_number,
                    payment.notes,
                )
            )
            await db.commit()

            # Get provider for the returned object
            provider = await self.provider_repo.get_by_id(payment.provider_id)

            return HealthInsurance(
                id=cursor.lastrowid,
                provider=provider,
                **payment.model_dump()
            )

    async def get_by_id(self, payment_id: int) -> HealthInsurance | None:
        """Get payment by ID."""
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, date, provider_id, insurance_type, coverage_type,
                       amount, has_krankengeld, policy_number, notes
                FROM health_insurance
                WHERE id = ? AND deleted_at IS NULL AND is_storno = FALSE
                """,
                (payment_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return await self._row_to_health_insurance(row)

    async def get_all(
        self,
        year: int | None = None,
        insurance_type: InsuranceType | None = None,
        coverage_type: CoverageType | None = None,
        provider_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HealthInsurance]:
        """Get all payments with optional filters.

        Args:
            year: Filter by year
            insurance_type: Filter by GKV or PKV
            coverage_type: Filter by coverage type
            provider_id: Filter by provider
            limit: Max results
            offset: Result offset

        Returns:
            List of HealthInsurance objects
        """
        query = """
            SELECT id, date, provider_id, insurance_type, coverage_type,
                   amount, has_krankengeld, policy_number, notes
            FROM health_insurance
            WHERE deleted_at IS NULL AND is_storno = FALSE
        """
        params: list = []

        if year:
            query += " AND strftime('%Y', date) = ?"
            params.append(str(year))

        if insurance_type:
            query += " AND insurance_type = ?"
            params.append(insurance_type.value)

        if coverage_type:
            query += " AND coverage_type = ?"
            params.append(coverage_type.value)

        if provider_id:
            query += " AND provider_id = ?"
            params.append(provider_id)

        query += " ORDER BY date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            payments = []
            for row in rows:
                payment = await self._row_to_health_insurance(row)
                payments.append(payment)
            return payments

    async def get_by_year(self, year: int) -> list[HealthInsurance]:
        """Get all payments for a specific year.

        Args:
            year: Tax year

        Returns:
            List of HealthInsurance objects
        """
        return await self.get_all(year=year, limit=1000)

    async def get_annual_totals(self, year: int) -> dict:
        """Get annual totals by category.

        Args:
            year: Tax year

        Returns:
            Dict with totals by coverage type
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT
                    coverage_type,
                    COALESCE(SUM(CAST(amount AS REAL)), 0) as total,
                    COUNT(*) as count
                FROM health_insurance
                WHERE deleted_at IS NULL
                  AND is_storno = FALSE
                  AND strftime('%Y', date) = ?
                GROUP BY coverage_type
                """,
                (str(year),)
            )
            rows = await cursor.fetchall()

            totals = {
                "basis_krankenversicherung": Decimal("0"),
                "pflegepflichtversicherung": Decimal("0"),
                "wahlleistungen": Decimal("0"),
                "zusatzversicherung": Decimal("0"),
                "total": Decimal("0"),
                "count": 0,
            }

            for row in rows:
                coverage = row["coverage_type"]
                amount = Decimal(str(row["total"])).quantize(Decimal("0.01"))
                totals[coverage] = amount
                totals["total"] += amount
                totals["count"] += row["count"]

            return totals

    async def delete(self, payment_id: int) -> bool:
        """Soft delete a payment.

        Args:
            payment_id: ID to delete

        Returns:
            True if deleted
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE health_insurance SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (payment_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def storno(self, payment_id: int) -> HealthInsurance | None:
        """Create a storno (reversal) record for a payment.

        Args:
            payment_id: ID of payment to reverse

        Returns:
            Created storno HealthInsurance
        """
        original = await self.get_by_id(payment_id)
        if not original:
            return None

        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO health_insurance (
                    date, provider_id, insurance_type, coverage_type,
                    amount, has_krankengeld, policy_number, notes,
                    storno_of, is_storno
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE)
                """,
                (
                    date.today().isoformat(),
                    original.provider_id,
                    original.insurance_type.value,
                    original.coverage_type.value,
                    str(-original.amount),  # Negative amount
                    original.has_krankengeld,
                    original.policy_number,
                    f"Storno of #{payment_id}",
                    payment_id,
                )
            )
            await db.commit()

            return await self.get_by_id(cursor.lastrowid)

    async def _row_to_health_insurance(self, row) -> HealthInsurance:
        """Convert database row to HealthInsurance object."""
        provider = await self.provider_repo.get_by_id(row["provider_id"])

        return HealthInsurance(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            provider_id=row["provider_id"],
            insurance_type=InsuranceType(row["insurance_type"]),
            coverage_type=CoverageType(row["coverage_type"]),
            amount=Decimal(row["amount"]),
            has_krankengeld=bool(row["has_krankengeld"]),
            policy_number=row["policy_number"] or "",
            notes=row["notes"] or "",
            provider=provider,
        )


# Convenience functions for dependency injection
async def get_expense_repo() -> ExpenseRepository:
    """FastAPI dependency for ExpenseRepository."""
    return ExpenseRepository()


async def get_invoice_repo() -> InvoiceRepository:
    """FastAPI dependency for InvoiceRepository."""
    return InvoiceRepository()


async def get_settings_repo() -> SettingsRepository:
    """FastAPI dependency for SettingsRepository."""
    return SettingsRepository()


async def get_client_repo() -> ClientRepository:
    """FastAPI dependency for ClientRepository."""
    return ClientRepository()


async def get_uploaded_doc_repo() -> UploadedDocumentRepository:
    """FastAPI dependency for UploadedDocumentRepository."""
    return UploadedDocumentRepository()


async def get_asset_repo() -> AssetRepository:
    """FastAPI dependency for AssetRepository."""
    return AssetRepository()


async def get_travel_repo() -> TravelExpenseRepository:
    """FastAPI dependency for TravelExpenseRepository."""
    return TravelExpenseRepository()


async def get_gift_repo() -> GiftExpenseRepository:
    """FastAPI dependency for GiftExpenseRepository."""
    return GiftExpenseRepository()


async def get_home_office_repo() -> HomeOfficeRepository:
    """FastAPI dependency for HomeOfficeRepository."""
    return HomeOfficeRepository()


async def get_business_meal_repo() -> BusinessMealRepository:
    """FastAPI dependency for BusinessMealRepository."""
    return BusinessMealRepository()


async def get_health_insurance_provider_repo() -> HealthInsuranceProviderRepository:
    """FastAPI dependency for HealthInsuranceProviderRepository."""
    return HealthInsuranceProviderRepository()


async def get_health_insurance_repo() -> HealthInsuranceRepository:
    """FastAPI dependency for HealthInsuranceRepository."""
    return HealthInsuranceRepository()
