<p align="center">
  <img src="fiscfox_logo_transparent.png" alt="FiscFox Logo" width="200">
</p>

<h1 align="center">FiscFox</h1>

<p align="center">Privacy-first tax management for German freelancers (Freiberufler).</p>

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-orange.svg)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## What is FiscFox?

FiscFox helps German self-employed professionals track income, expenses, and tax obligations. All calculations follow current German tax law (EStG, UStG) with automatic updates for yearly tax bracket changes.

**Key Benefits**:

- **Privacy First**: All data stays on your machine. No cloud sync, no telemetry.
- **German Tax Compliance**: Income tax (Section 32a EStG), VAT, reverse charge, Kleinunternehmer support.
- **Tax Optimization**: AfA depreciation, Reisekosten, Geschenke limits, Homeoffice-Pauschale, Bewirtung.
- **Local AI**: Chat with your tax data using local LLMs (llama.cpp / GGUF). Hardware-aware model selection auto-scales from a 4B laptop model up to Gemma 4 26B-A4B on a 24GB GPU. No data leaves your device.

## Screenshots

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="Dashboard" width="800">
  <br><em>Dashboard — financial overview with income forecast and tax deadlines</em>
</p>

<p align="center">
  <img src="docs/screenshots/expenses.png" alt="Expenses" width="800">
  <br><em>Expenses — categorized tracking with Vorsteuer deduction</em>
</p>

<p align="center">
  <img src="docs/screenshots/invoices.png" alt="Invoices" width="800">
  <br><em>Invoices — status tracking with VAT summary</em>
</p>

<p align="center">
  <img src="docs/screenshots/taxes.png" alt="Tax Overview" width="800">
  <br><em>Tax Overview — deadlines, prepayments, and EUeR preview</em>
</p>

## Quick Start

### Docker (Recommended)

```bash
git clone https://github.com/your-username/FiscFox.git
cd FiscFox
make build && make up
```

Access at [http://localhost:8000](http://localhost:8000)

### Local Development

```bash
make venv      # Create environment with uv
make db-init   # Initialize database
make run       # Start development server
```

For Asian regions (faster mirrors):
```bash
make venv-asia
make build-asia
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Python 3.11+ |
| Frontend | Jinja2, HTMX, Tailwind CSS |
| Database | SQLite (WAL mode) |
| ML | TabPFN, Prophet |
| LLM | llama.cpp/GGUF or Ollama (local) — Gemma 4, Qwen3 |
| Embeddings | sentence-transformers + sqlite-vec |
| Desktop | pywebview, PyInstaller |

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design with Mermaid diagrams |
| [Features](docs/FEATURES.md) | Detailed feature documentation |
| [Database](docs/DATABASE.md) | Schema reference with ERD |
| [Development](docs/DEVELOPMENT.md) | Contributing and testing guide |
| [Tax Reference](docs/TAX_REFERENCE.md) | German tax concepts and law citations |
| [LLM Integration](docs/LLM_INTEGRATION.md) | AI chat and RAG documentation |

## Features at a Glance

**Core**:
- Income tax calculation (Einkommensteuer) with progressive zones
- VAT management (Umsatzsteuer) with Vorsteuer deduction
- Invoice and expense tracking with receipt OCR
- Client management with Scheinselbstaendigkeit warnings

**Tax Optimization**:
- Asset depreciation (GWG, Pool, Linear, Degressive, Digital AfA)
- Travel expenses with per diem and km allowance
- Gift tracking with 50 EUR limit enforcement
- Business meals (70% client, 100% staff)
- Home office deduction (6 EUR/day)
- Health insurance deductions (GKV/PKV)

**Reporting**:
- Tax deadline calendar
- ELSTER XML export
- EUER preview
- ML-powered cash flow forecasting

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) before submitting a pull request.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## License

MIT License. See [LICENSE](LICENSE) file.

---

Built for the German freelance community. Tax calculations based on official Bundesfinanzministerium publications and current EStG/UStG legislation.
