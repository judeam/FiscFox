# Contributing to FiscFox

Thank you for your interest in contributing to FiscFox! This project helps German freelancers manage their taxes with privacy-first, local-only software.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/your-username/FiscFox.git`
3. Set up your environment: `make venv`
4. Initialize the database: `make db-init`
5. Run the development server: `make run`
6. Create a feature branch: `git checkout -b feature/your-feature`
7. Make your changes
8. Run tests: `make test`
9. Run linting: `make lint`
10. Submit a pull request

## Domain Knowledge

FiscFox implements German tax law. Contributors working on tax logic should be familiar with:

- **EStG** (Einkommensteuergesetz): Income tax law, especially Section 32a (progressive tax brackets)
- **UStG** (Umsatzsteuergesetz): VAT law, especially Section 19 (Kleinunternehmerregelung)
- **EUeR** (Einnahmen-Ueberschuss-Rechnung): Simplified accounting for freelancers

When modifying tax calculations, always cite the relevant law section in code comments:

```python
# Section 32a Abs. 1 EStG - Progressive tax zones
# Section 19 UStG - Small business VAT exemption
```

## Code Standards

### Financial Integrity

- **All monetary values must use `decimal.Decimal`** - never `float`
- Quantize to 2 decimal places before database storage: `amount.quantize(Decimal("0.01"))`
- Money is stored as TEXT in SQLite to preserve precision

### Tax Logic Isolation

Tax calculators in `src/core/tax/` must NOT import `fastapi`, `starlette`, or `jinja2`. They are pure domain logic with no framework dependencies.

### HTMX Patterns

- Routes return HTML fragments, not JSON
- Use partials (`_expense_row.html`) for HTMX responses
- Form validation errors are returned as HTML, not 400 JSON responses

## Development Commands

```bash
make venv         # Create virtual environment
make run          # Start dev server with hot reload
make test         # Run all tests
make lint         # Run ruff check + format check
make format       # Auto-format code
make typecheck    # Run mypy type checker
```

## Pull Request Process

1. Ensure all tests pass (`make test`)
2. Ensure code passes linting (`make lint`)
3. Update documentation if you changed behavior
4. Describe your changes clearly in the PR description
5. Link any relevant issues

## Tax Law Changes

When German tax law changes (e.g., new tax brackets for a new year):

1. Add a new `TaxYearConfig` entry in `src/core/models.py`
2. Update the relevant calculator in `src/core/tax/`
3. Cite the official BMF (Bundesfinanzministerium) publication
4. Add tests for the new year's values
5. Update `TAX_CONFIGS` dictionary with the new year

## Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Include steps to reproduce for bugs
- For tax calculation issues, include the relevant law section and expected values
