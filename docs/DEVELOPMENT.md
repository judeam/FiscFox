# FiscFox Development Guide

This guide covers environment setup, development workflows, testing, and contribution guidelines.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Make Commands](#make-commands)
- [Project Structure](#project-structure)
- [Code Quality](#code-quality)
- [Testing](#testing)
- [HTMX Patterns](#htmx-patterns)
- [Adding New Features](#adding-new-features)
- [Contribution Guidelines](#contribution-guidelines)

## Prerequisites

### Required

- Python 3.11 or higher
- uv (fast Rust-based Python package installer)
- SQLite 3.35 or higher

### Recommended

- Docker and Docker Compose
- 16+ GB RAM (for ML features)

### Installing uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or via pip
pip install uv
```

## Environment Setup

### Local Development

```bash
# Clone repository
git clone https://github.com/your-username/FiscFox.git
cd FiscFox

# Create virtual environment and install dependencies
make venv

# For faster installation in India/SEA/China
make venv-asia

# Initialize database
make db-init

# Run development server
make run

# Access at http://localhost:8000
```

### Docker Development

```bash
# Build image
make build

# For faster builds in India/SEA/China
make build-asia

# Start production container
make up

# Start development container with hot reload
make dev

# View logs
make logs

# Open shell in container
make shell
```

### Desktop App Development

```bash
# Install desktop dependencies
make desktop-deps

# Run desktop app in dev mode
make desktop-run

# Build standalone executable
make desktop-build
```

## Make Commands

### Docker Commands

| Command | Description |
|---------|-------------|
| `make build` | Build production Docker image |
| `make build-asia` | Build with Asian mirror (India/SEA/China) |
| `make up` | Start production container (detached) |
| `make down` | Stop and remove all containers |
| `make dev` | Start development container with hot reload |
| `make dev-d` | Start development container detached |
| `make logs` | View container logs |
| `make logs-dev` | View dev container logs |
| `make shell` | Open shell in running container |
| `make shell-dev` | Open shell in dev container |
| `make restart` | Restart production container |

### Local Development Commands

| Command | Description |
|---------|-------------|
| `make venv` | Create venv and install all deps with uv |
| `make venv-asia` | Create venv with Asian mirror |
| `make sync` | Sync dependencies with uv |
| `make run` | Run development server (hot reload) |
| `make test` | Run all tests |
| `make lint` | Run linter (ruff check + format check) |
| `make format` | Auto-format code |
| `make typecheck` | Run mypy type checker |

### Database Commands

| Command | Description |
|---------|-------------|
| `make db-init` | Initialize database |
| `make db-shell` | Open SQLite shell |

### Desktop Commands

| Command | Description |
|---------|-------------|
| `make desktop-deps` | Install pywebview + pyinstaller |
| `make desktop-run` | Run desktop app in dev mode |
| `make desktop-build` | Build standalone executable |
| `make desktop-build-linux` | Build for Linux |
| `make desktop-build-macos` | Build for macOS |
| `make desktop-build-windows` | Build for Windows |

### Custom Mirror

```bash
# Use custom PyPI mirror
make venv PYPI_MIRROR=https://your-mirror/simple
make build PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
```

## Project Structure

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed structure. Key directories:

```
src/
├── core/           # Pure domain logic (no framework deps)
│   ├── models.py   # Pydantic models, tax configs
│   ├── tax/        # Tax calculators with law citations
│   └── extraction/ # PDF/OCR processing
├── db/             # Data access layer
│   ├── schema.sql  # Database schema
│   └── repository.py # Async CRUD
├── ml/             # Machine learning
├── llm/            # Local LLM integration
├── licensing/      # License management
└── web/            # Application layer
    ├── routes/     # FastAPI endpoints
    ├── services/   # Business logic
    └── templates/  # Jinja2 templates
```

### Key Conventions

**Layer Boundaries**:
- `src/core/` must NOT import FastAPI, Starlette, or Jinja2
- `src/core/tax/` contains pure functions with law citations
- `src/web/` orchestrates between layers

**Naming Conventions**:
- Files: lowercase with underscores (`expense_ocr.py`)
- Classes: PascalCase (`TaxYearConfig`)
- Functions: snake_case (`calculate_income_tax`)
- Constants: UPPER_SNAKE_CASE (`VAT_STANDARD_RATE`)

## Code Quality

### Linting

FiscFox uses ruff for linting and formatting:

```bash
# Check for issues
make lint

# Auto-format code
make format

# Or directly
ruff check src/
ruff format src/
```

### Type Checking

Type hints are enforced with mypy:

```bash
make typecheck

# Or directly
mypy src/
```

### Pre-commit

Install pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

### Code Style Guidelines

1. **Financial Precision**: Always use `Decimal` for monetary values

```python
from decimal import Decimal

# Correct
amount = Decimal("100.00")
vat = amount * Decimal("0.19")

# Wrong
amount = 100.0
vat = amount * 0.19
```

2. **Law Citations**: Tax calculations must cite relevant law

```python
def calculate_income_tax(income: Decimal) -> Decimal:
    """Calculate income tax per Section 32a EStG.

    The progressive tax formula follows the 5-zone model
    defined in Section 32a Abs. 1 EStG.
    """
```

3. **Quantize Before Storage**: Always quantize monetary values

```python
result = amount.quantize(Decimal("0.01"))
```

4. **Type Hints**: All public functions must have type hints

```python
def get_vat_rate(category: str) -> Decimal:
    ...
```

## Testing

### Running Tests

```bash
# Run all tests
make test

# Or directly
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src

# Run specific test file
pytest tests/test_einkommensteuer.py -v

# Skip integration tests
pytest tests/ -m "not integration"

# Run only specific test
pytest tests/test_einkommensteuer.py::test_progressive_zones -v
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── test_einkommensteuer.py  # Income tax tests
├── test_umsatzsteuer.py     # VAT tests
├── test_afa.py              # Depreciation tests
├── test_repository.py       # Database tests
└── integration/             # Integration tests
```

### Writing Tests

1. **Unit Tests**: Test pure functions in isolation

```python
from decimal import Decimal
from src.core.tax.einkommensteuer import calculate_income_tax

def test_grundfreibetrag():
    """Test tax-free allowance (Grundfreibetrag)."""
    assert calculate_income_tax(Decimal("10000")) == Decimal("0.00")
```

2. **Integration Tests**: Mark with `@pytest.mark.integration`

```python
import pytest

@pytest.mark.integration
async def test_invoice_creation(test_db):
    """Test full invoice creation flow."""
    ...
```

3. **Test German Tax Cases**: Use realistic scenarios

```python
def test_freelancer_typical_income():
    """Test typical freelancer income (60k EUR)."""
    income = Decimal("60000")
    tax = calculate_income_tax(income)
    # Verify against official BMF calculator
    assert tax == Decimal("14697.00")
```

### Coverage Requirements

- Minimum 80% coverage for `src/core/`
- Tax calculators require 95%+ coverage
- All edge cases must be tested (0 income, max brackets, etc.)

## HTMX Patterns

FiscFox uses HTMX for dynamic interactions without JSON APIs.

### Basic Pattern

Routes return HTML fragments:

```python
@router.get("/expenses")
async def get_expenses(request: Request):
    expenses = await expense_service.list_expenses()
    return templates.TemplateResponse(
        "pages/expenses.html",
        {"request": request, "expenses": expenses}
    )
```

### Partial Updates

HTMX requests return partials:

```python
@router.get("/expenses/{expense_id}")
async def get_expense_row(request: Request, expense_id: int):
    expense = await expense_service.get_expense(expense_id)
    return templates.TemplateResponse(
        "partials/_expense_row.html",
        {"request": request, "expense": expense}
    )
```

### OOB Swaps

Update multiple elements:

```html
<div id="expense-list">
    <!-- Main content -->
</div>

<div id="total-display" hx-swap-oob="true">
    <!-- Updated total -->
</div>
```

### Form Scroll Behavior

Pages are non-scrollable by default. When forms open:

```javascript
function updateMainScroll() {
    const container = document.getElementById('form-container');
    if (container && container.innerHTML.trim()) {
        document.body.style.overflow = 'auto';
    } else {
        document.body.style.overflow = 'hidden';
    }
}
```

Form close handlers must call `updateMainScroll()` after clearing the container.

### Template Organization

```
templates/
├── base.html           # Base layout with updateMainScroll()
├── pages/              # Full page templates
│   ├── dashboard.html
│   ├── expenses.html
│   └── ...
├── partials/           # HTMX fragments
│   ├── _expense_row.html
│   ├── _expense_form.html
│   └── ...
└── components/         # Reusable UI components
    ├── _pagination.html
    ├── _alert.html
    └── ...
```

## Adding New Features

### 1. Tax Calculator

```python
# src/core/tax/new_feature.py

"""
New Tax Feature Calculator

Implements Section XX EStG for [feature description].
"""

from decimal import Decimal
from ..models import TaxYearConfig

def calculate_new_feature(
    value: Decimal,
    config: TaxYearConfig
) -> Decimal:
    """Calculate [feature] per Section XX EStG.

    Args:
        value: Input value
        config: Tax year configuration

    Returns:
        Calculated result (Decimal)

    Note:
        Based on Section XX Abs. Y EStG.
    """
    # Implementation with law citations
    pass
```

### 2. Database Table

Add to `src/db/schema.sql`:

```sql
-- New Feature Table
-- Description and law reference
CREATE TABLE IF NOT EXISTS new_feature (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Fields with constraints
    amount TEXT NOT NULL,  -- Decimal string
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_new_feature_... ON new_feature(...);

-- Audit trigger
CREATE TRIGGER IF NOT EXISTS trg_new_feature_audit_insert
AFTER INSERT ON new_feature
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, new_values)
    VALUES ('new_feature', NEW.id, 'INSERT', json_object(...));
END;
```

### 3. Repository Methods

Add to `src/db/repository.py`:

```python
class NewFeatureRepository:
    async def create(self, data: NewFeatureCreate) -> NewFeature:
        ...

    async def get(self, id: int) -> NewFeature | None:
        ...

    async def list(self, **filters) -> list[NewFeature]:
        ...

    async def update(self, id: int, data: NewFeatureUpdate) -> NewFeature:
        ...

    async def delete(self, id: int) -> None:
        # Soft delete
        await self._execute(
            "UPDATE new_feature SET deleted_at = ? WHERE id = ?",
            (datetime.now(), id)
        )
```

### 4. Service Layer

Create `src/web/services/new_feature.py`:

```python
from src.core.tax.new_feature import calculate_new_feature
from src.db.repository import NewFeatureRepository

class NewFeatureService:
    def __init__(self, repository: NewFeatureRepository):
        self.repository = repository

    async def create(self, data: NewFeatureCreate) -> NewFeature:
        # Business logic
        calculated = calculate_new_feature(data.value, config)
        return await self.repository.create(data)
```

### 5. Route

Create `src/web/routes/new_feature.py`:

```python
from fastapi import APIRouter, Request
from src.web.services.new_feature import NewFeatureService

router = APIRouter(prefix="/new-feature", tags=["new_feature"])

@router.get("/")
async def list_new_features(request: Request):
    items = await new_feature_service.list()
    return templates.TemplateResponse(
        "pages/new_feature.html",
        {"request": request, "items": items}
    )
```

Register in `src/web/routes/__init__.py`.

### 6. Templates

Create templates:
- `templates/pages/new_feature.html` - Full page
- `templates/partials/_new_feature_row.html` - HTMX partial
- `templates/partials/_new_feature_form.html` - Form partial

### 7. Tests

Create `tests/test_new_feature.py`:

```python
import pytest
from decimal import Decimal

from src.core.tax.new_feature import calculate_new_feature

def test_basic_calculation():
    result = calculate_new_feature(Decimal("1000"), config)
    assert result == Decimal("expected")

def test_edge_cases():
    # Zero value
    # Maximum value
    # Boundary conditions
    pass
```

## Contribution Guidelines

### Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make changes following code style guidelines
4. Write tests for new functionality
5. Run `make lint` and `make test`
6. Submit a pull request

### Pull Request Requirements

- All tests pass
- Code coverage maintained or improved
- Type hints for public functions
- Documentation for new features
- Law citations for tax-related changes
- No `float` for monetary values

### Commit Messages

Follow conventional commits:

```
feat: add gift expense tracking
fix: correct VAT calculation for reverse charge
docs: update depreciation methods reference
test: add edge cases for income tax zones
refactor: extract common validation logic
```

### Code Review Checklist

- [ ] Financial precision (Decimal, not float)
- [ ] Law citations where applicable
- [ ] Type hints complete
- [ ] Tests written and passing
- [ ] No framework imports in core/
- [ ] HTMX patterns followed
- [ ] Audit triggers for new tables
