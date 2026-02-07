# German Tax Reference

This document explains German tax concepts relevant to FiscFox, with law citations and practical examples.

## Table of Contents

- [Tax Types](#tax-types)
- [Income Tax (Einkommensteuer)](#income-tax-einkommensteuer)
- [Value Added Tax (Umsatzsteuer)](#value-added-tax-umsatzsteuer)
- [Tax Optimization Features](#tax-optimization-features)
- [Special Regulations](#special-regulations)
- [Document Patterns](#document-patterns)
- [Glossary](#glossary)
- [Legal References](#legal-references)

## Tax Types

German freelancers (Freiberufler) typically deal with these taxes:

| Tax | German | Law | Description |
|-----|--------|-----|-------------|
| Income Tax | Einkommensteuer | EStG | Progressive tax on annual income |
| Solidarity Surcharge | Solidaritaetszuschlag | SolZG | 5.5% surcharge on income tax |
| VAT | Umsatzsteuer (USt) | UStG | Value-added tax on sales |
| Church Tax | Kirchensteuer | KiStG | 8-9% of income tax (if applicable) |

Freelancers (Section 18 EStG) are generally exempt from:
- Trade Tax (Gewerbesteuer) - applies only to trades (Gewerbe)

## Income Tax (Einkommensteuer)

### Progressive Tax Zones

Income tax follows a progressive formula defined in Section 32a EStG.

**2026 Tax Brackets**:

| Zone | Taxable Income | Rate | Formula |
|------|---------------|------|---------|
| 1 | 0 - 12,096 EUR | 0% | Grundfreibetrag (tax-free) |
| 2 | 12,097 - 17,443 EUR | 14-24% | Progressive linear increase |
| 3 | 17,444 - 68,480 EUR | 24-42% | Progressive linear increase |
| 4 | 68,481 - 277,825 EUR | 42% | Flat rate |
| 5 | 277,826+ EUR | 45% | Reichensteuer |

### Calculation Example

For 60,000 EUR taxable income (2026):

```
Zone 1: 12,096 EUR at 0% = 0 EUR
Zone 2: 5,347 EUR (12,097-17,443) progressive = ~900 EUR
Zone 3: 42,557 EUR (17,444-60,000) progressive = ~13,797 EUR
Total: ~14,697 EUR
Effective rate: 24.5%
```

### Solidarity Surcharge

Per SolZG, 5.5% of income tax applies above threshold:
- Exemption threshold: 18,130 EUR (singles), 36,260 EUR (married)
- Above threshold: 5.5% of income tax

### Quarterly Prepayments (Vorauszahlungen)

Section 37 EStG requires quarterly prepayments:

| Quarter | Due Date |
|---------|----------|
| Q1 | March 10 |
| Q2 | June 10 |
| Q3 | September 10 |
| Q4 | December 10 |

## Value Added Tax (Umsatzsteuer)

### VAT Rates

| Rate | Application | Example |
|------|-------------|---------|
| 19% | Standard rate | Most services, software development |
| 7% | Reduced rate | Books, food, public transport |
| 0% | Reverse charge | B2B international services |

### Input VAT (Vorsteuer)

VAT paid on business purchases is deductible (Section 15 UStG):

```
VAT Liability = Output VAT - Input VAT
(Zahllast)     (Umsatzsteuer) (Vorsteuer)
```

### Reverse Charge (Section 13b UStG)

For B2B services to EU clients with valid VAT ID:
1. Invoice shows 0% VAT
2. Recipient handles VAT in their country
3. Must report in Zusammenfassende Meldung

Requirements:
- Client has valid EU VAT ID
- Service is B2B
- Client is in different EU country

### Kleinunternehmerregelung (Section 19 UStG)

Small business VAT exemption:

| Criterion | Threshold |
|-----------|-----------|
| Previous year revenue | Under 25,000 EUR |
| Current year forecast | Under 100,000 EUR |

When applicable:
- No VAT charged on invoices
- No VAT deduction on purchases
- Invoices must state exemption

### Filing Frequency

| Annual VAT | Frequency |
|------------|-----------|
| Under 1,000 EUR | Annual only |
| 1,000 - 7,500 EUR | Quarterly |
| Over 7,500 EUR | Monthly |

Due dates:
- Monthly: 10th of following month
- Quarterly: 10th of following month after quarter

### EC Sales List (Zusammenfassende Meldung)

Required for EU B2B reverse charge transactions (Section 18a UStG):
- Due: 25th of following month
- Lists all reverse charge invoices to EU clients
- Requires client VAT IDs

## Tax Optimization Features

### Asset Depreciation (AfA)

Section 7 EStG defines depreciation methods:

**Immediate Write-Off (GWG)**
- Section 6 Abs. 2 EStG
- Assets under 800 EUR net
- Full deduction in purchase year
- Trivial assets under 250 EUR: no tracking required

**Pool Depreciation (Sammelposten)**
- Section 6 Abs. 2a EStG
- Assets 250-1,000 EUR net
- 5-year straight-line depreciation
- 20% per year regardless of useful life

**Linear Depreciation**
- Section 7 Abs. 1 EStG
- Assets over 1,000 EUR
- Even annual amounts over useful life
- Pro-rata for partial years

**Degressive Depreciation**
- Wachstumschancengesetz 2024
- Up to 2.5x linear rate
- Maximum 25% per year
- Switchover to linear allowed

**Digital AfA**
- BMF Circular 2021
- Computer hardware and software
- 1-year useful life permitted
- Full write-off in purchase year

**Useful Life Examples**:

| Asset | Years | Basis |
|-------|-------|-------|
| Computer | 3 | AfA-Tabelle |
| Software | 3 | AfA-Tabelle |
| Office furniture | 13 | AfA-Tabelle |
| Vehicle | 6 | AfA-Tabelle |

### Travel Expenses (Reisekosten)

Section 9 Abs. 4a EStG governs travel deductions:

**Per Diem (Verpflegungsmehraufwand)**

Domestic rates:

| Duration | Rate |
|----------|------|
| 8-24 hours | 14 EUR |
| Full 24 hours | 28 EUR |
| Travel day (arrival/departure) | 14 EUR |

**Meal Reductions**

When meals are provided:

| Meal | Reduction |
|------|-----------|
| Breakfast | 20% (5.60 EUR from 28 EUR) |
| Lunch | 40% (11.20 EUR from 28 EUR) |
| Dinner | 40% (11.20 EUR from 28 EUR) |

**Kilometer Allowance**

| Distance | Rate |
|----------|------|
| First 20 km | 0.30 EUR/km |
| Beyond 20 km | 0.38 EUR/km |

**Foreign Per Diem**

BMF publishes annual foreign rates. Examples:

| Country | Full Day | Arrival/Departure |
|---------|----------|-------------------|
| USA | 66 EUR | 44 EUR |
| UK | 52 EUR | 35 EUR |
| France | 53 EUR | 36 EUR |

### Gift Expenses (Geschenke)

Section 4 Abs. 5 Nr. 1 EStG limits gift deductions:

**50 EUR Limit**
- Maximum 50 EUR net per recipient per year
- Cumulative across all gifts
- **Cliff effect**: 50.01 EUR makes entire amount non-deductible

**Example**:
```
Gift 1: 30 EUR -> Deductible, cumulative: 30 EUR
Gift 2: 15 EUR -> Deductible, cumulative: 45 EUR
Gift 3: 10 EUR -> ALL 55 EUR non-deductible (exceeds 50 EUR)
```

**Flat Tax Option (Section 37b EStG)**
- 30% flat tax on gift value
- Paid by giver
- Recipient has no tax obligation

### Business Meals (Bewirtung)

Section 4 Abs. 5 Nr. 2 EStG:

| Type | Deductible |
|------|------------|
| Client entertainment | 70% |
| Staff events | 100% (max 110 EUR/person) |

**Required Documentation**:
- Date and location
- Names of all attendees
- Business purpose
- Restaurant receipt with tip separated

### Home Office

**Homeoffice-Pauschale**
- 6 EUR per day
- Maximum 210 days = 1,260 EUR/year
- No separate room required

**Arbeitszimmer (Section 4 Abs. 5 EStG)**
- Requires separate, dedicated room
- Deduct proportional rent and utilities
- Alternative: 1,260 EUR flat rate

### Health Insurance (Section 10 EStG)

Health insurance premiums (Vorsorgeaufwendungen):

**Unlimited Deduction**:
- Basic health insurance (Basiskrankenversicherung)
- Mandatory care insurance (Pflegepflichtversicherung)

**Limited Deduction (2,800 EUR/year for self-employed)**:
- Optional PKV services (Wahlleistungen)
- Supplementary insurance (Zusatzversicherung)

**GKV Reduction**:
- 4% reduction if entitled to Krankengeld
- Section 10 Abs. 1 Nr. 3a EStG

## Special Regulations

### Freiberufler Status (Section 18 EStG)

Freelancer categories include:
- Software developers (Programmierer)
- Consultants (Berater)
- Writers (Schriftsteller)
- Artists (Kuenstler)
- Engineers (Ingenieure)

Benefits:
- No Gewerbesteuer
- Simplified accounting (EUER)
- No trade registration required

### Scheinselbstaendigkeit

False self-employment indicators:
- Over 83% income from single client
- Integration into client's organization
- No entrepreneurial freedom
- Using client's equipment exclusively

FiscFox warns when income concentration exceeds 83%.

## Document Patterns

### Storno (Reversal)

German accounting requires immutable records. Corrections via reversal:

1. Create Storno (negative copy) of original
2. Create new correct record
3. Both entries preserved for audit

```
Original Invoice: +1,000 EUR
Storno: -1,000 EUR
Corrected Invoice: +1,100 EUR
Net Effect: +1,100 EUR
```

### EUER (Einnahmen-Ueberschuss-Rechnung)

Simplified accounting for freelancers:
- Cash basis (Zufluss-/Abflussprinzip)
- No balance sheet required
- Revenue minus expenses = profit

### ELSTER

Electronic tax filing system:
- USt-Voranmeldung (VAT returns)
- Zusammenfassende Meldung (EC Sales List)
- Annual tax declarations

## Glossary

| German | English | Description |
|--------|---------|-------------|
| Abschreibung | Depreciation | Asset value reduction over time |
| Absetzung fuer Abnutzung (AfA) | Depreciation | Legal term for depreciation |
| Betriebsausgaben | Business expenses | Deductible business costs |
| Bewirtungskosten | Entertainment expenses | Client entertainment costs |
| Einkommensteuer | Income tax | Tax on personal income |
| Einnahmen-Ueberschuss-Rechnung (EUER) | Revenue surplus calculation | Simplified accounting |
| Finanzamt | Tax office | Local tax authority |
| Freiberufler | Freelancer | Self-employed professional |
| Geringwertiges Wirtschaftsgut (GWG) | Low-value asset | Assets under 800 EUR |
| Geschenke | Gifts | Business gifts |
| Grundfreibetrag | Basic allowance | Tax-free income threshold |
| Homeoffice-Pauschale | Home office allowance | Flat rate home office deduction |
| Kirchensteuer | Church tax | Tax for church members |
| Kleinunternehmer | Small business | VAT-exempt small business |
| Nutzungsdauer | Useful life | Depreciation period |
| Reisekosten | Travel expenses | Business travel deductions |
| Scheinselbstaendigkeit | False self-employment | Disguised employment |
| Solidaritaetszuschlag | Solidarity surcharge | 5.5% income tax surcharge |
| Steuernummer | Tax number | Tax identification number |
| Storno | Reversal | Accounting correction |
| Umsatzsteuer (USt) | VAT | Value-added tax |
| USt-IdNr. | VAT ID | VAT identification number |
| USt-Voranmeldung | VAT return | Periodic VAT declaration |
| Verpflegungsmehraufwand | Per diem | Meal allowance |
| Vorauszahlung | Prepayment | Quarterly tax prepayment |
| Vorsteuer | Input VAT | VAT on purchases |
| Zahllast | VAT liability | Net VAT owed |
| Zusammenfassende Meldung | EC Sales List | EU B2B transaction report |

## Legal References

### Primary Legislation

| Law | Full Name | Scope |
|-----|-----------|-------|
| EStG | Einkommensteuergesetz | Income tax |
| UStG | Umsatzsteuergesetz | VAT |
| AO | Abgabenordnung | Tax procedures |
| SolZG | Solidaritaetszuschlaggesetz | Solidarity surcharge |
| KiStG | Kirchensteuergesetz | Church tax |

### Administrative Guidance

| Source | Description |
|--------|-------------|
| EStR | Einkommensteuer-Richtlinien |
| UStAE | Umsatzsteuer-Anwendungserlass |
| BMF-Schreiben | Federal Ministry circulars |
| AfA-Tabelle | Depreciation tables |

### Key Sections Referenced

**EStG**:
- Section 4 Abs. 5: Non-deductible expenses
- Section 6 Abs. 2: GWG immediate write-off
- Section 6 Abs. 2a: Pool depreciation
- Section 7: Depreciation methods
- Section 9 Abs. 4a: Travel expenses
- Section 10: Special expenses
- Section 18: Freelancer income
- Section 32a: Tax rate formula
- Section 37: Prepayments
- Section 37b: Flat tax on gifts

**UStG**:
- Section 13b: Reverse charge
- Section 15: Input VAT deduction
- Section 18a: EC Sales List
- Section 19: Small business exemption

### Online Resources

- [Bundesfinanzministerium](https://www.bundesfinanzministerium.de)
- [Gesetze im Internet](https://www.gesetze-im-internet.de)
- [ELSTER](https://www.elster.de)
- [BZSt](https://www.bzst.de) - VAT ID validation
