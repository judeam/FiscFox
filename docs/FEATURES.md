# FiscFox Features

Comprehensive feature documentation organized by domain.

## Table of Contents

- [Income Tax (Einkommensteuer)](#income-tax-einkommensteuer)
- [VAT Management (Umsatzsteuer)](#vat-management-umsatzsteuer)
- [Invoice Management](#invoice-management)
- [Expense Tracking](#expense-tracking)
- [Client Management](#client-management)
- [Tax Optimization](#tax-optimization)
- [Health Insurance](#health-insurance)
- [Machine Learning Features](#machine-learning-features)
- [Reporting and Deadlines](#reporting-and-deadlines)

## Income Tax (Einkommensteuer)

FiscFox calculates German income tax according to Section 32a EStG with progressive tax zones.

### Tax Calculation

| Zone | Income Range (2026) | Rate |
|------|---------------------|------|
| 1 | 0 - 12,096 EUR | 0% (Grundfreibetrag) |
| 2 | 12,097 - 17,443 EUR | 14% - 24% (progressive) |
| 3 | 17,444 - 68,480 EUR | 24% - 42% (progressive) |
| 4 | 68,481 - 277,825 EUR | 42% |
| 5 | 277,826+ EUR | 45% (Reichensteuer) |

### Features

- **Progressive Calculation**: Exact formula per Section 32a EStG
- **Multi-Year Support**: Configurations for 2025 and 2026 tax brackets
- **Solidarity Surcharge**: 5.5% on income tax above threshold
- **Quarterly Prepayments**: Track Vorauszahlungen with due date reminders
- **Rate Display**: Effective and marginal tax rate visualization
- **Scheinselbstaendigkeit Warning**: Alert when income concentration exceeds 83% from single client

### Technical Implementation

```
Location: src/core/tax/einkommensteuer.py
Law Reference: Section 32a EStG
```

## VAT Management (Umsatzsteuer)

Complete VAT tracking for German freelancers including input VAT deduction.

### VAT Rates

| Rate | Application |
|------|-------------|
| 19% | Standard rate for most goods and services |
| 7% | Reduced rate (books, food, public transport) |
| 0% | Reverse charge for B2B international (Section 13b UStG) |

### Features

- **Output VAT (Umsatzsteuer)**: Track VAT collected on invoices
- **Input VAT (Vorsteuer)**: Deduct VAT paid on business expenses
- **VAT Liability (Zahllast)**: Calculate net VAT owed (USt - Vorsteuer)
- **Reverse Charge**: Automatic 0% VAT for EU B2B with VAT ID validation
- **Small Business Exemption**: Kleinunternehmerregelung support (Section 19 UStG)
  - Previous year revenue under 25,000 EUR
  - Current year revenue under 100,000 EUR
- **Filing Frequency**: Monthly, quarterly, or annual based on settings
- **EC Sales List**: Zusammenfassende Meldung tracking for EU B2B

### Technical Implementation

```
Location: src/core/tax/umsatzsteuer.py
Law Reference: UStG, Section 19
```

## Invoice Management

Create, track, and manage client invoices with full German compliance.

### Features

- **Invoice Creation**: Generate invoices with automatic numbering
- **Templates**: Classic, Modern, Professional, and Dark themes
- **Custom Numbering**: Configurable prefix (e.g., "INV-2026-")
- **Payment Tracking**: Pending, Paid, Overdue status management
- **Client Linking**: Associate invoices with client records
- **PDF Upload**: Import existing invoices with data extraction
- **ELSTER Export**: Generate XML for official tax submissions

### Reverse Charge Handling

For B2B international invoices:
1. Set client country (non-DE)
2. Enter client VAT ID
3. System applies 0% VAT automatically
4. Included in Zusammenfassende Meldung

### Storno (Reversal)

Financial records are immutable. To correct an invoice:
1. Create a Storno (reversal) of the original
2. Create a new correct invoice
3. Both entries preserved for audit trail

## Expense Tracking

Categorize and track business expenses with VAT recovery.

### Expense Categories

| Category | German | Description |
|----------|--------|-------------|
| buero | Buero | Office supplies, materials |
| software | Software | Subscriptions, licenses |
| hardware | Hardware | Computers, equipment |
| reise | Reise | Travel expenses |
| kommunikation | Kommunikation | Phone, internet |
| versicherung | Versicherung | Business insurance |
| fortbildung | Fortbildung | Training, education |
| bewirtung | Bewirtung | Business meals |
| geschenke | Geschenke | Client gifts |
| sonstiges | Sonstiges | Other expenses |

### Features

- **VAT Recovery**: Automatic Vorsteuer tracking at 19%, 7%, or 0%
- **Receipt Upload**: Scan and OCR receipts for data extraction
- **Category Reporting**: Breakdown by category per year
- **Vendor Tracking**: Associate expenses with vendors
- **Storno Support**: Reversal pattern for corrections

### Receipt OCR

FiscFox extracts data from receipt images:
1. Upload receipt image or PDF
2. OCR processing (PaddleOCR or Tesseract)
3. LLM enhancement for low-confidence extractions
4. Manual review and confirmation

## Client Management

Maintain client database for invoicing and tax compliance.

### Features

- **Contact Details**: Name, email, phone
- **Address Management**: Street, city, country (domestic and international)
- **VAT ID Tracking**: EU VAT IDs for reverse charge validation
- **Income Analysis**: Revenue distribution per client
- **Scheinselbstaendigkeit Detection**: Warning when single client exceeds 83% of income
- **Soft Delete**: Clients can be archived, not permanently deleted

### Client Data

| Field | Required | Purpose |
|-------|----------|---------|
| Name | Yes | Invoice display |
| Country | Yes | Reverse charge determination |
| VAT ID | No | EU B2B validation |
| Email | No | Contact information |
| Address | No | Invoice generation |

## Tax Optimization

Advanced deduction tracking for maximizing tax efficiency.

### Asset Depreciation (AfA)

Track depreciable business assets per Section 7 EStG.

| Method | Threshold | Duration | Law |
|--------|-----------|----------|-----|
| Immediate (GWG) | Under 800 EUR | 1 year | Section 6 Abs. 2 EStG |
| Pool | 250-1,000 EUR | 5 years | Section 6 Abs. 2a EStG |
| Linear | Over 1,000 EUR | Useful life | Section 7 Abs. 1 EStG |
| Degressive | Over 1,000 EUR | Up to 25% | Wachstumschancengesetz 2024 |
| Digital AfA | IT assets | 1 year | BMF 2021 |

**Features**:
- Automatic method suggestion based on value
- Mixed use percentage (private/business)
- Pro-rata calculation for mid-year purchases
- Book value tracking over time
- Disposal handling with gain/loss calculation

### Travel Expenses (Reisekosten)

Per diem and kilometer allowances per Section 9 Abs. 4a EStG.

**Per Diem Rates (Domestic)**:

| Duration | Rate | Notes |
|----------|------|-------|
| 8+ hours | 14 EUR | Single day trip |
| 24 hours | 28 EUR | Full day |
| Travel day | 14 EUR | Arrival or departure day |

**Meal Reductions**:
- Breakfast provided: -20% (5.60 EUR)
- Lunch provided: -40% (11.20 EUR)
- Dinner provided: -40% (11.20 EUR)

**Kilometer Allowance**:
- First 20 km: 0.30 EUR/km
- Beyond 20 km: 0.38 EUR/km

**Features**:
- Automatic per diem calculation based on duration
- Foreign per diem rates for major countries
- Meal reduction tracking
- Overnight trip handling
- Link to additional receipted expenses

### Gift Expenses (Geschenke)

Track client gifts with 50 EUR limit per Section 4 Abs. 5 Nr. 1 EStG.

**Rules**:
- Maximum 50 EUR net per recipient per year
- Cliff effect: 50.01 EUR makes entire amount non-deductible
- Cumulative tracking across all gifts to same recipient

**Features**:
- Per-recipient annual tracking
- Automatic deductibility determination
- Warning when approaching or exceeding limit
- Optional 30% flat tax (Section 37b EStG) tracking

### Business Meals (Bewirtung)

Entertainment expense tracking per Section 4 Abs. 5 Nr. 2 EStG.

| Type | Deductible | Limit |
|------|------------|-------|
| Client entertainment | 70% | None |
| Staff event | 100% | 110 EUR per person |

**Required Documentation**:
- Date and location
- Attendees (names)
- Business purpose
- Receipt with tip separated

### Home Office (Homeoffice-Pauschale)

Track work-from-home days for deduction.

**Options**:

| Method | Rate | Maximum |
|--------|------|---------|
| Pauschale | 6 EUR/day | 210 days = 1,260 EUR/year |
| Arbeitszimmer | Actual costs | 1,260 EUR flat or actual |

**Features**:
- Daily tracking with calendar view
- Automatic annual limit enforcement
- Support for both deduction methods
- Year-over-year comparison

## Health Insurance

Track health insurance payments for tax deduction per Section 10 EStG.

### Insurance Types

| Type | German | Description |
|------|--------|-------------|
| GKV | Gesetzliche Krankenversicherung | Statutory health insurance |
| PKV | Private Krankenversicherung | Private health insurance |

### Coverage Categories

| Category | Deductibility |
|----------|--------------|
| basis_krankenversicherung | Unlimited |
| pflegepflichtversicherung | Unlimited |
| wahlleistungen | Limited (2,800 EUR/year) |
| zusatzversicherung | Limited (2,800 EUR/year) |

### Features

- **Provider Database**: 30+ GKV and 30+ PKV providers pre-loaded
- **Payment Tracking**: Monthly payment recording
- **Krankengeld Reduction**: 4% reduction for GKV with sick pay entitlement
- **Deduction Calculation**: Automatic separation of unlimited vs limited
- **Annual Summary**: Tax-ready deduction totals

## Machine Learning Features

All ML features run locally with no external API calls.

### Expense Categorization

**Technology**: TabPFN 2.5

Automatically suggests expense categories based on:
- Vendor name patterns
- Description text
- Amount ranges
- Historical categorization

### Invoice Risk Scoring

**Technology**: TabPFN 2.5

Predicts payment risk for new invoices:
- Client payment history
- Invoice amount
- Payment terms
- Client relationship duration

### Cash Flow Forecasting

**Technology**: Prophet

Projects future cash flow based on:
- Historical revenue patterns
- Seasonal trends
- Expense patterns

### Vendor Deduplication

**Technology**: HDBSCAN

Identifies and merges duplicate vendor entries:
- Fuzzy name matching
- Pattern recognition

## Reporting and Deadlines

### Tax Deadline Calendar

Visual calendar with upcoming tax obligations:

| Deadline | Frequency | Due Date |
|----------|-----------|----------|
| USt-Voranmeldung | Monthly/Quarterly | 10th of following month |
| Zusammenfassende Meldung | Monthly/Quarterly | 25th of following month |
| ESt-Vorauszahlung | Quarterly | 10th of Mar, Jun, Sep, Dec |

**Features**:
- Color-coded urgency
- One-click completion marking
- Notification reminders
- Upcoming vs overdue distinction

### Reports

| Report | Description |
|--------|-------------|
| Annual Tax Summary | Yearly overview with visual breakdown |
| Monthly Revenue | Revenue charts with forecasting |
| Client Distribution | Income concentration analysis |
| Expense Categories | Category-wise expense breakdown |
| EUER Preview | Einnahmen-Ueberschuss-Rechnung draft |
| ELSTER XML | Official submission format |

### ELSTER Integration

Export tax data in official XML format for:
- USt-Voranmeldung
- Zusammenfassende Meldung
- Annual tax declaration
