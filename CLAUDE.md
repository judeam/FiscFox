# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Docker (Recommended)

```bash
make build       # Build production Docker image
make build-asia  # Build with Asian mirror (fastest for India/SEA/China)
make up          # Start production container (detached)
make down        # Stop and remove all containers
make dev         # Start development container with hot reload
make dev-d       # Start development container detached

make logs        # View container logs
make logs-dev    # View dev container logs
make shell       # Open shell in running container
make shell-dev   # Open shell in dev container
make restart     # Restart production container

# Custom mirror for your region:
make build PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
```

### Local Development (uses uv for fast installs)

```bash
make venv         # Create venv and install all deps with uv
make venv-asia    # Create venv with Asian mirror (India/SEA/China)
make sync         # Sync dependencies with uv
make run          # Run development server (hot reload)
make test         # Run all tests
make lint         # Run linter (ruff check + format check)
make format       # Auto-format code
make typecheck    # Run mypy type checker
make db-init      # Initialize database
make db-shell     # Open SQLite shell

# Custom mirror: make venv PYPI_MIRROR=https://your-mirror/simple
```

### Desktop App

```bash
make desktop-deps    # Install pywebview + pyinstaller
make desktop-run     # Run desktop app in dev mode
make desktop-build   # Build standalone executable for current platform
make desktop-build-linux   # Build for Linux
make desktop-build-macos   # Build for macOS
make desktop-build-windows # Build for Windows
```

## Architecture

**Stack**: FastAPI + Jinja2 + HTMX + SQLite + TabPFN + Local LLM (Hypermedia-first, no JSON APIs)

**Package Manager**: uv (fast Rust-based Python package installer)

### Layer Separation

```
src/
├── core/               # Pure domain logic (NO framework imports)
│   ├── models.py       # Pydantic models, TaxYearConfig, Decimal-only money
│   ├── i18n.py         # Internationalization (DE/EN)
│   ├── cache.py        # Caching utilities
│   ├── exceptions.py   # Domain exceptions
│   ├── tax/            # German tax calculators (EStG, UStG)
│   │   ├── einkommensteuer.py  # Income tax (§ 32a EStG)
│   │   ├── umsatzsteuer.py     # VAT, Vorsteuer, Kleinunternehmer (§ 19 UStG)
│   │   ├── deadlines.py        # Tax deadline calculation
│   │   ├── afa.py              # Depreciation (§ 7 EStG, BMF Digital AfA)
│   │   ├── reisekosten.py      # Travel expenses (§ 9 Abs. 4a EStG)
│   │   ├── geschenke.py        # Gift deductions (§ 4 Abs. 5 Nr. 1 EStG)
│   │   └── health_insurance.py # Health insurance deductions (§ 10 EStG)
│   └── extraction/     # PDF/OCR data extraction
│       ├── expense_models.py   # OCR result models
│       └── expense_ocr.py      # Receipt OCR with PaddleOCR/Tesseract
├── db/                 # Data access layer
│   ├── schema.sql      # SQLite schema with WAL mode
│   ├── schema_rag.sql  # RAG/embeddings schema for AI features
│   ├── migrations/     # Database migrations
│   └── repository.py   # Async CRUD with aiosqlite
├── ml/                 # Machine Learning features
│   ├── base.py         # Base ML utilities
│   ├── models.py       # Model definitions
│   ├── features.py     # Feature engineering
│   └── tabpfn_wrapper.py  # TabPFN integration
├── llm/                # Local LLM integration
│   ├── config.py       # LLM configuration (Ollama, etc.)
│   ├── manager.py      # Model management
│   ├── orchestrator.py # Multi-agent orchestration
│   ├── router.py       # Intent routing
│   ├── service.py      # Main LLM service
│   ├── embeddings.py   # Text embeddings for RAG
│   ├── retrieval.py    # RAG retrieval
│   ├── ingestion.py    # Document ingestion
│   ├── structured.py   # Structured output parsing
│   └── agents/         # Specialized agents
│       ├── tax_rag.py  # Tax knowledge RAG agent
│       └── text2sql.py # Natural language to SQL agent
└── web/                # Application layer
    ├── routes/         # FastAPI endpoints returning HTML
    │   ├── dashboard.py, expenses.py, invoices.py, clients.py
    │   ├── assets.py           # AfA/depreciation management
    │   ├── travel.py           # Reisekosten
    │   ├── gifts.py            # Geschenke
    │   ├── homeoffice.py       # Home office tracking
    │   ├── bewirtung.py        # Business meals
    │   ├── health_insurance.py # Krankenversicherung (GKV/PKV)
    │   ├── llm.py              # AI chat endpoints
    │   └── settings.py, upload.py
    ├── services/       # Business orchestration
    │   ├── dashboard.py, expense.py, invoice.py, client.py
    │   ├── asset.py, travel.py, gift.py, homeoffice.py, bewirtung.py
    │   ├── health_insurance.py # Health insurance service
    │   ├── expense_ocr.py      # Receipt OCR service
    │   ├── report.py, upload.py
    │   └── ml_*.py     # ML prediction services
    ├── middleware/     # Rate limiting, etc.
    └── templates/      # Jinja2 (pages/, partials/, components/)
```

### Critical Constraints

**Financial Integrity**:
- ALL monetary values: `decimal.Decimal` only, NEVER `float`
- Quantize to 2 decimals before DB storage: `amount.quantize(Decimal("0.01"))`
- Money stored as TEXT in SQLite to preserve precision

**Tax Logic Isolation** (`src/core/tax/`):
- Must NOT import `fastapi`, `starlette`, or `jinja2`
- Cite German tax law in comments: `# § 32a Abs. 1 EStG`
- Use Strategy Pattern for yearly configs (`TAX_CONFIGS[2025]`, `TAX_CONFIGS[2026]`)

**HTMX Patterns**:
- Routes return HTML fragments, not JSON
- Use partials (`_expense_row.html`) for HTMX responses
- OOB swaps (`hx-swap-oob`) for updating distant DOM elements
- Form validation errors returned as HTML, not 400 JSON
- Dynamic scroll: `updateMainScroll()` toggles page scroll when forms open/close

**ML Features**:
- TabPFN 2.5 for tabular predictions (expense categorization, invoice risk)
- Prophet for time series forecasting (cash flow)
- All models trained on user data locally, no cloud inference

**LLM Features**:
- Local LLM via Ollama (llama3, mistral, etc.)
- RAG for German tax law knowledge
- Text-to-SQL for natural language queries
- All processing local, no data leaves the device

**OCR Features**:
- PaddleOCR (primary) for receipt scanning
- Tesseract (fallback) for basic OCR
- LLM enhancement for low-confidence extractions

### Data Flow

```
HTTP Request → Route → Service → Repository/Tax Calculator → Jinja2 Template → HTML Response
```

Routes handle only HTTP/HTMX specifics. Services orchestrate business logic. Tax calculations are pure functions in `src/core/tax/`.

### Key Files

- `src/core/models.py`: Domain models, tax configs 2025/2026, enums, all tax optimization models
- `src/core/tax/einkommensteuer.py`: Income tax calculator (progressive zones per § 32a EStG)
- `src/core/tax/umsatzsteuer.py`: VAT calculator, Vorsteuer, Kleinunternehmerregelung (§ 19 UStG)
- `src/core/tax/afa.py`: Depreciation methods (GWG, Pool, Linear, Degressive, Digital AfA)
- `src/core/tax/reisekosten.py`: Per diem rates, km allowance, meal reductions
- `src/core/tax/geschenke.py`: Gift limit tracking (50 EUR cliff effect)
- `src/core/tax/health_insurance.py`: Health insurance deduction calculations (§ 10 EStG)
- `src/db/repository.py`: All repositories with soft deletes and storno support
- `src/db/schema.sql`: Full database schema including tax optimization tables
- `src/web/services/dashboard.py`: Aggregates financial data with tax calculations
- `src/llm/service.py`: Main LLM service for AI chat features
- `src/web/templates/base.html`: Base template with `updateMainScroll()` for form scroll behavior

### German Tax Concepts

**Core Tax Types**:
- **Einkommensteuer**: Income tax with 5 progressive zones (0% → 14-24% → 24-42% → 42% → 45%)
- **Umsatzsteuer (USt)**: VAT collected on invoices (19% standard, 7% reduced)
- **Vorsteuer**: Input VAT on expenses (deductible from USt)
- **Zahllast**: Net VAT liability = USt - Vorsteuer
- **Solidaritätszuschlag**: 5.5% surcharge on income tax (above threshold)

**Special Regulations**:
- **Kleinunternehmerregelung** (§ 19 UStG): Small business VAT exemption (<25k prev year, <100k current)
- **Reverse Charge** (§ 13b UStG): 0% VAT for B2B international services
- **Freiberufler** (§ 18 EStG): Freelancer status, exempt from Gewerbesteuer

**Tax Optimization Features**:
- **AfA** (§ 7 EStG): Depreciation - GWG (<800€), Pool (250-1000€), Linear, Degressive, Digital
- **Reisekosten** (§ 9 Abs. 4a EStG): Per diem (14€/28€), km allowance (0.30€/0.38€)
- **Geschenke** (§ 4 Abs. 5 Nr. 1 EStG): 50€ limit per recipient/year (cliff effect)
- **Bewirtung** (§ 4 Abs. 5 Nr. 2 EStG): 70% deductible for client meals
- **Homeoffice-Pauschale**: 6€/day, max 210 days = 1,260€/year
- **Arbeitszimmer**: Separate room deduction (actual costs or 1,260€ flat rate)
- **Krankenversicherung** (§ 10 EStG): Health insurance deductions (GKV/PKV basis contributions)

**Document Patterns**:
- **Storno**: Reversal transaction pattern (booked transactions are immutable)
- **EÜR**: Einnahmen-Überschuss-Rechnung (simplified accounting)
- **USt-Voranmeldung**: Monthly/quarterly VAT declaration
- **Zusammenfassende Meldung**: EC Sales List for EU B2B services

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_PATH` | SQLite database location | `data/FiscFox.db` |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `LLM_MODEL` | Default LLM model | `llama3` |

### Database Tables

**Core**: `clients`, `expenses`, `invoices`, `tax_payments`, `tax_reports`, `settings`, `audit_log`

**Tax Optimization**: `assets`, `depreciation_records`, `travel_expenses`, `gift_expenses`, `home_office_days`, `home_office_settings`, `business_meals`, `health_insurance_payments`, `health_insurance_providers`

**Documents**: `uploaded_documents`

**AI/RAG**: `embeddings`, `chat_history`, `tax_knowledge`

### UI Patterns

**Form Scroll Behavior**:
- Pages are non-scrollable by default (content fits viewport)
- When create/edit forms open, `updateMainScroll()` enables scrolling
- When forms close, scroll is disabled again
- All form close handlers must call `updateMainScroll()` after clearing the form container

**Form Containers**:
- `#expense-form-container` - Expenses page
- `#invoice-form-container` - Invoices page
- `#health-insurance-form-container` - Health insurance page
- `#upload-form-container` - Upload forms

### Testing

```bash
pytest tests/ -v                    # All tests
pytest tests/ --cov=src             # With coverage
pytest tests/test_einkommensteuer.py -v  # Specific module
pytest -m "not integration"         # Skip integration tests
```
