#!/usr/bin/env python
"""Seed the database with initial mock data for development.

Usage:
    python scripts/seed_database.py

Or with custom path:
    FiscFox_DB_PATH=/path/to/db.sqlite python scripts/seed_database.py
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.models import ExpenseInput, InvoiceInput
from src.db.repository import ExpenseRepository, InvoiceRepository, db_manager
from src.db.seed_data import get_mock_expenses, get_mock_invoices


async def seed_expenses(repo: ExpenseRepository) -> int:
    """Insert mock expenses into database."""
    expenses = get_mock_expenses()
    count = 0

    for exp in expenses:
        expense_input = ExpenseInput(
            date=exp.date,
            vendor=exp.vendor,
            description=exp.description,
            amount_gross=exp.amount_gross,
            vat_rate=exp.vat_rate,
            category=exp.category,
        )
        await repo.create(expense_input)
        count += 1
        print(f"  Created expense: {exp.vendor} - {exp.description[:30]}...")

    return count


async def seed_invoices(repo: InvoiceRepository) -> int:
    """Insert mock invoices into database."""
    invoices = get_mock_invoices()
    count = 0

    for inv in invoices:
        invoice_input = InvoiceInput(
            client=inv.client,
            invoice_number=inv.invoice_number,
            date=inv.date,
            due_date=inv.due_date,
            amount=inv.amount,
            vat_rate=inv.vat_rate,
            description=inv.description,
        )
        created = await repo.create(invoice_input)

        # Update status if not pending
        if inv.status.value == "paid" and inv.paid_date:
            await repo.mark_paid(created.id, inv.paid_date)
        elif inv.status.value == "overdue":
            await repo.update_overdue()

        count += 1
        print(f"  Created invoice: {inv.invoice_number} - {inv.client}")

    return count


async def main():
    """Initialize and seed the database."""
    print("=" * 60)
    print("FiscFox Database Seeding")
    print("=" * 60)

    # Initialize database (creates tables)
    print("\n[1/3] Initializing database...")
    await db_manager.initialize()
    print(f"  Database path: {db_manager.db_path}")

    # Seed expenses
    print("\n[2/3] Seeding expenses...")
    expense_repo = ExpenseRepository()
    expense_count = await seed_expenses(expense_repo)
    print(f"  Inserted {expense_count} expenses")

    # Seed invoices
    print("\n[3/3] Seeding invoices...")
    invoice_repo = InvoiceRepository()
    invoice_count = await seed_invoices(invoice_repo)
    print(f"  Inserted {invoice_count} invoices")

    print("\n" + "=" * 60)
    print("Database seeding complete!")
    print(f"  Total expenses: {expense_count}")
    print(f"  Total invoices: {invoice_count}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
