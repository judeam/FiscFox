-- FiscFox Database Schema
-- German Freelancer Tax Management System
--
-- All monetary values stored as TEXT (Decimal string) for precision.
-- SQLite stores DECIMAL as TEXT to preserve exact values.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA strict = ON;

-- =============================================================================
-- Core Tables
-- =============================================================================

-- Clients (Kunden)
-- Stores client details for invoicing and tax compliance
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(name) >= 1 AND length(name) <= 200),
    -- Address
    street TEXT DEFAULT '',
    address_details TEXT DEFAULT '',  -- Building, apartment, etc.
    zip_code TEXT DEFAULT '',
    city TEXT DEFAULT '',
    country TEXT DEFAULT 'DE' CHECK (length(country) = 2),  -- ISO 3166-1 alpha-2
    -- Contact
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    -- Tax Information (for Reverse Charge / Zusammenfassende Meldung, § 13b UStG)
    vat_id TEXT DEFAULT '',  -- EU VAT ID (e.g., DE123456789)
    -- Notes
    notes TEXT DEFAULT '',
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name);
CREATE INDEX IF NOT EXISTS idx_clients_country ON clients(country);


-- Business Expenses (Betriebsausgaben)
-- Tracks all deductible business expenses with VAT (Vorsteuer)
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    vendor TEXT NOT NULL CHECK (length(vendor) >= 1 AND length(vendor) <= 200),
    description TEXT NOT NULL CHECK (length(description) >= 3 AND length(description) <= 500),
    amount_gross TEXT NOT NULL,  -- Decimal string, gross amount including VAT
    amount_net TEXT NOT NULL,    -- Decimal string, calculated net amount
    vat_amount TEXT NOT NULL,    -- Decimal string, calculated VAT (Vorsteuer)
    vat_rate TEXT NOT NULL CHECK (vat_rate IN ('0.19', '0.07', '0.00')),
    category TEXT NOT NULL CHECK (category IN (
        'buero', 'software', 'hardware', 'reise',
        'kommunikation', 'versicherung', 'fortbildung',
        'bewirtung', 'geschenke', 'sonstiges'
    )),
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Soft delete for immutability
    deleted_at TIMESTAMP DEFAULT NULL,
    -- Storno reference for corrections
    storno_of INTEGER REFERENCES expenses(id),
    is_storno BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
CREATE INDEX IF NOT EXISTS idx_expenses_vendor ON expenses(vendor);


-- Client Invoices (Ausgangsrechnungen)
-- Tracks invoices sent to clients with VAT (Umsatzsteuer)
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Client reference (optional for backward compatibility, prefer client_id)
    client_id INTEGER REFERENCES clients(id),
    client TEXT NOT NULL CHECK (length(client) >= 1 AND length(client) <= 200),  -- Denormalized for display
    invoice_number TEXT NOT NULL UNIQUE,
    date DATE NOT NULL,
    due_date DATE,
    amount TEXT NOT NULL,        -- Decimal string, total amount
    amount_net TEXT NOT NULL,    -- Decimal string, net before VAT
    vat_amount TEXT NOT NULL,    -- Decimal string, VAT collected (Umsatzsteuer)
    vat_rate TEXT NOT NULL CHECK (vat_rate IN ('0.19', '0.07', '0.00')),
    description TEXT NOT NULL CHECK (length(description) >= 3 AND length(description) <= 1000),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'overdue')),
    paid_date DATE,
    -- Reverse Charge indicator for international B2B
    is_reverse_charge BOOLEAN DEFAULT FALSE,
    client_country TEXT,  -- ISO 3166-1 alpha-2 (e.g., 'US', 'SE', 'DE')
    client_vat_id TEXT,   -- EU VAT ID for Zusammenfassende Meldung
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL,
    -- Storno reference
    storno_of INTEGER REFERENCES invoices(id),
    is_storno BOOLEAN DEFAULT FALSE,
    -- Uploaded document reference (set when invoice created from PDF upload)
    uploaded_document_id INTEGER REFERENCES uploaded_documents(id)
);

CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(date);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_client ON invoices(client);
CREATE INDEX IF NOT EXISTS idx_invoices_client_id ON invoices(client_id);
CREATE INDEX IF NOT EXISTS idx_invoices_due_date ON invoices(due_date);


-- Tax Payments (Steuerzahlungen)
-- Tracks actual tax payments made (Vorauszahlungen, etc.)
CREATE TABLE IF NOT EXISTS tax_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN (
        'einkommensteuer', 'umsatzsteuer', 'gewerbesteuer',
        'solidaritaetszuschlag', 'kirchensteuer'
    )),
    period TEXT NOT NULL,  -- '2026-Q1', '2026-01', '2026' (annual)
    due_date DATE NOT NULL,
    amount TEXT NOT NULL,  -- Decimal string
    paid BOOLEAN DEFAULT FALSE,
    paid_date DATE,
    payment_reference TEXT,  -- Bank reference or Finanzamt Aktenzeichen
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tax_payments_type ON tax_payments(type);
CREATE INDEX IF NOT EXISTS idx_tax_payments_period ON tax_payments(period);
CREATE INDEX IF NOT EXISTS idx_tax_payments_due_date ON tax_payments(due_date);


-- Tax Reports (Steuermeldungen)
-- Tracks submitted tax reports (USt-Voranmeldung, etc.)
CREATE TABLE IF NOT EXISTS tax_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN (
        'ust_voranmeldung', 'zusammenfassende_meldung',
        'euer', 'steuererklaerung'
    )),
    period TEXT NOT NULL,  -- '2026-01', '2026-Q1', '2026'
    year INTEGER NOT NULL,
    -- Calculated values at time of submission
    umsatz_net TEXT,         -- Total net revenue
    umsatzsteuer TEXT,       -- USt collected
    vorsteuer TEXT,          -- Input VAT deductible
    zahllast TEXT,           -- Net VAT liability
    reverse_charge_total TEXT,  -- For Zusammenfassende Meldung
    -- Submission tracking
    submitted BOOLEAN DEFAULT FALSE,
    submitted_date DATE,
    elster_reference TEXT,   -- ELSTER submission reference
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tax_reports_type ON tax_reports(type);
CREATE INDEX IF NOT EXISTS idx_tax_reports_period ON tax_reports(period);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tax_reports_unique ON tax_reports(type, period);


-- =============================================================================
-- Settings & Configuration
-- =============================================================================

-- Application Settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default settings
INSERT OR IGNORE INTO settings (key, value, description) VALUES
    ('tax_year', '2026', 'Current tax year'),
    ('ust_frequency', 'monthly', 'USt-Voranmeldung frequency: monthly, quarterly, annual'),
    ('is_kleinunternehmer', 'false', 'Kleinunternehmerregelung (§ 19 UStG)'),
    ('is_freiberufler', 'true', 'Freiberufler status (exempt from Gewerbesteuer)'),
    ('has_eu_clients', 'true', 'Has EU clients requiring Zusammenfassende Meldung'),
    ('quarterly_est_amount', '3500.00', 'Quarterly ESt-Vorauszahlung amount'),
    ('business_name', 'Max Mustermann Softwareentwicklung', 'Business/freelancer name'),
    ('steuernummer', '', 'Tax number from Finanzamt'),
    ('ust_id', '', 'VAT ID (USt-IdNr.)'),
    ('finanzamt', '', 'Responsible Finanzamt');


-- =============================================================================
-- Audit Trail
-- =============================================================================

-- Change Log for audit trail
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE', 'STORNO')),
    old_values TEXT,  -- JSON of old values
    new_values TEXT,  -- JSON of new values
    user_id TEXT,     -- For future multi-user support
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_log_table ON audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_record ON audit_log(table_name, record_id);


-- =============================================================================
-- Views for Reporting
-- =============================================================================

-- Monthly Revenue Summary
CREATE VIEW IF NOT EXISTS v_monthly_revenue AS
SELECT
    strftime('%Y-%m', date) AS month,
    COUNT(*) AS invoice_count,
    SUM(CAST(amount_net AS REAL)) AS total_net,
    SUM(CAST(vat_amount AS REAL)) AS total_vat,
    SUM(CAST(amount AS REAL)) AS total_gross,
    SUM(CASE WHEN is_reverse_charge THEN CAST(amount_net AS REAL) ELSE 0 END) AS reverse_charge_total
FROM invoices
WHERE deleted_at IS NULL AND is_storno = FALSE
GROUP BY strftime('%Y-%m', date)
ORDER BY month DESC;


-- Monthly Expenses Summary
CREATE VIEW IF NOT EXISTS v_monthly_expenses AS
SELECT
    strftime('%Y-%m', date) AS month,
    COUNT(*) AS expense_count,
    SUM(CAST(amount_net AS REAL)) AS total_net,
    SUM(CAST(vat_amount AS REAL)) AS total_vorsteuer,
    SUM(CAST(amount_gross AS REAL)) AS total_gross
FROM expenses
WHERE deleted_at IS NULL AND is_storno = FALSE
GROUP BY strftime('%Y-%m', date)
ORDER BY month DESC;


-- Expense Category Breakdown
CREATE VIEW IF NOT EXISTS v_expense_categories AS
SELECT
    category,
    strftime('%Y', date) AS year,
    COUNT(*) AS expense_count,
    SUM(CAST(amount_net AS REAL)) AS total_net,
    SUM(CAST(vat_amount AS REAL)) AS total_vorsteuer
FROM expenses
WHERE deleted_at IS NULL AND is_storno = FALSE
GROUP BY category, strftime('%Y', date)
ORDER BY year DESC, total_net DESC;


-- VAT Summary (for USt-Voranmeldung)
CREATE VIEW IF NOT EXISTS v_vat_summary AS
SELECT
    strftime('%Y-%m', date) AS period,
    -- Invoices: USt collected
    (SELECT COALESCE(SUM(CAST(vat_amount AS REAL)), 0)
     FROM invoices
     WHERE strftime('%Y-%m', invoices.date) = strftime('%Y-%m', base.date)
       AND deleted_at IS NULL AND is_storno = FALSE) AS ust_collected,
    -- Expenses: Vorsteuer deductible
    (SELECT COALESCE(SUM(CAST(vat_amount AS REAL)), 0)
     FROM expenses
     WHERE strftime('%Y-%m', expenses.date) = strftime('%Y-%m', base.date)
       AND deleted_at IS NULL AND is_storno = FALSE) AS vorsteuer,
    -- Net liability
    (SELECT COALESCE(SUM(CAST(vat_amount AS REAL)), 0)
     FROM invoices
     WHERE strftime('%Y-%m', invoices.date) = strftime('%Y-%m', base.date)
       AND deleted_at IS NULL AND is_storno = FALSE) -
    (SELECT COALESCE(SUM(CAST(vat_amount AS REAL)), 0)
     FROM expenses
     WHERE strftime('%Y-%m', expenses.date) = strftime('%Y-%m', base.date)
       AND deleted_at IS NULL AND is_storno = FALSE) AS zahllast
FROM (
    SELECT DISTINCT date FROM invoices
    UNION
    SELECT DISTINCT date FROM expenses
) AS base
GROUP BY strftime('%Y-%m', date)
ORDER BY period DESC;


-- =============================================================================
-- Triggers for Audit Trail
-- =============================================================================

-- Expenses audit trigger
CREATE TRIGGER IF NOT EXISTS trg_expenses_audit_insert
AFTER INSERT ON expenses
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, new_values)
    VALUES ('expenses', NEW.id, 'INSERT',
            json_object(
                'vendor', NEW.vendor,
                'amount_gross', NEW.amount_gross,
                'category', NEW.category
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_expenses_audit_update
AFTER UPDATE ON expenses
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values)
    VALUES ('expenses', NEW.id, 'UPDATE',
            json_object(
                'vendor', OLD.vendor,
                'amount_gross', OLD.amount_gross,
                'category', OLD.category
            ),
            json_object(
                'vendor', NEW.vendor,
                'amount_gross', NEW.amount_gross,
                'category', NEW.category
            ));
END;


-- Invoices audit trigger
CREATE TRIGGER IF NOT EXISTS trg_invoices_audit_insert
AFTER INSERT ON invoices
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, new_values)
    VALUES ('invoices', NEW.id, 'INSERT',
            json_object(
                'client', NEW.client,
                'invoice_number', NEW.invoice_number,
                'amount', NEW.amount,
                'status', NEW.status
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_invoices_audit_update
AFTER UPDATE ON invoices
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values)
    VALUES ('invoices', NEW.id, 'UPDATE',
            json_object(
                'client', OLD.client,
                'amount', OLD.amount,
                'status', OLD.status
            ),
            json_object(
                'client', NEW.client,
                'amount', NEW.amount,
                'status', NEW.status
            ));
END;


-- Auto-update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS trg_expenses_updated_at
AFTER UPDATE ON expenses
BEGIN
    UPDATE expenses SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_invoices_updated_at
AFTER UPDATE ON invoices
BEGIN
    UPDATE invoices SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;


-- Clients audit trigger
CREATE TRIGGER IF NOT EXISTS trg_clients_audit_insert
AFTER INSERT ON clients
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, new_values)
    VALUES ('clients', NEW.id, 'INSERT',
            json_object(
                'name', NEW.name,
                'city', NEW.city,
                'country', NEW.country
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_clients_audit_update
AFTER UPDATE ON clients
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values)
    VALUES ('clients', NEW.id, 'UPDATE',
            json_object(
                'name', OLD.name,
                'city', OLD.city,
                'country', OLD.country
            ),
            json_object(
                'name', NEW.name,
                'city', NEW.city,
                'country', NEW.country
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_clients_updated_at
AFTER UPDATE ON clients
BEGIN
    UPDATE clients SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;


-- =============================================================================
-- Uploaded Documents (Invoice PDF Storage)
-- =============================================================================

-- Uploaded Documents
-- Stores uploaded invoice PDFs with extraction metadata
CREATE TABLE IF NOT EXISTS uploaded_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- File information
    filename TEXT NOT NULL CHECK (length(filename) >= 1 AND length(filename) <= 255),
    stored_filename TEXT NOT NULL UNIQUE,  -- UUID-based storage name
    file_path TEXT NOT NULL,               -- Relative path in uploads directory
    file_size INTEGER NOT NULL CHECK (file_size > 0),
    content_hash TEXT NOT NULL,            -- SHA-256 for duplicate detection
    mime_type TEXT DEFAULT 'application/pdf',
    -- Extraction metadata
    extraction_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (extraction_status IN ('pending', 'processing', 'completed', 'failed', 'manual')),
    extraction_confidence REAL CHECK (extraction_confidence IS NULL OR (extraction_confidence >= 0.0 AND extraction_confidence <= 1.0)),
    extraction_method TEXT CHECK (extraction_method IS NULL OR extraction_method IN ('text', 'ocr', 'ai', 'manual')),
    extracted_data TEXT,                   -- JSON blob of extracted invoice data
    extraction_errors TEXT,                -- JSON array of extraction issues/warnings
    -- Linking to invoice (set when extraction is confirmed)
    invoice_id INTEGER REFERENCES invoices(id),
    -- Audit fields
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    confirmed_at TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_uploaded_docs_status ON uploaded_documents(extraction_status);
CREATE INDEX IF NOT EXISTS idx_uploaded_docs_invoice ON uploaded_documents(invoice_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_docs_hash ON uploaded_documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_uploaded_docs_uploaded_at ON uploaded_documents(uploaded_at);


-- Add uploaded_document_id to invoices table for reverse lookup
-- Note: This is added via ALTER TABLE in migrations for existing databases


-- Uploaded Documents audit trigger
CREATE TRIGGER IF NOT EXISTS trg_uploaded_docs_audit_insert
AFTER INSERT ON uploaded_documents
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, new_values)
    VALUES ('uploaded_documents', NEW.id, 'INSERT',
            json_object(
                'filename', NEW.filename,
                'file_size', NEW.file_size,
                'extraction_status', NEW.extraction_status
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_uploaded_docs_audit_update
AFTER UPDATE ON uploaded_documents
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values)
    VALUES ('uploaded_documents', NEW.id, 'UPDATE',
            json_object(
                'extraction_status', OLD.extraction_status,
                'invoice_id', OLD.invoice_id
            ),
            json_object(
                'extraction_status', NEW.extraction_status,
                'invoice_id', NEW.invoice_id
            ));
END;


-- =============================================================================
-- Tax Optimization Tables (WISO Steuer Features)
-- =============================================================================

-- Fixed Assets (Anlagevermögen)
-- Tracks depreciable business assets with AfA calculations
-- Implements: GWG (§ 6 Abs. 2 EStG), Pool (§ 6 Abs. 2a), Digital AfA (BMF 2021)
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(name) >= 1 AND length(name) <= 200),
    description TEXT DEFAULT '',
    purchase_date DATE NOT NULL,
    -- Monetary values (all TEXT for Decimal precision)
    acquisition_cost TEXT NOT NULL,     -- Net purchase price
    vat_amount TEXT NOT NULL,           -- VAT paid (Vorsteuer)
    vat_rate TEXT NOT NULL CHECK (vat_rate IN ('0.19', '0.07', '0.00')),
    -- Asset classification
    category TEXT NOT NULL CHECK (category IN (
        'computer', 'software', 'office', 'vehicle',
        'furniture', 'machinery', 'other'
    )),
    useful_life_years INTEGER NOT NULL CHECK (useful_life_years > 0),
    -- Depreciation method
    -- immediate: GWG < 800 EUR, trivial < 250 EUR
    -- linear: Standard AfA (§ 7 Abs. 1 EStG)
    -- degressive: Up to 2.5x linear, max 25% (Wachstumschancengesetz)
    -- pool: Sammelposten 5 years (§ 6 Abs. 2a EStG)
    -- digital: 1-year write-off for IT (BMF 2021)
    depreciation_method TEXT NOT NULL CHECK (depreciation_method IN (
        'immediate', 'linear', 'degressive', 'pool', 'digital'
    )),
    pool_year INTEGER,  -- Year of pool assignment (for Sammelposten)
    -- Tracking
    current_book_value TEXT NOT NULL,   -- Residual value (Restbuchwert)
    total_depreciated TEXT DEFAULT '0', -- Sum of all depreciation
    depreciation_complete BOOLEAN DEFAULT FALSE,
    -- Mixed use (private/business)
    private_use_percent TEXT DEFAULT '0',  -- e.g., '0.20' for 20% private
    -- Disposal
    disposal_date DATE,
    disposal_amount TEXT,  -- Sale price
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
CREATE INDEX IF NOT EXISTS idx_assets_purchase_date ON assets(purchase_date);
CREATE INDEX IF NOT EXISTS idx_assets_method ON assets(depreciation_method);
CREATE INDEX IF NOT EXISTS idx_assets_pool_year ON assets(pool_year);


-- Depreciation Records (AfA-Buchungen)
-- Annual depreciation entries per asset
CREATE TABLE IF NOT EXISTS depreciation_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL REFERENCES assets(id),
    year INTEGER NOT NULL,
    -- Amounts
    depreciation_amount TEXT NOT NULL,  -- AfA for this year
    book_value_start TEXT NOT NULL,     -- Book value at year start
    book_value_end TEXT NOT NULL,       -- Book value at year end
    -- Method applied (may differ from asset default for switchover)
    method_applied TEXT NOT NULL CHECK (method_applied IN (
        'immediate', 'linear', 'degressive', 'pool', 'digital'
    )),
    -- Pro-rata calculation details
    months_applicable INTEGER DEFAULT 12,  -- Months of ownership this year
    notes TEXT,
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, year)
);

CREATE INDEX IF NOT EXISTS idx_depreciation_asset ON depreciation_records(asset_id);
CREATE INDEX IF NOT EXISTS idx_depreciation_year ON depreciation_records(year);


-- Travel Expenses (Reisekosten)
-- Per diem and km tracking per § 9 Abs. 4a EStG
CREATE TABLE IF NOT EXISTS travel_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    destination TEXT NOT NULL CHECK (length(destination) >= 1 AND length(destination) <= 200),
    purpose TEXT NOT NULL CHECK (length(purpose) >= 3 AND length(purpose) <= 500),
    -- Time tracking
    departure_time TEXT,  -- ISO format HH:MM or full timestamp
    return_time TEXT,
    absence_hours TEXT NOT NULL,  -- Decimal hours (calculated or manual)
    is_overnight BOOLEAN DEFAULT FALSE,
    is_travel_day BOOLEAN DEFAULT FALSE,  -- An-/Abreisetag (14 EUR)
    -- Km tracking (Fahrtkosten)
    km_driven TEXT DEFAULT '0',
    km_rate TEXT DEFAULT '0.30',  -- 0.30 first 20km, 0.38 after
    km_deduction TEXT DEFAULT '0',  -- Calculated: km * rate
    -- Per diem (Verpflegungsmehraufwand)
    country_code TEXT DEFAULT 'DE' CHECK (length(country_code) = 2),
    per_diem_rate TEXT NOT NULL,  -- 14/28 EUR domestic, varies foreign
    breakfast_provided BOOLEAN DEFAULT FALSE,
    lunch_provided BOOLEAN DEFAULT FALSE,
    dinner_provided BOOLEAN DEFAULT FALSE,
    meal_reduction TEXT DEFAULT '0',  -- Reduction for provided meals
    per_diem_deduction TEXT NOT NULL,  -- Final after reductions
    -- Total deduction
    total_deduction TEXT NOT NULL,
    -- Link to receipted expenses (fuel, parking, etc.)
    linked_expense_id INTEGER REFERENCES expenses(id),
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL,
    storno_of INTEGER REFERENCES travel_expenses(id),
    is_storno BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_travel_date ON travel_expenses(date);
CREATE INDEX IF NOT EXISTS idx_travel_country ON travel_expenses(country_code);


-- Gift Expenses (Geschenke)
-- Per-recipient tracking with 50 EUR limit (§ 4 Abs. 5 Nr. 1 EStG)
CREATE TABLE IF NOT EXISTS gift_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    recipient_name TEXT NOT NULL CHECK (length(recipient_name) >= 1 AND length(recipient_name) <= 200),
    recipient_company TEXT DEFAULT '',
    description TEXT NOT NULL CHECK (length(description) >= 3 AND length(description) <= 500),
    -- Amounts
    amount_net TEXT NOT NULL,
    vat_amount TEXT NOT NULL,
    vat_rate TEXT NOT NULL CHECK (vat_rate IN ('0.19', '0.07', '0.00')),
    -- Deductibility tracking
    is_deductible BOOLEAN DEFAULT TRUE,  -- False if cumulative > 50 EUR
    cumulative_year_total TEXT NOT NULL, -- Running total for recipient this year
    -- Optional flat tax (§ 37b EStG)
    flat_tax_paid BOOLEAN DEFAULT FALSE,
    flat_tax_amount TEXT DEFAULT '0',  -- 30% of gift value
    -- Link to regular expense entry
    expense_id INTEGER REFERENCES expenses(id),
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_gift_date ON gift_expenses(date);
CREATE INDEX IF NOT EXISTS idx_gift_recipient ON gift_expenses(recipient_name);
CREATE INDEX IF NOT EXISTS idx_gift_recipient_year ON gift_expenses(
    recipient_name, strftime('%Y', date)
);


-- Home Office Days (Homeoffice-Pauschale)
-- Tracks work-from-home days for 6 EUR/day deduction (max 210 days = 1260 EUR)
CREATE TABLE IF NOT EXISTS home_office_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL UNIQUE,
    hours TEXT,  -- Optional: hours worked from home
    notes TEXT DEFAULT '',
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_homeoffice_date ON home_office_days(date);
CREATE INDEX IF NOT EXISTS idx_homeoffice_year ON home_office_days(strftime('%Y', date));


-- Home Office Settings (annual configuration)
CREATE TABLE IF NOT EXISTS home_office_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER UNIQUE NOT NULL,
    -- Type of deduction (pauschale = 6 EUR/day, arbeitszimmer = room cost)
    method_type TEXT NOT NULL CHECK (method_type IN ('pauschale', 'arbeitszimmer')),
    -- For Arbeitszimmer: room details
    room_sqm TEXT,          -- Room size in sqm
    total_sqm TEXT,         -- Total home size in sqm
    monthly_rent TEXT,      -- Monthly rent
    monthly_utilities TEXT, -- Monthly utilities (Nebenkosten)
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- Business Meals Extended Data (Bewirtungskosten)
-- Links to expenses table for meals requiring attendee tracking
CREATE TABLE IF NOT EXISTS business_meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER NOT NULL REFERENCES expenses(id),
    -- Required fields (§ 4 Abs. 5 Nr. 2 EStG)
    attendees TEXT NOT NULL,  -- JSON array of names
    business_purpose TEXT NOT NULL CHECK (length(business_purpose) >= 10),
    is_internal BOOLEAN DEFAULT FALSE,  -- Staff event (100%) vs client (70%)
    attendee_count INTEGER NOT NULL DEFAULT 1,
    -- Calculated amounts
    deductible_amount TEXT NOT NULL,      -- 70% for clients, 100% capped for staff
    non_deductible_amount TEXT NOT NULL,  -- 30% for clients, excess for staff
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_meals_expense ON business_meals(expense_id);


-- =============================================================================
-- Audit Triggers for New Tables
-- =============================================================================

-- Assets audit trigger
CREATE TRIGGER IF NOT EXISTS trg_assets_audit_insert
AFTER INSERT ON assets
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, new_values)
    VALUES ('assets', NEW.id, 'INSERT',
            json_object(
                'name', NEW.name,
                'acquisition_cost', NEW.acquisition_cost,
                'depreciation_method', NEW.depreciation_method
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_assets_audit_update
AFTER UPDATE ON assets
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values)
    VALUES ('assets', NEW.id, 'UPDATE',
            json_object(
                'name', OLD.name,
                'current_book_value', OLD.current_book_value
            ),
            json_object(
                'name', NEW.name,
                'current_book_value', NEW.current_book_value
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_assets_updated_at
AFTER UPDATE ON assets
BEGIN
    UPDATE assets SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;


-- Travel expenses audit trigger
CREATE TRIGGER IF NOT EXISTS trg_travel_audit_insert
AFTER INSERT ON travel_expenses
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, new_values)
    VALUES ('travel_expenses', NEW.id, 'INSERT',
            json_object(
                'destination', NEW.destination,
                'total_deduction', NEW.total_deduction
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_travel_updated_at
AFTER UPDATE ON travel_expenses
BEGIN
    UPDATE travel_expenses SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;


-- Gift expenses audit trigger
CREATE TRIGGER IF NOT EXISTS trg_gift_audit_insert
AFTER INSERT ON gift_expenses
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, new_values)
    VALUES ('gift_expenses', NEW.id, 'INSERT',
            json_object(
                'recipient_name', NEW.recipient_name,
                'amount_net', NEW.amount_net,
                'is_deductible', NEW.is_deductible
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_gift_updated_at
AFTER UPDATE ON gift_expenses
BEGIN
    UPDATE gift_expenses SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;


-- =============================================================================
-- Views for Tax Optimization Reporting
-- =============================================================================

-- Annual Depreciation Summary
CREATE VIEW IF NOT EXISTS v_annual_depreciation AS
SELECT
    strftime('%Y', a.purchase_date) AS purchase_year,
    dr.year AS depreciation_year,
    a.category,
    a.depreciation_method,
    COUNT(DISTINCT a.id) AS asset_count,
    SUM(CAST(dr.depreciation_amount AS REAL)) AS total_depreciation,
    SUM(CAST(a.acquisition_cost AS REAL)) AS total_acquisition_cost
FROM assets a
LEFT JOIN depreciation_records dr ON a.id = dr.asset_id
WHERE a.deleted_at IS NULL
GROUP BY dr.year, a.category, a.depreciation_method
ORDER BY dr.year DESC, total_depreciation DESC;


-- Travel Expense Summary by Year
CREATE VIEW IF NOT EXISTS v_travel_summary AS
SELECT
    strftime('%Y', date) AS year,
    strftime('%m', date) AS month,
    COUNT(*) AS trip_count,
    SUM(CAST(km_driven AS REAL)) AS total_km,
    SUM(CAST(km_deduction AS REAL)) AS total_km_deduction,
    SUM(CAST(per_diem_deduction AS REAL)) AS total_per_diem,
    SUM(CAST(total_deduction AS REAL)) AS total_travel_deduction
FROM travel_expenses
WHERE deleted_at IS NULL AND is_storno = FALSE
GROUP BY strftime('%Y', date), strftime('%m', date)
ORDER BY year DESC, month DESC;


-- Gift Expense Summary by Recipient
CREATE VIEW IF NOT EXISTS v_gift_summary AS
SELECT
    recipient_name,
    strftime('%Y', date) AS year,
    COUNT(*) AS gift_count,
    SUM(CAST(amount_net AS REAL)) AS total_net,
    MAX(CAST(cumulative_year_total AS REAL)) AS final_cumulative,
    MIN(is_deductible) AS all_deductible  -- 0 if any non-deductible
FROM gift_expenses
WHERE deleted_at IS NULL
GROUP BY recipient_name, strftime('%Y', date)
ORDER BY year DESC, total_net DESC;


-- Home Office Summary by Year
CREATE VIEW IF NOT EXISTS v_home_office_summary AS
SELECT
    strftime('%Y', date) AS year,
    COUNT(*) AS days_claimed,
    SUM(CAST(amount AS REAL)) AS total_deduction,
    deduction_type
FROM home_office_days
GROUP BY strftime('%Y', date), deduction_type
ORDER BY year DESC;


-- =============================================================================
-- Health Insurance Tables (Krankenversicherung)
-- Implements § 10 Abs. 1 Nr. 3 EStG - Vorsorgeaufwand
-- =============================================================================

-- Health Insurance Providers (static data)
-- Contains GKV (gesetzliche) and PKV (private) providers
CREATE TABLE IF NOT EXISTS health_insurance_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE CHECK (length(name) >= 1 AND length(name) <= 200),
    short_name TEXT CHECK (length(short_name) <= 50),
    type TEXT NOT NULL CHECK (type IN ('gkv', 'pkv')),
    logo_filename TEXT,
    website TEXT,
    is_nationwide BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_health_providers_type ON health_insurance_providers(type);
CREATE INDEX IF NOT EXISTS idx_health_providers_name ON health_insurance_providers(name);


-- Health Insurance Payments (Krankenversicherungsbeiträge)
-- Tracks all health insurance payments with tax deductibility categories
CREATE TABLE IF NOT EXISTS health_insurance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    provider_id INTEGER NOT NULL REFERENCES health_insurance_providers(id),
    insurance_type TEXT NOT NULL CHECK (insurance_type IN ('gkv', 'pkv')),
    -- Coverage types per § 10 EStG
    -- basis_krankenversicherung: Basic health coverage (unlimited deduction)
    -- pflegepflichtversicherung: Mandatory care insurance (unlimited deduction)
    -- wahlleistungen: Optional PKV services (limited to 2,800 EUR/year)
    -- zusatzversicherung: Supplementary insurance (limited to 2,800 EUR/year)
    coverage_type TEXT NOT NULL CHECK (coverage_type IN (
        'basis_krankenversicherung',
        'pflegepflichtversicherung',
        'wahlleistungen',
        'zusatzversicherung'
    )),
    amount TEXT NOT NULL,  -- Decimal string
    -- For GKV: 4% reduction applies if Krankengeldanspruch exists (§ 10 Abs. 1 Nr. 3a EStG)
    has_krankengeld BOOLEAN DEFAULT FALSE,
    policy_number TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NULL,
    -- Storno support
    storno_of INTEGER REFERENCES health_insurance(id),
    is_storno BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_health_insurance_date ON health_insurance(date);
CREATE INDEX IF NOT EXISTS idx_health_insurance_type ON health_insurance(insurance_type);
CREATE INDEX IF NOT EXISTS idx_health_insurance_coverage ON health_insurance(coverage_type);
CREATE INDEX IF NOT EXISTS idx_health_insurance_provider ON health_insurance(provider_id);
CREATE INDEX IF NOT EXISTS idx_health_insurance_year ON health_insurance(strftime('%Y', date));


-- Health Insurance Audit Trigger
CREATE TRIGGER IF NOT EXISTS trg_health_insurance_audit_insert
AFTER INSERT ON health_insurance
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, new_values)
    VALUES ('health_insurance', NEW.id, 'INSERT',
            json_object(
                'provider_id', NEW.provider_id,
                'coverage_type', NEW.coverage_type,
                'amount', NEW.amount
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_health_insurance_audit_update
AFTER UPDATE ON health_insurance
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, old_values, new_values)
    VALUES ('health_insurance', NEW.id, 'UPDATE',
            json_object(
                'coverage_type', OLD.coverage_type,
                'amount', OLD.amount
            ),
            json_object(
                'coverage_type', NEW.coverage_type,
                'amount', NEW.amount
            ));
END;

CREATE TRIGGER IF NOT EXISTS trg_health_insurance_updated_at
AFTER UPDATE ON health_insurance
BEGIN
    UPDATE health_insurance SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;


-- Health Insurance Summary View
CREATE VIEW IF NOT EXISTS v_health_insurance_summary AS
SELECT
    strftime('%Y', date) AS year,
    insurance_type,
    coverage_type,
    COUNT(*) AS payment_count,
    SUM(CAST(amount AS REAL)) AS total_amount,
    SUM(CASE WHEN has_krankengeld THEN CAST(amount AS REAL) * 0.96 ELSE CAST(amount AS REAL) END) AS deductible_amount
FROM health_insurance
WHERE deleted_at IS NULL AND is_storno = FALSE
GROUP BY strftime('%Y', date), insurance_type, coverage_type
ORDER BY year DESC, insurance_type, coverage_type;


-- =============================================================================
-- Seed Data: Health Insurance Providers
-- =============================================================================

-- GKV (Gesetzliche Krankenversicherung) Providers
INSERT OR IGNORE INTO health_insurance_providers (name, short_name, type, logo_filename, website, is_nationwide) VALUES
    ('Techniker Krankenkasse', 'TK', 'gkv', 'tk.svg', 'https://www.tk.de', TRUE),
    ('BARMER', 'BARMER', 'gkv', 'barmer.svg', 'https://www.barmer.de', TRUE),
    ('DAK-Gesundheit', 'DAK', 'gkv', 'dak.svg', 'https://www.dak.de', TRUE),
    ('AOK Bayern - Die Gesundheitskasse', 'AOK BY', 'gkv', 'aok.svg', 'https://www.aok.de/bayern', FALSE),
    ('AOK Baden-Württemberg', 'AOK BW', 'gkv', 'aok.svg', 'https://www.aok.de/bw', FALSE),
    ('AOK Nordwest', 'AOK NW', 'gkv', 'aok.svg', 'https://www.aok.de/nordwest', FALSE),
    ('AOK Rheinland/Hamburg', 'AOK RH', 'gkv', 'aok.svg', 'https://www.aok.de/rheinland-hamburg', FALSE),
    ('AOK Niedersachsen', 'AOK NI', 'gkv', 'aok.svg', 'https://www.aok.de/niedersachsen', FALSE),
    ('AOK Plus (Sachsen/Thüringen)', 'AOK Plus', 'gkv', 'aok.svg', 'https://www.aokplus-online.de', FALSE),
    ('AOK Hessen', 'AOK HE', 'gkv', 'aok.svg', 'https://www.aok.de/hessen', FALSE),
    ('AOK Rheinland-Pfalz/Saarland', 'AOK RPS', 'gkv', 'aok.svg', 'https://www.aok.de/rps', FALSE),
    ('AOK Nordost', 'AOK NO', 'gkv', 'aok.svg', 'https://www.aok.de/nordost', FALSE),
    ('AOK Bremen/Bremerhaven', 'AOK HB', 'gkv', 'aok.svg', 'https://www.aok.de/bremen', FALSE),
    ('AOK Sachsen-Anhalt', 'AOK ST', 'gkv', 'aok.svg', 'https://www.aok.de/sachsen-anhalt', FALSE),
    ('IKK classic', 'IKK classic', 'gkv', 'ikk-classic.svg', 'https://www.ikk-classic.de', TRUE),
    ('IKK gesund plus', 'IKK gesund plus', 'gkv', 'ikk.svg', 'https://www.ikk-gesundplus.de', TRUE),
    ('IKK Südwest', 'IKK Südwest', 'gkv', 'ikk.svg', 'https://www.ikk-suedwest.de', FALSE),
    ('hkk Krankenkasse', 'hkk', 'gkv', 'hkk.svg', 'https://www.hkk.de', TRUE),
    ('KKH Kaufmännische Krankenkasse', 'KKH', 'gkv', 'kkh.svg', 'https://www.kkh.de', TRUE),
    ('KNAPPSCHAFT', 'Knappschaft', 'gkv', 'knappschaft.svg', 'https://www.knappschaft.de', TRUE),
    ('Mobil Krankenkasse', 'Mobil', 'gkv', 'mobil.svg', 'https://www.mobil-krankenkasse.de', TRUE),
    ('SBK Siemens-Betriebskrankenkasse', 'SBK', 'gkv', 'sbk.svg', 'https://www.sbk.org', TRUE),
    ('mhplus Krankenkasse', 'mhplus', 'gkv', 'mhplus.svg', 'https://www.mhplus.de', TRUE),
    ('Audi BKK', 'Audi BKK', 'gkv', 'audi-bkk.svg', 'https://www.audibkk.de', TRUE),
    ('BKK firmus', 'BKK firmus', 'gkv', 'bkk-firmus.svg', 'https://www.bkk-firmus.de', TRUE),
    ('BKK Pfalz', 'BKK Pfalz', 'gkv', 'bkk-pfalz.svg', 'https://www.bkk-pfalz.de', TRUE),
    ('BKK VBU', 'BKK VBU', 'gkv', 'bkk-vbu.svg', 'https://www.meine-krankenkasse.de', TRUE),
    ('Bertelsmann BKK', 'Bertelsmann BKK', 'gkv', 'bertelsmann-bkk.svg', 'https://www.bertelsmann-bkk.de', TRUE),
    ('Bosch BKK', 'Bosch BKK', 'gkv', 'bosch-bkk.svg', 'https://www.bosch-bkk.de', TRUE),
    ('BIG direkt gesund', 'BIG', 'gkv', 'big.svg', 'https://www.big-direkt.de', TRUE);

-- PKV (Private Krankenversicherung) Providers
INSERT OR IGNORE INTO health_insurance_providers (name, short_name, type, logo_filename, website, is_nationwide) VALUES
    ('HUK-COBURG Krankenversicherung AG', 'HUK-COBURG', 'pkv', 'huk-coburg.svg', 'https://www.huk.de', TRUE),
    ('Allianz Private Krankenversicherungs-AG', 'Allianz', 'pkv', 'allianz.svg', 'https://www.allianz.de', TRUE),
    ('Debeka Krankenversicherungsverein a.G.', 'Debeka', 'pkv', 'debeka.svg', 'https://www.debeka.de', TRUE),
    ('DKV Deutsche Krankenversicherung AG', 'DKV', 'pkv', 'dkv.svg', 'https://www.dkv.com', TRUE),
    ('AXA Krankenversicherung AG', 'AXA', 'pkv', 'axa.svg', 'https://www.axa.de', TRUE),
    ('SIGNAL IDUNA Krankenversicherung a.G.', 'Signal Iduna', 'pkv', 'signal-iduna.svg', 'https://www.signal-iduna.de', TRUE),
    ('Barmenia Krankenversicherung AG', 'Barmenia', 'pkv', 'barmenia.svg', 'https://www.barmenia.de', TRUE),
    ('HALLESCHE Krankenversicherung a.G.', 'Hallesche', 'pkv', 'hallesche.svg', 'https://www.hallesche.de', TRUE),
    ('HanseMerkur Krankenversicherung AG', 'HanseMerkur', 'pkv', 'hansemerkur.svg', 'https://www.hansemerkur.de', TRUE),
    ('Gothaer Krankenversicherung AG', 'Gothaer', 'pkv', 'gothaer.svg', 'https://www.gothaer.de', TRUE),
    ('Continentale Krankenversicherung a.G.', 'Continentale', 'pkv', 'continentale.svg', 'https://www.continentale.de', TRUE),
    ('Württembergische Krankenversicherung AG', 'Württembergische', 'pkv', 'wuerttembergische.svg', 'https://www.wuerttembergische.de', TRUE),
    ('Inter Krankenversicherung AG', 'Inter', 'pkv', 'inter.svg', 'https://www.inter.de', TRUE),
    ('LVM Krankenversicherungs-AG', 'LVM', 'pkv', 'lvm.svg', 'https://www.lvm.de', TRUE),
    ('Münchener Verein Krankenversicherung a.G.', 'Münchener Verein', 'pkv', 'muenchener-verein.svg', 'https://www.muenchener-verein.de', TRUE),
    ('NÜRNBERGER Krankenversicherung AG', 'Nürnberger', 'pkv', 'nuernberger.svg', 'https://www.nuernberger.de', TRUE),
    ('R+V Krankenversicherung AG', 'R+V', 'pkv', 'rv.svg', 'https://www.ruv.de', TRUE),
    ('SDK Süddeutsche Krankenversicherung a.G.', 'SDK', 'pkv', 'sdk.svg', 'https://www.sdk.de', TRUE),
    ('uniVersa Krankenversicherung a.G.', 'uniVersa', 'pkv', 'universa.svg', 'https://www.universa.de', TRUE),
    ('DEVK Krankenversicherungs-AG', 'DEVK', 'pkv', 'devk.svg', 'https://www.devk.de', TRUE),
    ('Alte Oldenburger Krankenversicherung AG', 'Alte Oldenburger', 'pkv', 'alte-oldenburger.svg', 'https://www.alte-oldenburger.de', TRUE),
    ('Bayerische Beamtenkrankenkasse AG', 'BBKK', 'pkv', 'bbkk.svg', 'https://www.bbkk.de', TRUE),
    ('Central Krankenversicherung AG', 'Central', 'pkv', 'central.svg', 'https://www.central.de', TRUE),
    ('Concordia Krankenversicherungs-AG', 'Concordia', 'pkv', 'concordia.svg', 'https://www.concordia.de', TRUE),
    ('Envivas Krankenversicherung AG', 'Envivas', 'pkv', 'envivas.svg', 'https://www.envivas.de', TRUE),
    ('Generali Deutschland Krankenversicherung AG', 'Generali', 'pkv', 'generali.svg', 'https://www.generali.de', TRUE),
    ('ottonova Krankenversicherung AG', 'ottonova', 'pkv', 'ottonova.svg', 'https://www.ottonova.de', TRUE),
    ('ARAG Krankenversicherungs-AG', 'ARAG', 'pkv', 'arag.svg', 'https://www.arag.de', TRUE),
    ('Landeskrankenhilfe V.V.a.G.', 'LKH', 'pkv', 'lkh.svg', 'https://www.lkh.de', TRUE),
    ('ERGO Krankenversicherung AG', 'ERGO', 'pkv', 'ergo.svg', 'https://www.ergo.de', TRUE);
