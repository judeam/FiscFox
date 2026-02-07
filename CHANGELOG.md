# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Renamed project from PyYield to FiscFox
- Prepared repository for public open-source release
- Removed commercial licensing components

## [0.1.0] - 2025-01-01

### Added
- Income tax calculation (Einkommensteuer) with progressive zones per Section 32a EStG
- VAT management (Umsatzsteuer) with Vorsteuer deduction
- Kleinunternehmerregelung support (Section 19 UStG)
- Reverse Charge for EU B2B services (Section 13b UStG)
- Invoice and expense tracking
- Client management with dependency warnings
- Asset depreciation (AfA): GWG, Pool, Linear, Degressive, Digital
- Travel expense tracking (Reisekosten) with per diem and km allowance
- Gift tracking (Geschenke) with 50 EUR limit enforcement
- Business meal deductions (Bewirtung) at 70%/100%
- Home office deduction (Homeoffice-Pauschale) at 6 EUR/day
- Health insurance deduction tracking (GKV/PKV)
- Receipt OCR with PaddleOCR and Tesseract
- Local AI chat via Ollama with RAG for tax knowledge
- Text-to-SQL natural language queries
- ML-powered expense categorization (TabPFN)
- Cash flow forecasting (Prophet)
- Tax deadline calendar
- Docker support with multi-region build mirrors
- Desktop app packaging via pywebview/PyInstaller
- Bilingual UI (German/English)
