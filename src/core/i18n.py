"""Internationalization (i18n) module for FiscFox.

Provides translations for German and English.
"""
from collections.abc import Callable
from enum import StrEnum


class Language(StrEnum):
    """Supported languages."""
    DE = "de"  # German (default)
    EN = "en"  # English


# Translation dictionary: key -> {language: translation}
TRANSLATIONS: dict[str, dict[str, str]] = {
    # ==========================================================================
    # Navigation
    # ==========================================================================
    "nav.tax_management": {"de": "Steuerverwaltung", "en": "Tax Management"},
    "nav.dashboard": {"de": "Dashboard", "en": "Dashboard"},
    "nav.expenses": {"de": "Ausgaben", "en": "Expenses"},
    "nav.invoices": {"de": "Rechnungen", "en": "Invoices"},
    "nav.tax_deadlines": {"de": "Steuertermine", "en": "Tax Deadlines"},
    "nav.reports": {"de": "Berichte", "en": "Reports"},
    "nav.settings": {"de": "Einstellungen", "en": "Settings"},
    "nav.dark_mode": {"de": "Dunkelmodus", "en": "Dark Mode"},
    "nav.light_mode": {"de": "Hellmodus", "en": "Light Mode"},

    # ==========================================================================
    # Dashboard
    # ==========================================================================
    "dashboard.overview": {"de": "Übersicht", "en": "Overview"},
    "dashboard.greeting": {"de": "Guten Tag", "en": "Good Day"},
    "dashboard.tax_year": {"de": "Steuerjahr", "en": "Tax Year"},
    "dashboard.new_expense": {"de": "Neue Ausgabe", "en": "New Expense"},
    "dashboard.new_invoice": {"de": "Neue Rechnung", "en": "New Invoice"},
    "dashboard.all": {"de": "Alle", "en": "All"},
    "dashboard.open": {"de": "Offen", "en": "Open"},
    "dashboard.paid": {"de": "Bezahlt", "en": "Paid"},
    "dashboard.overdue": {"de": "Überfällig", "en": "Overdue"},
    "dashboard.prepayments": {"de": "Vorauszahlungen", "en": "Prepayments"},
    "dashboard.income_forecast": {"de": "Einkommensprognose", "en": "Income Forecast"},
    "dashboard.actual": {"de": "Tatsächlich", "en": "Actual"},
    "dashboard.forecast": {"de": "Prognose", "en": "Forecast"},
    "dashboard.confidence": {"de": "95% Konfidenz", "en": "95% Confidence"},
    "dashboard.no_data_yet": {"de": "Noch keine Rechnungsdaten", "en": "No invoice data yet"},
    "dashboard.add_invoices_hint": {"de": "Erstellen Sie Rechnungen, um die Prognose zu sehen", "en": "Create invoices to see the forecast"},
    "dashboard.tax_overview": {"de": "Steuerübersicht", "en": "Tax Overview"},
    "dashboard.gp_subtitle": {"de": "Bayessche Prognose mit 6-Monats-Vorschau", "en": "Bayesian forecast with 6-month lookahead"},
    "dashboard.gp_mean": {"de": "GP-Mittelwert", "en": "GP Mean"},
    "dashboard.bayesian": {"de": "Bayessch", "en": "Bayesian"},
    "dashboard.expense": {"de": "Ausgabe", "en": "Expense"},
    "dashboard.invoice": {"de": "Rechnung", "en": "Invoice"},

    # Table headers
    "table.client": {"de": "Kunde", "en": "Client"},
    "table.date": {"de": "Datum", "en": "Date"},
    "table.amount": {"de": "Betrag", "en": "Amount"},
    "table.status": {"de": "Status", "en": "Status"},
    "table.vendor": {"de": "Lieferant", "en": "Vendor"},
    "table.category": {"de": "Kategorie", "en": "Category"},
    "table.description": {"de": "Beschreibung", "en": "Description"},
    "table.due_date": {"de": "Fällig", "en": "Due"},
    "table.quarter": {"de": "Quartal", "en": "Quarter"},
    "table.actions": {"de": "Aktionen", "en": "Actions"},
    "table.net": {"de": "Netto", "en": "Net"},
    "table.gross": {"de": "Brutto", "en": "Gross"},

    # ==========================================================================
    # Stats Cards
    # ==========================================================================
    "stats.revenue": {"de": "Umsatz", "en": "Revenue"},
    "stats.expenses": {"de": "Ausgaben", "en": "Expenses"},
    "stats.vat_collected": {"de": "USt. Eingenommen", "en": "VAT Collected"},
    "stats.estimated_tax": {"de": "Geschätzte Steuer", "en": "Estimated Tax"},
    "stats.vs_last_year": {"de": "ggü. Vorjahr", "en": "vs Last Year"},
    "stats.next_ust": {"de": "Nächste USt-Voranm.", "en": "Next VAT Return"},
    "stats.ytd": {"de": "Jahr bis dato", "en": "Year to Date"},

    # ==========================================================================
    # Expenses
    # ==========================================================================
    "expense.title": {"de": "Ausgaben", "en": "Expenses"},
    "expense.add": {"de": "Ausgabe hinzufügen", "en": "Add Expense"},
    "expense.edit": {"de": "Ausgabe bearbeiten", "en": "Edit Expense"},
    "expense.delete": {"de": "Ausgabe löschen", "en": "Delete Expense"},
    "expense.gross_amount": {"de": "Bruttobetrag", "en": "Gross Amount"},
    "expense.net_amount": {"de": "Nettobetrag", "en": "Net Amount"},
    "expense.vat_amount": {"de": "MwSt.-Betrag", "en": "VAT Amount"},
    "expense.vat_rate": {"de": "MwSt.-Satz", "en": "VAT Rate"},
    "expense.no_expenses": {"de": "Keine Ausgaben vorhanden", "en": "No expenses found"},

    # Categories
    "category.buero": {"de": "Büro", "en": "Office"},
    "category.software": {"de": "Software", "en": "Software"},
    "category.hardware": {"de": "Hardware", "en": "Hardware"},
    "category.reise": {"de": "Reise", "en": "Travel"},
    "category.kommunikation": {"de": "Kommunikation", "en": "Communication"},
    "category.versicherung": {"de": "Versicherung", "en": "Insurance"},
    "category.fortbildung": {"de": "Fortbildung", "en": "Training"},
    "category.bewirtung": {"de": "Bewirtung", "en": "Business Meals"},
    "category.geschenke": {"de": "Geschenke", "en": "Gifts"},
    "category.sonstiges": {"de": "Sonstiges", "en": "Other"},

    # ==========================================================================
    # Invoices
    # ==========================================================================
    "invoice.title": {"de": "Rechnungen", "en": "Invoices"},
    "invoice.add": {"de": "Rechnung erstellen", "en": "Create Invoice"},
    "invoice.edit": {"de": "Rechnung bearbeiten", "en": "Edit Invoice"},
    "invoice.delete": {"de": "Rechnung löschen", "en": "Delete Invoice"},
    "invoice.preview": {"de": "Vorschau", "en": "Preview"},
    "invoice.download": {"de": "Herunterladen", "en": "Download"},
    "invoice.mark_paid": {"de": "Als bezahlt markieren", "en": "Mark as Paid"},
    "invoice.number": {"de": "Rechnungsnummer", "en": "Invoice Number"},
    "invoice.issue_date": {"de": "Rechnungsdatum", "en": "Invoice Date"},
    "invoice.due_date": {"de": "Fälligkeitsdatum", "en": "Due Date"},
    "invoice.subtotal": {"de": "Zwischensumme", "en": "Subtotal"},
    "invoice.total": {"de": "Gesamtbetrag", "en": "Total"},
    "invoice.no_invoices": {"de": "Keine Rechnungen vorhanden", "en": "No invoices found"},
    "invoice.create_first_hint": {"de": "Erstellen Sie Ihre erste Rechnung", "en": "Create your first invoice"},
    "invoice.due": {"de": "Fällig", "en": "Due"},
    "invoice.new": {"de": "neu", "en": "new"},
    "invoice.open": {"de": "offen", "en": "open"},
    "invoice.reminders": {"de": "Mahnungen", "en": "Reminders"},
    "invoice.revenue": {"de": "Umsatz", "en": "Revenue"},

    # Status
    "status.pending": {"de": "Offen", "en": "Pending"},
    "status.paid": {"de": "Bezahlt", "en": "Paid"},
    "status.overdue": {"de": "Überfällig", "en": "Overdue"},

    # ==========================================================================
    # Tax
    # ==========================================================================
    "tax.title": {"de": "Steuertermine", "en": "Tax Deadlines"},
    "tax.income_tax": {"de": "Einkommensteuer", "en": "Income Tax"},
    "tax.vat": {"de": "Umsatzsteuer", "en": "VAT"},
    "tax.trade_tax": {"de": "Gewerbesteuer", "en": "Trade Tax"},
    "tax.solidarity_surcharge": {"de": "Solidaritätszuschlag", "en": "Solidarity Surcharge"},
    "tax.church_tax": {"de": "Kirchensteuer", "en": "Church Tax"},
    "tax.vat_return": {"de": "USt-Voranmeldung", "en": "VAT Return"},
    "tax.days_remaining": {"de": "Tage verbleibend", "en": "days remaining"},
    "tax.due_today": {"de": "Heute fällig", "en": "Due today"},
    "tax.overdue": {"de": "Überfällig", "en": "Overdue"},
    "tax.quarterly_payment": {"de": "Vierteljährliche Vorauszahlung", "en": "Quarterly Prepayment"},
    "tax.estimated_liability": {"de": "Geschätzte Steuerlast", "en": "Estimated Tax Liability"},
    "tax.effective_rate": {"de": "Effektiver Steuersatz", "en": "Effective Tax Rate"},

    # ==========================================================================
    # Reports
    # ==========================================================================
    "report.title": {"de": "Berichte", "en": "Reports"},
    "report.monthly_summary": {"de": "Monatliche Zusammenfassung", "en": "Monthly Summary"},
    "report.annual_overview": {"de": "Jahresübersicht", "en": "Annual Overview"},
    "report.expense_by_category": {"de": "Ausgaben nach Kategorie", "en": "Expenses by Category"},
    "report.revenue_by_client": {"de": "Umsatz nach Kunde", "en": "Revenue by Client"},
    "report.export": {"de": "Exportieren", "en": "Export"},
    "report.print": {"de": "Drucken", "en": "Print"},

    # ==========================================================================
    # Settings
    # ==========================================================================
    "settings.title": {"de": "Einstellungen", "en": "Settings"},
    "settings.configuration": {"de": "Konfiguration", "en": "Configuration"},
    "settings.description": {
        "de": "Verwalten Sie Ihre Geschäftsinformationen für Rechnungen und Steuererklärungen. Diese Daten werden automatisch in Ihren Rechnungsvorlagen verwendet.",
        "en": "Manage your business information for invoices and tax returns. This data will be automatically used in your invoice templates."
    },
    "settings.saved": {"de": "Einstellungen gespeichert", "en": "Settings saved"},

    # Business Identity
    "settings.business_identity": {"de": "Geschäftsidentität", "en": "Business Identity"},
    "settings.business_identity_desc": {"de": "Ihr Firmenname erscheint auf allen Rechnungen", "en": "Your business name appears on all invoices"},
    "settings.business_name": {"de": "Firmenname / Vollständiger Name", "en": "Business Name / Full Name"},

    # Address
    "settings.business_address": {"de": "Geschäftsadresse", "en": "Business Address"},
    "settings.business_address_desc": {"de": "Wird im Briefkopf Ihrer Rechnungen angezeigt", "en": "Displayed in the letterhead of your invoices"},
    "settings.street": {"de": "Straße und Hausnummer", "en": "Street and Number"},
    "settings.address_details": {"de": "Adresszusatz", "en": "Address Details"},
    "settings.zip_code": {"de": "Postleitzahl", "en": "Postal Code"},
    "settings.city": {"de": "Stadt", "en": "City"},
    "settings.country": {"de": "Land", "en": "Country"},

    # Contact
    "settings.contact": {"de": "Kontaktdaten", "en": "Contact Information"},
    "settings.contact_desc": {"de": "So können Ihre Kunden Sie erreichen", "en": "How your clients can reach you"},
    "settings.phone": {"de": "Telefon", "en": "Phone"},
    "settings.email": {"de": "E-Mail", "en": "Email"},
    "settings.website": {"de": "Website", "en": "Website"},

    # Tax Information
    "settings.tax_info": {"de": "Steuerinformationen", "en": "Tax Information"},
    "settings.tax_info_desc": {"de": "Pflichtangaben gemäß §14 UStG", "en": "Required information per §14 UStG"},
    "settings.vat_id": {"de": "USt-IdNr.", "en": "VAT ID"},
    "settings.vat_id_desc": {"de": "Umsatzsteuer-Identifikationsnummer", "en": "Value Added Tax Identification Number"},
    "settings.tax_number": {"de": "Steuernummer", "en": "Tax Number"},
    "settings.tax_number_desc": {"de": "Vom Finanzamt zugewiesene Nummer", "en": "Number assigned by the tax office"},
    "settings.required": {"de": "Pflichtfeld", "en": "Required"},

    # Bank Details
    "settings.bank_details": {"de": "Bankverbindung", "en": "Bank Details"},
    "settings.bank_details_desc": {"de": "Für Zahlungsinformationen auf Rechnungen", "en": "For payment information on invoices"},
    "settings.bank_name": {"de": "Bank", "en": "Bank"},
    "settings.iban": {"de": "IBAN", "en": "IBAN"},
    "settings.bic_swift": {"de": "BIC / SWIFT", "en": "BIC / SWIFT"},

    # Invoice Preferences
    "settings.invoice_prefs": {"de": "Rechnungseinstellungen", "en": "Invoice Settings"},
    "settings.invoice_prefs_desc": {"de": "Standardwerte für neue Rechnungen", "en": "Default values for new invoices"},
    "settings.payment_terms": {"de": "Zahlungsziel (Tage)", "en": "Payment Terms (Days)"},
    "settings.default_vat_rate": {"de": "Standard MwSt.-Satz", "en": "Default VAT Rate"},
    "settings.invoice_prefix": {"de": "Rechnungsnummer-Präfix", "en": "Invoice Number Prefix"},

    # Display Preferences
    "settings.display_prefs": {"de": "Anzeigeoptionen", "en": "Display Options"},
    "settings.display_prefs_desc": {"de": "Formatierung und Darstellung", "en": "Formatting and Display"},
    "settings.currency": {"de": "Währung", "en": "Currency"},
    "settings.date_format": {"de": "Datumsformat", "en": "Date Format"},
    "settings.language": {"de": "Sprache", "en": "Language"},
    "settings.tax_year": {"de": "Steuerjahr", "en": "Tax Year"},
    "settings.tax_year_desc": {"de": "Wähle das Jahr für Statistiken und Berichte", "en": "Select the year for statistics and reports"},
    "settings.current": {"de": "Aktuell", "en": "Current"},

    # Save
    "settings.save": {"de": "Einstellungen speichern", "en": "Save Settings"},
    "settings.save_note": {"de": "Änderungen werden sofort auf neue Rechnungen angewendet", "en": "Changes will be applied immediately to new invoices"},

    # Tax Obligation Settings
    "settings.tax_obligations": {"de": "Steuerpflichten", "en": "Tax Obligations"},
    "settings.tax_obligations_desc": {"de": "Legen Sie fest, welche Steuermeldungen für Sie relevant sind", "en": "Configure which tax filings apply to you"},
    "settings.is_freiberufler": {"de": "Freiberufler (§ 18 EStG)", "en": "Freelancer (§ 18 EStG)"},
    "settings.is_freiberufler_desc": {"de": "Befreit von Gewerbesteuer-Vorauszahlungen", "en": "Exempt from trade tax prepayments"},
    "settings.has_eu_clients": {"de": "EU-Kunden (Zusammenfassende Meldung)", "en": "EU Clients (EC Sales List)"},
    "settings.has_eu_clients_desc": {"de": "Innergemeinschaftliche Leistungen erfordern monatliche ZM", "en": "Intra-community services require monthly EC Sales List"},
    "settings.ust_frequency": {"de": "USt-Voranmeldung Häufigkeit", "en": "VAT Return Frequency"},
    "settings.ust_monthly": {"de": "Monatlich", "en": "Monthly"},
    "settings.ust_quarterly": {"de": "Vierteljährlich", "en": "Quarterly"},
    "settings.ust_annual": {"de": "Jährlich", "en": "Annually"},
    "settings.ust_frequency_desc": {"de": "Basiert auf Vorjahres-USt (> €9.000 = monatlich)", "en": "Based on prior year VAT (> €9,000 = monthly)"},
    "settings.quarterly_est_amount": {"de": "ESt-Vorauszahlung pro Quartal", "en": "Income Tax Prepayment per Quarter"},
    "settings.quarterly_est_desc": {"de": "Laut Vorauszahlungsbescheid vom Finanzamt", "en": "As per prepayment notice from tax office"},
    "settings.activity_start_date": {"de": "Beginn der Tätigkeit", "en": "Start of Activity"},
    "settings.activity_start_date_hint": {"de": "Daten vor diesem Datum werden ignoriert", "en": "Data before this date will be ignored"},

    # ==========================================================================
    # Common Actions
    # ==========================================================================
    "action.save": {"de": "Speichern", "en": "Save"},
    "action.cancel": {"de": "Abbrechen", "en": "Cancel"},
    "action.delete": {"de": "Löschen", "en": "Delete"},
    "action.edit": {"de": "Bearbeiten", "en": "Edit"},
    "action.add": {"de": "Hinzufügen", "en": "Add"},
    "action.close": {"de": "Schließen", "en": "Close"},
    "action.confirm": {"de": "Bestätigen", "en": "Confirm"},
    "action.update": {"de": "Aktualisieren", "en": "Update"},
    "action.search": {"de": "Suchen", "en": "Search"},
    "action.filter": {"de": "Filtern", "en": "Filter"},
    "action.export": {"de": "Exportieren", "en": "Export"},
    "action.import": {"de": "Importieren", "en": "Import"},

    # ==========================================================================
    # Common Labels
    # ==========================================================================
    "label.optional": {"de": "optional", "en": "optional"},
    "label.required": {"de": "erforderlich", "en": "required"},
    "label.yes": {"de": "Ja", "en": "Yes"},
    "label.no": {"de": "Nein", "en": "No"},
    "label.total": {"de": "Gesamt", "en": "Total"},
    "label.net": {"de": "Netto", "en": "Net"},
    "label.gross": {"de": "Brutto", "en": "Gross"},
    "label.days": {"de": "Tage", "en": "days"},

    # ==========================================================================
    # VAT Rates
    # ==========================================================================
    "vat.standard": {"de": "19% (Standard)", "en": "19% (Standard)"},
    "vat.reduced": {"de": "7% (Ermäßigt)", "en": "7% (Reduced)"},
    "vat.zero": {"de": "0% (Reverse Charge / EU B2B)", "en": "0% (Reverse Charge / EU B2B)"},

    # ==========================================================================
    # Date Formats
    # ==========================================================================
    "date_format.iso": {"de": "ISO (2026-01-08)", "en": "ISO (2026-01-08)"},
    "date_format.german": {"de": "Deutsch (08.01.2026)", "en": "German (08.01.2026)"},
    "date_format.us": {"de": "US (01/08/2026)", "en": "US (01/08/2026)"},

    # ==========================================================================
    # Languages
    # ==========================================================================
    "language.de": {"de": "Deutsch", "en": "German"},
    "language.en": {"de": "Englisch", "en": "English"},

    # ==========================================================================
    # Expense Page Stats
    # ==========================================================================
    "expense.business_expenses": {"de": "Betriebsausgaben", "en": "Business Expenses"},
    "expense.total_gross": {"de": "Brutto Gesamt", "en": "Total Gross"},
    "expense.total_net": {"de": "Netto Gesamt", "en": "Total Net"},
    "expense.tax_deductible": {"de": "Steuerlich absetzbar", "en": "Tax Deductible"},
    "expense.input_vat": {"de": "Vorsteuer", "en": "Input VAT"},
    "expense.refundable": {"de": "Erstattungsfähig", "en": "Refundable"},
    "expense.receipt_count": {"de": "Anzahl Belege", "en": "Receipt Count"},
    "expense.this_month": {"de": "diesen Monat", "en": "this month"},
    "expense.this_month_short": {"de": "Monat", "en": "month"},
    "expense.new_expense": {"de": "Neue Ausgabe", "en": "New Expense"},
    "expense.record_expense": {"de": "Neue Ausgabe erfassen", "en": "Record New Expense"},
    "expense.confirm_delete": {"de": "Diese Ausgabe wirklich löschen?", "en": "Really delete this expense?"},
    "expense.by_category": {"de": "Nach Kategorie", "en": "By Category"},
    "expense.monthly_expenses": {"de": "Monatliche Ausgaben", "en": "Monthly Expenses"},
    "expense.top_vendors": {"de": "Top Anbieter", "en": "Top Vendors"},
    "expense.receipts": {"de": "Belege", "en": "Receipts"},
    "expense.deductible": {"de": "Absetzbar", "en": "Deductible"},
    "expense.recoverable": {"de": "Erstattbar", "en": "Recoverable"},
    "expense.new": {"de": "neu", "en": "new"},
    "expense.search": {"de": "Suchen...", "en": "Search..."},
    "expense.create_first_hint": {"de": "Erfasse deine erste Ausgabe", "en": "Record your first expense"},

    # Receipt OCR
    "expense.scan_receipt": {"de": "Beleg scannen", "en": "Scan Receipt"},
    "expense.ocr.scan_receipt": {"de": "Beleg scannen", "en": "Scan Receipt"},
    "expense.ocr.engine": {"de": "OCR-Engine", "en": "OCR Engine"},
    "expense.ocr.no_engine": {"de": "Nicht verfügbar", "en": "Not available"},
    "expense.ocr.status": {"de": "OCR Status", "en": "OCR Status"},
    "expense.ocr.ready": {"de": "Bereit", "en": "Ready"},
    "expense.ocr.unavailable": {"de": "Nicht verfügbar", "en": "Unavailable"},
    "expense.ocr.drop_receipt": {"de": "Beleg hier ablegen oder klicken", "en": "Drop receipt here or click"},
    "expense.ocr.supported_formats": {"de": "JPG, PNG, TIFF, WebP", "en": "JPG, PNG, TIFF, WebP"},
    "expense.ocr.use_ai": {"de": "KI-Verbesserung (bei niedriger Konfidenz)", "en": "AI enhancement (for low confidence)"},
    "expense.ocr.scanning": {"de": "Beleg wird gescannt...", "en": "Scanning receipt..."},
    "expense.ocr.scan_button": {"de": "Scannen", "en": "Scan"},
    "expense.ocr.scan_failed": {"de": "Scannen fehlgeschlagen", "en": "Scan Failed"},
    "expense.ocr.unsupported_format": {"de": "Nicht unterstütztes Format. Bitte verwenden Sie: {formats}", "en": "Unsupported format. Please use: {formats}"},
    "expense.ocr.read_error": {"de": "Fehler beim Lesen der Datei", "en": "Error reading file"},
    "expense.ocr.extraction_failed": {"de": "Datenextraktion fehlgeschlagen", "en": "Data extraction failed"},
    "expense.ocr.suggestions": {"de": "Tipps für bessere Ergebnisse:", "en": "Tips for better results:"},
    "expense.ocr.tip_lighting": {"de": "Gute Beleuchtung beim Fotografieren", "en": "Good lighting when taking photo"},
    "expense.ocr.tip_flat": {"de": "Beleg flach und gerade auslegen", "en": "Place receipt flat and straight"},
    "expense.ocr.tip_quality": {"de": "Hohe Bildauflösung verwenden", "en": "Use high image resolution"},
    "expense.ocr.tip_format": {"de": "JPG oder PNG Format bevorzugen", "en": "Prefer JPG or PNG format"},
    "expense.ocr.try_again": {"de": "Erneut versuchen", "en": "Try Again"},
    "expense.ocr.scan_result": {"de": "Scan-Ergebnis", "en": "Scan Result"},
    "expense.ocr.extracted_data": {"de": "Extrahierte Daten", "en": "Extracted Data"},
    "expense.ocr.review_data": {"de": "Bitte überprüfen Sie die extrahierten Daten", "en": "Please review the extracted data"},
    "expense.ocr.confidence": {"de": "Konfidenz", "en": "Confidence"},
    "expense.ocr.confidence_high": {"de": "Hoch", "en": "High"},
    "expense.ocr.confidence_medium": {"de": "Mittel", "en": "Medium"},
    "expense.ocr.confidence_low": {"de": "Niedrig", "en": "Low"},
    "expense.ocr.detected_items": {"de": "Erkannte Positionen", "en": "Detected Items"},
    "expense.ocr.processing_time": {"de": "Verarbeitungszeit", "en": "Processing Time"},
    "expense.ocr.save_expense": {"de": "Ausgabe speichern", "en": "Save Expense"},
    "expense.ocr.scan_another": {"de": "Weiteren scannen", "en": "Scan Another"},

    # ==========================================================================
    # Invoice Page Stats
    # ==========================================================================
    "invoice.customer_invoices": {"de": "Kundenrechnungen", "en": "Customer Invoices"},
    "invoice.total_revenue": {"de": "Gesamtumsatz", "en": "Total Revenue"},
    "invoice.invoices_count": {"de": "Rechnungen", "en": "invoices"},
    "invoice.outstanding": {"de": "Ausstehend", "en": "Outstanding"},
    "invoice.open_invoices": {"de": "offene Rechnungen", "en": "open invoices"},
    "invoice.reminders_needed": {"de": "Mahnungen erforderlich", "en": "reminders needed"},
    "invoice.no_reminders": {"de": "Keine Mahnungen", "en": "No reminders"},
    "invoice.this_month": {"de": "Diesen Monat", "en": "This Month"},
    "invoice.new_invoices": {"de": "neue Rechnungen", "en": "new invoices"},
    "invoice.create_new": {"de": "Neue Rechnung erstellen", "en": "Create New Invoice"},
    "invoice.revenue_by_client": {"de": "Umsatz nach Kunde", "en": "Revenue by Client"},
    "invoice.monthly_revenue": {"de": "Monatlicher Umsatz", "en": "Monthly Revenue"},
    "invoice.vat_summary": {"de": "USt. Zusammenfassung", "en": "VAT Summary"},
    "invoice.reverse_charge": {"de": "Reverse Charge (0%)", "en": "Reverse Charge (0%)"},
    "invoice.collected_vat": {"de": "Gesammelte USt.", "en": "Collected VAT"},
    "invoice.preview_print": {"de": "Vorschau & Drucken", "en": "Preview & Print"},
    "invoice.details": {"de": "Details", "en": "Details"},

    # Form Labels
    "form.date": {"de": "Datum", "en": "Date"},
    "form.vendor": {"de": "Lieferant/Dienstleister", "en": "Vendor/Service Provider"},
    "form.vendor_placeholder": {"de": "z.B. Amazon, Deutsche Bahn", "en": "e.g. Amazon, Deutsche Bahn"},
    "form.gross_amount": {"de": "Bruttobetrag (€)", "en": "Gross Amount (€)"},
    "form.amount": {"de": "Betrag (€)", "en": "Amount (€)"},
    "form.vat_rate": {"de": "MwSt.-Satz", "en": "VAT Rate"},
    "form.ust_rate": {"de": "USt.-Satz", "en": "VAT Rate"},
    "form.category": {"de": "Kategorie", "en": "Category"},
    "form.description": {"de": "Beschreibung", "en": "Description"},
    "form.description_placeholder": {"de": "Kurze Beschreibung der Ausgabe", "en": "Brief description of expense"},
    "form.client": {"de": "Kunde", "en": "Client"},
    "form.select_client": {"de": "Kunde auswählen", "en": "Select client"},
    "form.new_client": {"de": "Neuer Kunde", "en": "New Client"},
    "form.client_placeholder": {"de": "z.B. SAP SE", "en": "e.g. SAP SE"},
    "form.invoice_number": {"de": "Rechnungsnummer", "en": "Invoice Number"},
    "form.invoice_number_placeholder": {"de": "z.B. 2026-006", "en": "e.g. 2026-006"},
    "form.invoice_date": {"de": "Rechnungsdatum", "en": "Invoice Date"},
    "form.due_date": {"de": "Fälligkeitsdatum", "en": "Due Date"},
    "form.service_description": {"de": "Leistungsbeschreibung", "en": "Service Description"},
    "form.service_description_placeholder": {"de": "z.B. Backend-Entwicklung API Integration - März 2026", "en": "e.g. Backend development API integration - March 2026"},
    "form.create_invoice": {"de": "Rechnung erstellen", "en": "Create Invoice"},

    # VAT Rate Labels (Extended)
    "vat.zero_exempt": {"de": "0% (Steuerfrei)", "en": "0% (Tax Exempt)"},
    "vat.zero_small_business": {"de": "0% (Steuerfrei/Kleinunternehmer)", "en": "0% (Tax Exempt/Small Business)"},
    "vat.incl": {"de": "inkl.", "en": "incl."},

    # ==========================================================================
    # Taxes Page
    # ==========================================================================
    "tax.page_title": {"de": "Steuern", "en": "Taxes"},
    "tax.tax_office": {"de": "Finanzamt", "en": "Tax Office"},
    "tax.tax_overview": {"de": "Steuerübersicht", "en": "Tax Overview"},
    "tax.as_of": {"de": "Stand", "en": "As of"},
    "tax.estimated_profit": {"de": "Geschätzter Gewinn", "en": "Estimated Profit"},
    "tax.revenue_minus_expenses": {"de": "Einnahmen - Ausgaben", "en": "Revenue - Expenses"},
    "tax.effective_rate_label": {"de": "effektiver Satz", "en": "effective rate"},
    "tax.vat_liability": {"de": "USt.-Zahllast", "en": "VAT Liability"},
    "tax.vat_minus_input": {"de": "USt. - Vorsteuer", "en": "VAT - Input VAT"},
    "tax.next_deadline": {"de": "Nächste Frist", "en": "Next Deadline"},
    "tax.today": {"de": "Heute!", "en": "Today!"},
    "tax.tomorrow": {"de": "Morgen", "en": "Tomorrow"},
    "tax.in_days": {"de": "In", "en": "In"},
    "tax.no_deadlines": {"de": "Keine Fristen", "en": "No Deadlines"},
    "tax.days_overdue": {"de": "Tage überfällig", "en": "days overdue"},
    "tax.in_x_days": {"de": "in", "en": "in"},
    "tax.days": {"de": "Tagen", "en": "days"},
    "tax.estimated_amount": {"de": "Geschätzter Betrag:", "en": "Estimated amount:"},
    "tax.prepayments": {"de": "Vorauszahlungen", "en": "Prepayments"},
    "tax.vat_advance_return": {"de": "USt-Voranmeldung", "en": "VAT Advance Return"},
    "tax.current_period": {"de": "Aktuelle Periode", "en": "Current Period"},
    "tax.in_progress": {"de": "In Bearbeitung", "en": "In Progress"},
    "tax.vat_collected": {"de": "USt. gesammelt", "en": "VAT collected"},
    "tax.vorsteuer": {"de": "Vorsteuer", "en": "Input VAT"},
    "tax.zahllast": {"de": "Zahllast", "en": "Tax Liability"},
    "tax.eur_preview": {"de": "EÜR Vorschau", "en": "P&L Preview"},
    "tax.business_income": {"de": "Betriebseinnahmen", "en": "Business Income"},
    "tax.business_expenses": {"de": "Betriebsausgaben", "en": "Business Expenses"},
    "tax.profit": {"de": "Gewinn", "en": "Profit"},
    "tax.urgent": {"de": "Dringend", "en": "Urgent"},

    # Quarterly Table
    "quarterly.quarter": {"de": "Quartal", "en": "Quarter"},
    "quarterly.due": {"de": "Fällig", "en": "Due"},
    "quarterly.amount": {"de": "Betrag", "en": "Amount"},
    "quarterly.status": {"de": "Status", "en": "Status"},
    "quarterly.paid": {"de": "Bezahlt", "en": "Paid"},
    "quarterly.pending": {"de": "Ausstehend", "en": "Pending"},
    "quarterly.overdue": {"de": "Überfällig", "en": "Overdue"},
    "quarterly.due_soon": {"de": "Bald fällig", "en": "Due Soon"},
    "quarterly.click_to_toggle": {"de": "Klicken zum Umschalten", "en": "Click to toggle"},
    "quarterly.total_prepayments": {"de": "Gesamte Vorauszahlungen", "en": "Total Prepayments"},
    "quarterly.total": {"de": "Gesamt", "en": "Total"},

    # Deadline Status Badges
    "deadline.click_to_toggle": {"de": "Klicken zum Umschalten", "en": "Click to toggle"},
    "deadline.done": {"de": "Erledigt", "en": "Done"},
    "deadline.completed": {"de": "Erledigt", "en": "Completed"},
    "deadline.overdue": {"de": "Überfällig", "en": "Overdue"},
    "deadline.urgent": {"de": "Dringend", "en": "Urgent"},
    "deadline.due_soon": {"de": "Bald fällig", "en": "Due Soon"},
    "deadline.pending": {"de": "Ausstehend", "en": "Pending"},
    "deadline.no_deadlines": {"de": "Keine anstehenden Fristen", "en": "No upcoming deadlines"},
    "tax.zsm": {"de": "ZSM", "en": "EC Sales"},
    "tax.annual_return_summary": {"de": "Steuererklärung", "en": "Tax Return"},
    "tax.estimated_est": {"de": "Geschätzte ESt", "en": "Estimated Income Tax"},
    "tax.prepayments_paid": {"de": "Vorauszahlungen bezahlt", "en": "Prepayments Made"},
    "tax.remaining_tax_due": {"de": "Noch zu zahlen", "en": "Remaining Due"},
    "tax.due_with_return": {"de": "Fällig mit Steuererklärung", "en": "Due with tax return"},
    "tax.prepayments_sufficient": {"de": "Vorauszahlungen decken geschätzte Steuer", "en": "Prepayments cover estimated tax"},
    "tax.annual_return": {"de": "Steuererklärung", "en": "Tax Return"},
    "tax.breakdown": {"de": "Aufschlüsselung", "en": "Breakdown"},
    "tax.burden": {"de": "Steuerlast", "en": "Tax Burden"},
    "tax.collected": {"de": "gesammelt", "en": "collected"},
    "tax.covered": {"de": "gedeckt", "en": "covered"},
    "tax.eff": {"de": "eff.", "en": "eff."},
    "tax.eff_rate": {"de": "Eff. Satz", "en": "Eff. Rate"},
    "tax.est": {"de": "Gesch.", "en": "Est."},
    "tax.expenses": {"de": "Ausgaben", "en": "Expenses"},
    "tax.income": {"de": "Einnahmen", "en": "Income"},
    "tax.margin": {"de": "Marge", "en": "Margin"},
    "tax.prepaid": {"de": "Vorauszahlungen", "en": "Prepaid"},
    "tax.remaining": {"de": "Verbleibend", "en": "Remaining"},
    "tax.remaining_due": {"de": "Noch fällig", "en": "Remaining Due"},
    "tax.revenue": {"de": "Einnahmen", "en": "Revenue"},
    "tax.soli": {"de": "Soli", "en": "Soli"},
    "tax.taxable_income": {"de": "Zu verst. Einkommen", "en": "Taxable Income"},
    "tax.total_prepayments": {"de": "Vorauszahlungen gesamt", "en": "Total Prepayments"},
    "tax.vat_advance": {"de": "USt-Voranmeldung", "en": "VAT Advance"},
    # Tax Optimization Dashboard Widgets
    "tax.afa": {"de": "AfA", "en": "Depreciation"},
    "tax.travel": {"de": "Reisekosten", "en": "Travel"},
    "tax.gifts": {"de": "Geschenke", "en": "Gifts"},
    "tax.homeoffice": {"de": "Homeoffice", "en": "Home Office"},
    # Asset Widget
    "asset.active": {"de": "aktiv", "en": "active"},
    "asset.expiring": {"de": "ablaufend", "en": "expiring"},
    # Travel Widget
    "travel.trips": {"de": "Reisen", "en": "trips"},
    "travel.per_diem_short": {"de": "VMA", "en": "per diem"},
    # Gift Widget
    "gift.recipients": {"de": "Empfänger", "en": "recipients"},
    "gift.over_limit": {"de": ">50€", "en": ">€50"},
    "gift.at_risk": {"de": "≈50€", "en": "≈€50"},
    "gift.all_ok": {"de": "OK", "en": "OK"},
    # Home Office Widget
    "homeoffice.room": {"de": "Arbeitszimmer", "en": "Office Room"},
    "homeoffice.days": {"de": "Tage", "en": "days"},

    # ==========================================================================
    # Reports Page
    # ==========================================================================
    "report.page_subtitle": {"de": "Finanzberichte", "en": "Financial Reports"},
    "report.page_title": {"de": "Berichte & Exporte", "en": "Reports & Exports"},
    "report.period_month": {"de": "Monat", "en": "Month"},
    "report.period_quarter": {"de": "Quartal", "en": "Quarter"},
    "report.period_year": {"de": "Jahr", "en": "Year"},
    "report.ust_voranmeldung": {"de": "USt-Voranmeldung", "en": "VAT Return"},
    "report.ust_voranmeldung_desc": {"de": "Umsatzsteuer-Voranmeldung für das Finanzamt. Zusammenfassung der USt. und Vorsteuer.", "en": "VAT return for the tax office. Summary of VAT and input VAT."},
    "report.monthly": {"de": "Monatlich", "en": "Monthly"},
    "report.quarterly": {"de": "Quartalsweise", "en": "Quarterly"},
    "report.yearly": {"de": "Jährlich", "en": "Yearly"},
    "report.preview": {"de": "Vorschau", "en": "Preview"},
    "report.zsm": {"de": "Zusammenfassende Meldung", "en": "EC Sales List"},
    "report.zsm_desc": {"de": "EU-weite innergemeinschaftliche Lieferungen und Leistungen an EU-Kunden.", "en": "EU-wide intra-community supplies and services to EU customers."},
    "report.eu_reverse_charge": {"de": "EU-Reverse-Charge Umsatz", "en": "EU Reverse Charge Revenue"},
    "report.eu_clients": {"de": "Anzahl EU-Kunden", "en": "Number of EU Clients"},
    "report.eur": {"de": "Einnahmen-Überschuss-Rechnung", "en": "Income Statement"},
    "report.eur_desc": {"de": "EÜR für die Einkommensteuererklärung. Betriebseinnahmen und -ausgaben nach Kategorien.", "en": "P&L for income tax return. Business income and expenses by category."},
    "report.income": {"de": "Einnahmen", "en": "Income"},
    "report.expenses": {"de": "Ausgaben", "en": "Expenses"},
    "report.annual_overview_desc": {"de": "Komplette Finanzübersicht des Jahres mit Steuerlast und Vergleich zum Vorjahr.", "en": "Complete annual financial overview with tax burden and year-over-year comparison."},
    "report.total_revenue": {"de": "Gesamtumsatz", "en": "Total Revenue"},
    "report.estimated_tax": {"de": "Geschätzte Steuer", "en": "Estimated Tax"},
    "report.net_remaining": {"de": "Netto verbleibend", "en": "Net Remaining"},
    "report.report_preview": {"de": "Berichtvorschau", "en": "Report Preview"},
    "report.pdf_export": {"de": "PDF Export", "en": "PDF Export"},
    "report.csv_export": {"de": "CSV Export", "en": "CSV Export"},
    "report.select_report": {"de": "Bericht auswählen", "en": "Select Report"},
    "report.select_report_desc": {"de": "Klicken Sie auf \"Vorschau\" bei einem der Berichte oben, um eine Vorschau anzuzeigen.", "en": "Click \"Preview\" on one of the reports above to display a preview."},
    "report.recent_exports": {"de": "Letzte Exporte", "en": "Recent Exports"},
    "report.report_name": {"de": "Bericht", "en": "Report"},
    "report.period": {"de": "Zeitraum", "en": "Period"},
    "report.created": {"de": "Erstellt", "en": "Created"},
    "report.format": {"de": "Format", "en": "Format"},
    "report.action": {"de": "Aktion", "en": "Action"},
    "report.breakdown": {"de": "Aufschlüsselung", "en": "Breakdown"},
    "report.clients": {"de": "Kunden", "en": "Clients"},
    "report.deadline_note": {"de": "Abgabefrist: 10. des Folgemonats (mit Dauerfristverlängerung)", "en": "Deadline: 10th of following month (with extension)"},
    "report.no_exports": {"de": "Noch keine Exporte", "en": "No exports yet"},
    "report.view_all": {"de": "Alle →", "en": "View all →"},
    "report.annual_overview": {"de": "Jahresübersicht", "en": "Annual Overview"},

    # USt-Voranmeldung breakdown
    "report.ust_standard_19": {"de": "Lieferungen und Leistungen (19%)", "en": "Supplies and services (19%)"},
    "report.ust_reduced_7": {"de": "Lieferungen ermäßigt (7%)", "en": "Supplies reduced rate (7%)"},
    "report.reverse_charge": {"de": "Innergemeinschaftliche Lieferungen", "en": "Intra-community supplies"},
    "report.deductible_vorsteuer": {"de": "Abziehbare Vorsteuerbeträge", "en": "Deductible input VAT"},
    "report.remaining_ust": {"de": "Verbleibende USt-Vorauszahlung", "en": "Remaining VAT advance payment"},
    "report.nullmeldung_note": {"de": "Nullmeldung: Nur steuerfreie Umsätze", "en": "Nil return: Only tax-exempt sales"},

    # ZSM (Zusammenfassende Meldung)
    "report.zsm_vat_id": {"de": "USt-IdNr.", "en": "VAT ID"},
    "report.zsm_country": {"de": "Land", "en": "Country"},
    "report.zsm_amount": {"de": "Betrag", "en": "Amount"},
    "report.zsm_no_entries": {"de": "Keine EU-Reverse-Charge-Umsätze im Zeitraum", "en": "No EU reverse charge sales in period"},
    "report.zsm_total": {"de": "Gesamtsumme EU-Umsätze", "en": "Total EU sales"},
    "report.zsm_deadline": {"de": "Abgabefrist: 25. des Folgemonats nach Quartalsende", "en": "Deadline: 25th of month following quarter end"},
    "report.no_vat_id": {"de": "Keine USt-IdNr.", "en": "No VAT ID"},

    # EÜR (Einnahmen-Überschuss-Rechnung)
    "report.eur_betriebseinnahmen": {"de": "Betriebseinnahmen", "en": "Business Income"},
    "report.eur_domestic": {"de": "Umsatzerlöse (19% USt.)", "en": "Revenue (19% VAT)"},
    "report.eur_reduced": {"de": "Umsatzerlöse (7% USt.)", "en": "Revenue (7% VAT)"},
    "report.eur_eu": {"de": "Erlöse EU/Drittland (0%)", "en": "Revenue EU/Third Country (0%)"},
    "report.eur_sum_income": {"de": "Summe Betriebseinnahmen", "en": "Total Business Income"},
    "report.eur_betriebsausgaben": {"de": "Betriebsausgaben", "en": "Business Expenses"},
    "report.eur_sum_expenses": {"de": "Summe Betriebsausgaben", "en": "Total Business Expenses"},
    "report.eur_gewinn": {"de": "Gewinn", "en": "Profit"},
    "report.eur_verlust": {"de": "Verlust", "en": "Loss"},
    "report.eur_vorsteuer_total": {"de": "Vorsteuer aus Betriebsausgaben", "en": "Input VAT from expenses"},
    "report.eur_note": {"de": "Anlage EÜR für die Einkommensteuererklärung (§ 4 Abs. 3 EStG)", "en": "Schedule EÜR for income tax return (§ 4 Abs. 3 EStG)"},
    "report.no_expenses": {"de": "Keine Ausgaben im Zeitraum", "en": "No expenses in period"},

    # Annual Overview (Jahresübersicht)
    "report.annual_total_revenue": {"de": "Gesamtumsatz", "en": "Total Revenue"},
    "report.annual_tax_burden": {"de": "Steuerbelastung", "en": "Tax Burden"},
    "report.annual_net_remaining": {"de": "Netto verbleibend", "en": "Net Remaining"},
    "report.annual_effective_rate": {"de": "effektiv", "en": "effective"},
    "report.annual_after_tax": {"de": "Nach Steuern", "en": "After Tax"},
    "report.annual_monthly_chart": {"de": "Monatliche Entwicklung", "en": "Monthly Development"},
    "report.vs_prev_year": {"de": "ggü. Vorjahr", "en": "vs. prior year"},
    "report.expense_change": {"de": "Ausgabenentwicklung ggü. Vorjahr", "en": "Expense change vs. prior year"},

    # Month names for reports
    "report.january": {"de": "Januar", "en": "January"},
    "report.february": {"de": "Februar", "en": "February"},
    "report.march": {"de": "März", "en": "March"},
    "report.april": {"de": "April", "en": "April"},
    "report.may": {"de": "Mai", "en": "May"},
    "report.june": {"de": "Juni", "en": "June"},
    "report.july": {"de": "Juli", "en": "July"},
    "report.august": {"de": "August", "en": "August"},
    "report.september": {"de": "September", "en": "September"},
    "report.october": {"de": "Oktober", "en": "October"},
    "report.november": {"de": "November", "en": "November"},
    "report.december": {"de": "Dezember", "en": "December"},

    # Invoice Preview Modal
    "modal.invoice_preview": {"de": "Rechnungsvorschau", "en": "Invoice Preview"},
    "modal.select_template": {"de": "Vorlage wählen", "en": "Select Template"},
    "modal.print_pdf": {"de": "Drucken / PDF", "en": "Print / PDF"},
    "modal.close": {"de": "Schließen", "en": "Close"},
    "modal.loading_preview": {"de": "Vorschau wird geladen...", "en": "Loading preview..."},

    # ==========================================================================
    # Clients Page
    # ==========================================================================
    "nav.clients": {"de": "Kunden", "en": "Clients"},
    "client.title": {"de": "Kunden", "en": "Clients"},
    "client.management": {"de": "Kundenverwaltung", "en": "Client Management"},
    "client.new": {"de": "Neuer Kunde", "en": "New Client"},
    "client.total": {"de": "Kunden gesamt", "en": "Total Clients"},
    "client.at_risk": {"de": "Kunden mit Risiko", "en": "Clients at Risk"},
    "client.concentration": {"de": "Hohe Konzentration", "en": "High Concentration"},
    "client.diversified": {"de": "Gut diversifiziert", "en": "Well Diversified"},
    "client.total_invoiced": {"de": "Fakturiert gesamt", "en": "Total Invoiced"},
    "client.net_amount": {"de": "Nettobetrag", "en": "Net Amount"},
    "client.outstanding": {"de": "Ausstehend", "en": "Outstanding"},
    "client.open_payments": {"de": "Offene Zahlungen", "en": "Open Payments"},
    "client.top_clients": {"de": "Top Kunden", "en": "Top Clients"},
    "client.income_distribution": {"de": "Einkommensverteilung", "en": "Income Distribution"},
    "client.all_clients": {"de": "Alle Kunden", "en": "All Clients"},
    "client.search": {"de": "Kunden suchen...", "en": "Search clients..."},
    "client.company": {"de": "Firma", "en": "Company"},
    "client.contact": {"de": "Kontakt", "en": "Contact"},
    "client.share": {"de": "Anteil", "en": "Share"},
    "client.open": {"de": "Offen", "en": "Open"},
    "client.active": {"de": "aktive Kunden", "en": "active clients"},
    "client.no_clients": {"de": "Noch keine Kunden vorhanden", "en": "No clients yet"},
    "client.create_first": {
        "de": "Erstellen Sie Ihren ersten Kunden, um loszulegen.",
        "en": "Create your first client to get started.",
    },
    "client.income_share": {"de": "Einkommensanteil", "en": "Income Share"},
    "client.threshold": {"de": "Grenzwert", "en": "Threshold"},
    "client.of_income": {"de": "des Einkommens", "en": "of income"},

    # Client Form
    "client.new_client": {"de": "Neuer Kunde", "en": "New Client"},
    "client.edit": {"de": "Kunde bearbeiten", "en": "Edit Client"},
    "client.name": {"de": "Name", "en": "Name"},
    "client.name_placeholder": {"de": "z.B. SAP SE", "en": "e.g. SAP SE"},
    "client.street": {"de": "Straße", "en": "Street"},
    "client.street_placeholder": {"de": "Musterstraße 123", "en": "123 Main Street"},
    "client.zip_code": {"de": "PLZ", "en": "ZIP Code"},
    "client.city": {"de": "Stadt", "en": "City"},
    "client.country": {"de": "Land", "en": "Country"},
    "client.vat_id": {"de": "USt-IdNr.", "en": "VAT ID"},
    "client.email": {"de": "E-Mail", "en": "Email"},
    "client.phone": {"de": "Telefon", "en": "Phone"},
    "client.address_details": {"de": "Adresszusatz", "en": "Address Details"},
    "client.save": {"de": "Speichern", "en": "Save"},
    "client.created_success": {"de": "Kunde erfolgreich angelegt", "en": "Client created successfully"},
    "client.select_from_dropdown": {
        "de": "Bitte wählen Sie den Kunden aus dem Dropdown aus.",
        "en": "Please select the client from the dropdown.",
    },
    "client.not_found": {"de": "Kunde nicht gefunden", "en": "Client not found"},
    "client.actions": {"de": "Aktionen", "en": "Actions"},
    "client.address": {"de": "Adresse", "en": "Address"},
    "client.no_results": {"de": "Keine Kunden gefunden", "en": "No clients found"},
    "client.notes": {"de": "Notizen", "en": "Notes"},
    "client.tax_info": {"de": "Steuerinfo", "en": "Tax Info"},

    # Country Names
    "country.DE": {"de": "Deutschland", "en": "Germany"},
    "country.AT": {"de": "Österreich", "en": "Austria"},
    "country.CH": {"de": "Schweiz", "en": "Switzerland"},
    "country.US": {"de": "USA", "en": "USA"},
    "country.GB": {"de": "Großbritannien", "en": "United Kingdom"},
    "country.FR": {"de": "Frankreich", "en": "France"},
    "country.NL": {"de": "Niederlande", "en": "Netherlands"},
    "country.SE": {"de": "Schweden", "en": "Sweden"},
    "country.IT": {"de": "Italien", "en": "Italy"},
    "country.ES": {"de": "Spanien", "en": "Spain"},

    # Scheinselbständigkeit Warning
    "client.scheinselbstaendig_warning_title": {
        "de": "Scheinselbständigkeit-Risiko erkannt",
        "en": "False Self-Employment Risk Detected",
    },
    "client.scheinselbstaendig_warning_text": {
        "de": (
            "Mehr als 83% Ihres Einkommens stammt von einem einzelnen Kunden. "
            "Dies kann nach deutschem Arbeitsrecht zu einer Prüfung durch die "
            "Finanzbehörden führen."
        ),
        "en": (
            "More than 83% of your income comes from a single client. "
            "This may trigger tax authority scrutiny under German employment law."
        ),
    },
    "client.scheinselbstaendig_warning_short": {
        "de": ">83% Einkommen von einem Kunden (§ 7 SGB IV)",
        "en": ">83% income from one client (§ 7 SGB IV)",
    },
    "client.learn_more": {"de": "Mehr erfahren", "en": "Learn More"},
    "client.dismiss": {"de": "Schließen", "en": "Dismiss"},

    # Common actions
    "common.actions": {"de": "Aktionen", "en": "Actions"},
    "common.view": {"de": "Ansehen", "en": "View"},
    "common.edit": {"de": "Bearbeiten", "en": "Edit"},

    # ==========================================================================
    # Error Messages
    # ==========================================================================
    "error.required_field": {"de": "Dieses Feld ist erforderlich", "en": "This field is required"},
    "error.invalid_amount": {"de": "Ungültiger Betrag", "en": "Invalid amount"},
    "error.invalid_date": {"de": "Ungültiges Datum", "en": "Invalid date"},
    "error.save_failed": {"de": "Speichern fehlgeschlagen", "en": "Save failed"},

    # ==========================================================================
    # Success Messages
    # ==========================================================================
    "success.saved": {"de": "Erfolgreich gespeichert", "en": "Successfully saved"},
    "success.deleted": {"de": "Erfolgreich gelöscht", "en": "Successfully deleted"},
    "success.updated": {"de": "Erfolgreich aktualisiert", "en": "Successfully updated"},

    # ==========================================================================
    # Travel Expenses (Reisekosten)
    # ==========================================================================
    "travel.title": {"de": "Reisekosten", "en": "Travel Expenses"},
    "travel.new_trip": {"de": "Neue Dienstreise erfassen", "en": "Record New Business Trip"},
    "travel.destination": {"de": "Zielort", "en": "Destination"},
    "travel.destination_placeholder": {"de": "z.B. München, Berlin", "en": "e.g. Munich, Berlin"},
    "travel.purpose": {"de": "Reisezweck", "en": "Trip Purpose"},
    "travel.purpose_placeholder": {"de": "z.B. Kundentermin, Konferenz", "en": "e.g. Client meeting, Conference"},
    "travel.country": {"de": "Land", "en": "Country"},
    "travel.departure": {"de": "Abfahrt", "en": "Departure"},
    "travel.return": {"de": "Rückkehr", "en": "Return"},
    "travel.hours": {"de": "Abwesenheit (Std)", "en": "Absence (Hours)"},
    "travel.km": {"de": "Kilometer", "en": "Kilometers"},
    "travel.overnight": {"de": "Mit Übernachtung", "en": "With Overnight Stay"},
    "travel.travel_day": {"de": "An-/Abreisetag", "en": "Travel Day"},
    "travel.meals_provided": {"de": "Bereitgestellte Mahlzeiten (für Kürzung)", "en": "Meals Provided (for Reduction)"},
    "travel.breakfast": {"de": "Frühstück", "en": "Breakfast"},
    "travel.lunch": {"de": "Mittagessen", "en": "Lunch"},
    "travel.dinner": {"de": "Abendessen", "en": "Dinner"},
    "travel.per_diem": {"de": "Pauschale", "en": "Per Diem"},
    "travel.per_diem_preview": {"de": "Verpflegungsmehraufwand", "en": "Per Diem Allowance"},
    "travel.km_preview": {"de": "Fahrtkosten", "en": "Travel Costs"},
    "travel.km_deduction": {"de": "Fahrtkosten", "en": "Travel Costs"},
    "travel.meal_reduction": {"de": "Kürzung", "en": "Reduction"},
    "travel.total": {"de": "Gesamt", "en": "Total"},
    "travel.time": {"de": "Zeit", "en": "Time"},
    "travel.save": {"de": "Reise speichern", "en": "Save Trip"},
    "travel.confirm_delete": {"de": "Reise wirklich löschen?", "en": "Really delete trip?"},
    "travel.no_trips": {"de": "Keine Reisen erfasst", "en": "No trips recorded"},
    "travel.not_found": {"de": "Reise nicht gefunden", "en": "Trip not found"},
    "travel.per_diem_total": {"de": "Verpflegungspauschalen", "en": "Per Diem Total"},
    "travel.km_total": {"de": "Fahrtkosten", "en": "Travel Costs Total"},
    "travel.total_deduction": {"de": "Gesamt Abzug", "en": "Total Deduction"},
    "travel.monthly_breakdown": {"de": "Monatliche Übersicht", "en": "Monthly Breakdown"},
    "travel.trips": {"de": "Reisen", "en": "Trips"},

    # ==========================================================================
    # Gift Expenses (Geschenke)
    # ==========================================================================
    "gift.title": {"de": "Geschenke", "en": "Gifts"},
    "gift.new_gift": {"de": "Neues Geschenk erfassen", "en": "Record New Gift"},
    "gift.recipient": {"de": "Empfänger", "en": "Recipient"},
    "gift.recipient_placeholder": {"de": "z.B. Max Mustermann", "en": "e.g. John Doe"},
    "gift.company": {"de": "Firma (optional)", "en": "Company (optional)"},
    "gift.company_placeholder": {"de": "z.B. Musterfirma GmbH", "en": "e.g. Example Inc."},
    "gift.description": {"de": "Beschreibung", "en": "Description"},
    "gift.description_placeholder": {"de": "z.B. Weihnachtsgeschenk, Weinflasche", "en": "e.g. Christmas gift, Wine bottle"},
    "gift.occasion": {"de": "Anlass (optional)", "en": "Occasion (optional)"},
    "gift.occasion_placeholder": {"de": "z.B. Geburtstag, Projektabschluss", "en": "e.g. Birthday, Project completion"},
    "gift.amount": {"de": "Betrag", "en": "Amount"},
    "gift.amount_net": {"de": "Nettobetrag (€)", "en": "Net Amount (€)"},
    "gift.cumulative": {"de": "Kumuliert", "en": "Cumulative"},
    "gift.status": {"de": "Status", "en": "Status"},
    "gift.deductible": {"de": "Abzugsfähig", "en": "Deductible"},
    "gift.not_deductible": {"de": "Nicht abzugsfähig", "en": "Not Deductible"},
    "gift.limit_info": {"de": "Geschenkegrenze", "en": "Gift Limit"},
    "gift.limit_explanation": {"de": "Pro Empfänger und Jahr. Bei Überschreitung ist der gesamte Betrag nicht abzugsfähig.", "en": "Per recipient per year. If exceeded, the entire amount is not deductible."},
    "gift.save": {"de": "Geschenk speichern", "en": "Save Gift"},
    "gift.confirm_delete": {"de": "Geschenk wirklich löschen?", "en": "Really delete gift?"},
    "gift.no_gifts": {"de": "Keine Geschenke erfasst", "en": "No gifts recorded"},
    "gift.not_found": {"de": "Geschenk nicht gefunden", "en": "Gift not found"},
    "gift.approaching_limit": {"de": "Achtung: Geschenkegrenze für diesen Empfänger erreicht oder überschritten!", "en": "Warning: Gift limit for this recipient reached or exceeded!"},
    "gift.year": {"de": "Jahr", "en": "Year"},
    "gift.remaining": {"de": "Verbleibend", "en": "Remaining"},
    "gift.over_limit_warning": {"de": "Grenze überschritten! Alle Geschenke an diesen Empfänger sind nicht abzugsfähig.", "en": "Limit exceeded! All gifts to this recipient are not deductible."},
    "gift.near_limit_warning": {"de": "Achtung: Grenze fast erreicht!", "en": "Warning: Limit almost reached!"},
    "gift.total": {"de": "Gesamt", "en": "Total"},
    "gift.non_deductible": {"de": "Nicht abzugsfähig", "en": "Not Deductible"},
    "gift.at_risk_title": {"de": "Empfänger nahe Geschenkegrenze", "en": "Recipients Near Gift Limit"},
    "gift.no_at_risk": {"de": "Keine Empfänger nahe der Grenze", "en": "No recipients near the limit"},
    "gift.over_limit": {"de": "Über Limit", "en": "Over Limit"},
    "gift.within_limit": {"de": "OK", "en": "OK"},

    # ==========================================================================
    # Business Meals (Bewirtung)
    # ==========================================================================
    "bewirtung.title": {"de": "Bewirtungskosten", "en": "Business Meals"},
    "bewirtung.new_meal": {"de": "Neue Bewirtung erfassen", "en": "Record New Business Meal"},
    "bewirtung.restaurant": {"de": "Restaurant", "en": "Restaurant"},
    "bewirtung.restaurant_placeholder": {"de": "z.B. Restaurant Zur Post", "en": "e.g. The Local Bistro"},
    "bewirtung.purpose": {"de": "Geschäftlicher Anlass", "en": "Business Purpose"},
    "bewirtung.purpose_placeholder": {"de": "z.B. Projektbesprechung mit Kunde XY bzgl. Webseitenredesign", "en": "e.g. Project discussion with client XY regarding website redesign"},
    "bewirtung.purpose_hint": {"de": "Min. 10 Zeichen. Muss konkret und nachvollziehbar sein.", "en": "Min. 10 characters. Must be specific and verifiable."},
    "bewirtung.attendees": {"de": "Teilnehmer", "en": "Attendees"},
    "bewirtung.attendees_placeholder": {"de": "z.B. Max Mustermann, Erika Muster, Sie selbst", "en": "e.g. John Doe, Jane Smith, yourself"},
    "bewirtung.count": {"de": "Anzahl Personen", "en": "Number of Persons"},
    "bewirtung.amount": {"de": "Gesamtbetrag (€)", "en": "Total Amount (€)"},
    "bewirtung.tip": {"de": "Trinkgeld (€)", "en": "Tip (€)"},
    "bewirtung.internal": {"de": "Betriebsveranstaltung", "en": "Internal Event"},
    "bewirtung.external": {"de": "Extern", "en": "External"},
    "bewirtung.type": {"de": "Typ", "en": "Type"},
    "bewirtung.deductible": {"de": "Abzugsfähig", "en": "Deductible"},
    "bewirtung.not_deductible": {"de": "Nicht abzugsfähig", "en": "Not Deductible"},
    "bewirtung.rate": {"de": "Rate", "en": "Rate"},
    "bewirtung.save": {"de": "Bewirtung speichern", "en": "Save Business Meal"},
    "bewirtung.confirm_delete": {"de": "Bewirtung wirklich löschen?", "en": "Really delete business meal?"},
    "bewirtung.no_meals": {"de": "Keine Bewirtungen erfasst", "en": "No business meals recorded"},
    "bewirtung.not_found": {"de": "Bewirtung nicht gefunden", "en": "Business meal not found"},
    "bewirtung.cap_warning": {"de": "Hinweis: €110/Person Grenze für interne Veranstaltungen überschritten", "en": "Note: €110/person limit for internal events exceeded"},
    "bewirtung.internal_rate": {"de": "Interne Veranstaltung: 100% bis max €110/Person", "en": "Internal event: 100% up to €110/person"},
    "bewirtung.external_rate": {"de": "Externe Bewirtung: 70% abzugsfähig", "en": "External meal: 70% deductible"},
    "bewirtung.total_spent": {"de": "Ausgaben Gesamt", "en": "Total Spent"},
    "bewirtung.meal_count": {"de": "Anzahl Bewirtungen", "en": "Number of Meals"},
    "bewirtung.monthly_breakdown": {"de": "Monatliche Übersicht", "en": "Monthly Breakdown"},
    "bewirtung.rate_info": {"de": "Externe Bewirtung: 70% abzugsfähig | Interne Veranstaltung: 100% bis max €110/Person", "en": "External meal: 70% deductible | Internal event: 100% up to €110/person"},

    # ==========================================================================
    # Home Office
    # ==========================================================================
    "homeoffice.title": {"de": "Homeoffice", "en": "Home Office"},
    "homeoffice.date": {"de": "Datum", "en": "Date"},
    "homeoffice.notes": {"de": "Notiz (optional)", "en": "Notes (optional)"},
    "homeoffice.notes_placeholder": {"de": "z.B. Projektarbeit", "en": "e.g. Project work"},
    "homeoffice.add_day": {"de": "Tag erfassen", "en": "Record Day"},
    "homeoffice.progress": {"de": "Jahresfortschritt", "en": "Annual Progress"},
    "homeoffice.days": {"de": "Tage", "en": "Days"},
    "homeoffice.remaining": {"de": "Verbleibend", "en": "Remaining"},
    "homeoffice.confirm_delete": {"de": "Tag wirklich löschen?", "en": "Really delete day?"},
    "homeoffice.limit_reached": {"de": "Achtung: Höchstgrenze von 210 Tagen erreicht!", "en": "Warning: Maximum of 210 days reached!"},
    "homeoffice.annual_deduction": {"de": "Jahresabzug", "en": "Annual Deduction"},
    "homeoffice.weekday": {"de": "Wochentag", "en": "Weekday"},
    "homeoffice.amount": {"de": "Betrag", "en": "Amount"},
    "homeoffice.no_days": {"de": "Keine Homeoffice-Tage erfasst", "en": "No home office days recorded"},
    "homeoffice.settings_title": {"de": "Homeoffice-Einstellungen", "en": "Home Office Settings"},
    "homeoffice.method": {"de": "Abzugsmethode", "en": "Deduction Method"},
    "homeoffice.pauschale": {"de": "Homeoffice-Pauschale", "en": "Home Office Flat Rate"},
    "homeoffice.pauschale_desc": {"de": "Für Arbeit von zuhause ohne separates Arbeitszimmer", "en": "For working from home without a separate office room"},
    "homeoffice.arbeitszimmer_flat": {"de": "Arbeitszimmer (Pauschale €1.260)", "en": "Home Office Room (€1,260 Flat Rate)"},
    "homeoffice.arbeitszimmer_flat_desc": {"de": "Separates Arbeitszimmer, Mittelpunkt der Tätigkeit - Jahrespauschale", "en": "Separate office room, center of activity - annual flat rate"},
    "homeoffice.arbeitszimmer_actual": {"de": "Arbeitszimmer (tatsächliche Kosten)", "en": "Home Office Room (Actual Costs)"},
    "homeoffice.arbeitszimmer_actual_desc": {"de": "Separates Arbeitszimmer, Mittelpunkt der Tätigkeit - anteilige Kosten", "en": "Separate office room, center of activity - pro-rata costs"},
    "homeoffice.room_details": {"de": "Raumangaben", "en": "Room Details"},
    "homeoffice.room_sqm": {"de": "Arbeitszimmer (m²)", "en": "Office Room (sqm)"},
    "homeoffice.total_sqm": {"de": "Wohnung gesamt (m²)", "en": "Total Home (sqm)"},
    "homeoffice.monthly_costs": {"de": "Monatl. Kosten (€)", "en": "Monthly Costs (€)"},
    "homeoffice.costs_hint": {"de": "Miete + Nebenkosten", "en": "Rent + Utilities"},
    "homeoffice.save_settings": {"de": "Einstellungen speichern", "en": "Save Settings"},
    "homeoffice.edit_settings": {"de": "Einstellungen", "en": "Settings"},
    "homeoffice.monthly_breakdown": {"de": "Monatliche Übersicht", "en": "Monthly Breakdown"},
    "homeoffice.calendar_hint": {"de": "Klicken Sie auf einen Tag, um ihn als Homeoffice-Tag zu erfassen", "en": "Click on a day to record it as a home office day"},

    # ==========================================================================
    # Assets (Anlagevermögen)
    # ==========================================================================
    "asset.title": {"de": "Anlagevermögen", "en": "Fixed Assets"},
    "asset.new_asset": {"de": "Neues Anlagegut erfassen", "en": "Record New Asset"},
    "asset.name": {"de": "Bezeichnung", "en": "Name"},
    "asset.name_placeholder": {"de": "z.B. MacBook Pro, Bürostuhl", "en": "e.g. MacBook Pro, Office Chair"},
    "asset.purchase_date": {"de": "Anschaffungsdatum", "en": "Purchase Date"},
    "asset.acquisition_cost": {"de": "Anschaffungskosten (€)", "en": "Acquisition Cost (€)"},
    "asset.category": {"de": "Kategorie", "en": "Category"},
    "asset.useful_life": {"de": "Nutzungsdauer (Jahre)", "en": "Useful Life (Years)"},
    "asset.depreciation_method": {"de": "AfA-Methode", "en": "Depreciation Method"},
    "asset.book_value": {"de": "Buchwert", "en": "Book Value"},
    "asset.annual_depreciation": {"de": "Jahres-AfA", "en": "Annual Depreciation"},
    "asset.private_use": {"de": "Privatanteil (%)", "en": "Private Use (%)"},
    "asset.save": {"de": "Anlagegut speichern", "en": "Save Asset"},
    "asset.confirm_delete": {"de": "Anlagegut wirklich löschen?", "en": "Really delete asset?"},
    "asset.no_assets": {"de": "Keine Anlagegüter erfasst", "en": "No assets recorded"},
    "asset.not_found": {"de": "Anlagegut nicht gefunden", "en": "Asset not found"},
    "asset.depreciation_schedule": {"de": "AfA-Plan", "en": "Depreciation Schedule"},
    "asset.total_depreciation": {"de": "Gesamt-AfA", "en": "Total Depreciation"},
    "asset.expiring_soon": {"de": "Bald abgeschrieben", "en": "Expiring Soon"},
    "asset.method.gwg": {"de": "GWG (sofort)", "en": "GWG (immediate)"},
    "asset.method.pool": {"de": "Sammelposten (5 Jahre)", "en": "Pool (5 years)"},
    "asset.method.linear": {"de": "Linear", "en": "Linear"},
    "asset.method.digital": {"de": "Digital-AfA (1 Jahr)", "en": "Digital (1 year)"},
    "asset.method.degressive": {"de": "Degressiv", "en": "Declining Balance"},
    "asset.category.computer": {"de": "Computer/IT", "en": "Computer/IT"},
    "asset.category.software": {"de": "Software", "en": "Software"},
    "asset.category.office": {"de": "Büroausstattung", "en": "Office Equipment"},
    "asset.category.furniture": {"de": "Möbel", "en": "Furniture"},
    "asset.category.vehicle": {"de": "Fahrzeug", "en": "Vehicle"},
    "asset.category.machinery": {"de": "Maschinen", "en": "Machinery"},
    "asset.category.other": {"de": "Sonstiges", "en": "Other"},

    # ==========================================================================
    # AI Chat Interface
    # ==========================================================================
    "ai.title": {"de": "KI-Assistent", "en": "AI Assistant"},
    "ai.fiscfox_ai": {"de": "FiscFox KI", "en": "FiscFox AI"},
    "ai.status_ready": {"de": "Bereit", "en": "Ready"},
    "ai.status_thinking": {"de": "Denkt nach...", "en": "Thinking..."},
    "ai.status_error": {"de": "Fehler", "en": "Error"},
    "ai.loading_model": {"de": "Modell wird geladen...", "en": "Loading model..."},
    "ai.loading_model_hint": {
        "de": "Dies kann beim ersten Start einige Sekunden dauern",
        "en": "This may take a few seconds on first start",
    },
    "ai.placeholder": {"de": "Frag mich etwas...", "en": "Ask me something..."},
    "ai.local_processing": {
        "de": "Lokal verarbeitet - Keine Cloud-Verbindung",
        "en": "Processed locally - No cloud connection",
    },
    "ai.connection_error": {
        "de": "Verbindungsfehler. Bitte erneut versuchen.",
        "en": "Connection error. Please try again.",
    },

    # Welcome Message
    "ai.welcome": {
        "de": "Hallo! Ich bin dein FiscFox KI-Assistent. Ich kann dir bei Fragen zu:",
        "en": "Hello! I'm your FiscFox AI assistant. I can help you with:",
    },
    "ai.help_tax": {
        "de": "Deutschem Steuerrecht (EStG, UStG)",
        "en": "German tax law (EStG, UStG)",
    },
    "ai.help_financial": {
        "de": "Deinen Finanzdaten (Umsatz, Ausgaben)",
        "en": "Your financial data (revenue, expenses)",
    },
    "ai.help_afa": {"de": "AfA und Abschreibungen", "en": "Depreciation (AfA)"},
    "ai.ask_me": {"de": "Frag mich einfach!", "en": "Just ask me!"},

    # Intent Types
    "ai.intent.tax_law": {"de": "Steuerrecht", "en": "Tax Law"},
    "ai.intent.financial_query": {"de": "Finanzdaten", "en": "Financial Data"},
    "ai.intent.afa_assist": {"de": "AfA-Hilfe", "en": "Depreciation Help"},
    "ai.intent.expense_categorize": {"de": "Kategorisierung", "en": "Categorization"},
    "ai.intent.invoice_risk": {"de": "Risikoanalyse", "en": "Risk Analysis"},
    "ai.intent.general_chat": {"de": "Allgemein", "en": "General"},

    # Confidence Levels
    "ai.confidence.high": {"de": "Hohe Konfidenz", "en": "High Confidence"},
    "ai.confidence.medium": {"de": "Mittlere Konfidenz", "en": "Medium Confidence"},
    "ai.confidence.low": {"de": "Niedrige Konfidenz", "en": "Low Confidence"},

    # Error Messages
    "ai.error.generic": {"de": "Fehler: {error}", "en": "Error: {error}"},
    "ai.error.sql_validation": {
        "de": "SQL-Validierungsfehler: {error}",
        "en": "SQL validation error: {error}",
    },
    "ai.error.sql_execution": {
        "de": "SQL-Ausführungsfehler: {error}",
        "en": "SQL execution error: {error}",
    },
    "ai.error.afa_calculation": {
        "de": "Fehler bei der AfA-Berechnung: {error}",
        "en": "Depreciation calculation error: {error}",
    },
    "ai.error.sql_generic": {"de": "SQL-Fehler: {error}", "en": "SQL error: {error}"},
    "ai.error.timeout": {
        "de": "Die Anfrage hat zu lange gedauert. Bitte versuche es erneut mit einer einfacheren Frage.",
        "en": "Request timed out. Please try again with a simpler question.",
    },

    # ==========================================================================
    # AfA Suggestions
    # ==========================================================================
    "ai.afa.acquisition_cost": {"de": "Anschaffungskosten", "en": "Acquisition Cost"},
    "ai.afa.method_label": {"de": "Abschreibungsmethode", "en": "Depreciation Method"},
    "ai.afa.useful_life": {"de": "Nutzungsdauer", "en": "Useful Life"},
    "ai.afa.annual_depreciation": {"de": "Jährliche AfA", "en": "Annual Depreciation"},
    "ai.afa.legal_basis": {"de": "Rechtsgrundlage", "en": "Legal Basis"},
    "ai.afa.record_asset": {"de": "Als Anlage erfassen", "en": "Record as Asset"},
    "ai.afa.disclaimer": {
        "de": "Diese Empfehlung ersetzt keine steuerliche Beratung. Bei Unsicherheiten bitte Steuerberater konsultieren.",
        "en": "This recommendation does not replace tax advice. Please consult a tax advisor if in doubt.",
    },

    # AfA Methods (short)
    "ai.afa.method.gwg": {"de": "GWG", "en": "LVA"},
    "ai.afa.method.sofort": {"de": "Sofortabzug", "en": "Immediate"},
    "ai.afa.method.pool": {"de": "Pool", "en": "Pool"},
    "ai.afa.method.digital": {"de": "Digital-AfA", "en": "Digital"},
    "ai.afa.method.linear": {"de": "Linear", "en": "Straight-Line"},
    "ai.afa.method.degressive": {"de": "Degressiv", "en": "Declining"},

    # AfA Methods (full names)
    "ai.afa.method.gwg_full": {
        "de": "Geringwertiges Wirtschaftsgut",
        "en": "Low-Value Asset",
    },
    "ai.afa.method.sofort_full": {"de": "Sofortabzug", "en": "Immediate Deduction"},
    "ai.afa.method.pool_full": {"de": "Sammelposten (Pool)", "en": "Pool Assets"},
    "ai.afa.method.digital_full": {
        "de": "Digitale Wirtschaftsgüter",
        "en": "Digital Assets",
    },
    "ai.afa.method.linear_full": {"de": "Lineare AfA", "en": "Straight-Line Depreciation"},
    "ai.afa.method.degressive_full": {
        "de": "Degressive AfA",
        "en": "Declining Balance Depreciation",
    },

    # AfA Explanations
    "ai.afa.explain.sofort": {
        "de": "Sofortabzug als Betriebsausgabe möglich (< 250 EUR)",
        "en": "Immediate deduction as business expense possible (< EUR 250)",
    },
    "ai.afa.explain.gwg": {
        "de": "Geringwertiges Wirtschaftsgut - Sofortabschreibung im Jahr der Anschaffung",
        "en": "Low-value asset - Immediate write-off in year of acquisition",
    },
    "ai.afa.explain.pool": {
        "de": "Sammelposten-Abschreibung über 5 Jahre (Poolabschreibung)",
        "en": "Pool depreciation over 5 years",
    },
    "ai.afa.explain.linear": {
        "de": "Lineare Abschreibung über {years} Jahre Nutzungsdauer",
        "en": "Straight-line depreciation over {years} years useful life",
    },
    "ai.afa.explain.digital": {
        "de": "Digitale Wirtschaftsgüter - Sofortabschreibung gemäß BMF-Schreiben",
        "en": "Digital assets - Immediate write-off per BMF directive",
    },

    # AfA Time Units
    "ai.afa.immediate": {"de": "Sofort", "en": "Immediate"},
    "ai.afa.year": {"de": "Jahr", "en": "year"},
    "ai.afa.years": {"de": "Jahre", "en": "years"},
    "ai.afa.year_singular": {"de": "1 Jahr", "en": "1 year"},
    "ai.afa.years_plural": {"de": "{n} Jahre", "en": "{n} years"},

    # ==========================================================================
    # SQL Results
    # ==========================================================================
    "ai.sql.row": {"de": "Zeile", "en": "row"},
    "ai.sql.rows": {"de": "Zeilen", "en": "rows"},
    "ai.sql.no_results": {"de": "Keine Ergebnisse gefunden.", "en": "No results found."},
    "ai.sql.show_query": {"de": "SQL-Abfrage anzeigen", "en": "Show SQL query"},

    # ==========================================================================
    # Tax RAG
    # ==========================================================================
    "ai.rag.sources": {"de": "Quellen", "en": "Sources"},
    "ai.rag.disclaimer": {
        "de": "Diese Auskunft ersetzt keine professionelle steuerliche Beratung.",
        "en": "This information does not replace professional tax advice.",
    },
    "ai.rag.no_sources": {
        "de": "Keine relevanten Quellen gefunden. Können Sie die Frage präzisieren?",
        "en": "No relevant sources found. Can you clarify the question?",
    },
    "ai.rag.no_context": {
        "de": "Ich konnte leider keine relevanten Informationen zu dieser Frage finden.",
        "en": "Unfortunately, I couldn't find relevant information for this question.",
    },
    "ai.rag.no_context_reasons": {
        "de": "Dies kann folgende Gründe haben:",
        "en": "This may be because:",
    },
    "ai.rag.no_context_reason1": {
        "de": "Die Frage betrifft einen sehr speziellen Bereich, der nicht in meiner Wissensbasis enthalten ist",
        "en": "The question concerns a very specific area not in my knowledge base",
    },
    "ai.rag.no_context_reason2": {
        "de": "Die Frage ist möglicherweise nicht steuerlich relevant",
        "en": "The question may not be tax-related",
    },
    "ai.rag.recommendations": {
        "de": "Für eine verlässliche Auskunft empfehle ich:",
        "en": "For reliable information, I recommend:",
    },
    "ai.rag.recommend_advisor": {
        "de": "Konsultieren Sie einen Steuerberater",
        "en": "Consult a tax advisor",
    },
    "ai.rag.recommend_law": {
        "de": "Prüfen Sie direkt im Gesetzestext (EStG, UStG, AO)",
        "en": "Check the legal text directly (EStG, UStG, AO)",
    },
    "ai.rag.recommend_office": {
        "de": "Kontaktieren Sie Ihr Finanzamt",
        "en": "Contact your tax office",
    },
    "ai.rag.generation_error": {
        "de": "Fehler bei der Antwortgenerierung: {error}",
        "en": "Error generating answer: {error}",
    },

    # ==========================================================================
    # Health Insurance (Krankenversicherung)
    # ==========================================================================
    "nav.health_insurance": {"de": "Krankenversicherung", "en": "Health Insurance"},

    # Page titles
    "health_insurance.title": {"de": "Krankenversicherung", "en": "Health Insurance"},
    "health_insurance.subtitle": {"de": "Beiträge für Anlage Vorsorgeaufwand", "en": "Contributions for Tax Deduction"},
    "health_insurance.new_payment": {"de": "Neue Zahlung erfassen", "en": "Record New Payment"},

    # Stats cards
    "health_insurance.total_paid": {"de": "Gezahlt", "en": "Paid"},
    "health_insurance.total_paid_desc": {"de": "Gesamte Beiträge in diesem Jahr", "en": "Total contributions this year"},
    "health_insurance.deductible": {"de": "Absetzbar", "en": "Deductible"},
    "health_insurance.deductible_desc": {"de": "Steuerlich absetzbar (§ 10 EStG)", "en": "Tax deductible (§ 10 EStG)"},
    "health_insurance.remaining_limit": {"de": "Verbleibendes Limit", "en": "Remaining Limit"},
    "health_insurance.remaining_limit_desc": {"de": "Für Wahlleistungen (max. 2.800 €)", "en": "For optional services (max. €2,800)"},
    "health_insurance.payment_count": {"de": "Zahlungen", "en": "Payments"},
    "health_insurance.payment_count_desc": {"de": "Erfasste Zahlungen in diesem Jahr", "en": "Recorded payments this year"},

    # Insurance types
    "insurance_type.gkv": {"de": "Gesetzlich (GKV)", "en": "Statutory (GKV)"},
    "insurance_type.pkv": {"de": "Privat (PKV)", "en": "Private (PKV)"},
    "insurance_type.gkv_short": {"de": "GKV", "en": "GKV"},
    "insurance_type.pkv_short": {"de": "PKV", "en": "PKV"},

    # Coverage types
    "coverage.basis_krankenversicherung": {"de": "Basisabsicherung", "en": "Basic Health Coverage"},
    "coverage.pflegepflichtversicherung": {"de": "Pflegepflichtversicherung", "en": "Mandatory Care Insurance"},
    "coverage.wahlleistungen": {"de": "Wahlleistungen", "en": "Optional Services"},
    "coverage.zusatzversicherung": {"de": "Zusatzversicherung", "en": "Supplementary Insurance"},

    # Coverage descriptions
    "coverage.basis_krankenversicherung_desc": {
        "de": "Unbegrenzt absetzbar (§ 10 Abs. 1 Nr. 3a EStG)",
        "en": "Unlimited deduction (§ 10 Abs. 1 Nr. 3a EStG)"
    },
    "coverage.pflegepflichtversicherung_desc": {
        "de": "Unbegrenzt absetzbar (§ 10 Abs. 1 Nr. 3a EStG)",
        "en": "Unlimited deduction (§ 10 Abs. 1 Nr. 3a EStG)"
    },
    "coverage.wahlleistungen_desc": {
        "de": "Begrenzt auf 2.800 €/Jahr (§ 10 Abs. 4 EStG)",
        "en": "Limited to €2,800/year (§ 10 Abs. 4 EStG)"
    },
    "coverage.zusatzversicherung_desc": {
        "de": "Begrenzt auf 2.800 €/Jahr (§ 10 Abs. 4 EStG)",
        "en": "Limited to €2,800/year (§ 10 Abs. 4 EStG)"
    },

    # Form labels
    "health_insurance.provider": {"de": "Versicherung", "en": "Insurance Provider"},
    "health_insurance.provider_placeholder": {"de": "Versicherung auswählen...", "en": "Select insurance provider..."},
    "health_insurance.search_provider": {"de": "Versicherung suchen...", "en": "Search insurance provider..."},
    "health_insurance.coverage_type": {"de": "Beitragsart", "en": "Coverage Type"},
    "health_insurance.amount": {"de": "Betrag (€)", "en": "Amount (€)"},
    "health_insurance.amount_placeholder": {"de": "z.B. 450.00", "en": "e.g. 450.00"},
    "health_insurance.date": {"de": "Datum", "en": "Date"},
    "health_insurance.has_krankengeld": {"de": "Mit Krankengeldanspruch", "en": "With Sick Pay Entitlement"},
    "health_insurance.has_krankengeld_hint": {
        "de": "Bei GKV: 4% Kürzung wenn Krankengeldanspruch besteht",
        "en": "For GKV: 4% reduction if sick pay entitlement exists"
    },
    "health_insurance.policy_number": {"de": "Versicherungsnummer", "en": "Policy Number"},
    "health_insurance.policy_number_placeholder": {"de": "Optional", "en": "Optional"},
    "health_insurance.notes": {"de": "Notizen", "en": "Notes"},
    "health_insurance.notes_placeholder": {"de": "z.B. Monatsbeitrag Januar", "en": "e.g. Monthly contribution January"},

    # Buttons
    "health_insurance.save": {"de": "Zahlung speichern", "en": "Save Payment"},
    "health_insurance.cancel": {"de": "Abbrechen", "en": "Cancel"},
    "health_insurance.delete": {"de": "Löschen", "en": "Delete"},
    "health_insurance.confirm_delete": {"de": "Zahlung wirklich löschen?", "en": "Really delete payment?"},

    # Table headers
    "health_insurance.table.date": {"de": "Datum", "en": "Date"},
    "health_insurance.table.provider": {"de": "Versicherung", "en": "Provider"},
    "health_insurance.table.coverage": {"de": "Beitragsart", "en": "Coverage"},
    "health_insurance.table.amount": {"de": "Betrag", "en": "Amount"},
    "health_insurance.table.deductible": {"de": "Absetzbar", "en": "Deductible"},
    "health_insurance.table.actions": {"de": "Aktionen", "en": "Actions"},

    # Empty states
    "health_insurance.no_payments": {"de": "Keine Zahlungen erfasst", "en": "No payments recorded"},
    "health_insurance.no_payments_hint": {
        "de": "Erfassen Sie Ihre Krankenversicherungsbeiträge für die Steuererklärung.",
        "en": "Record your health insurance contributions for your tax return."
    },
    "health_insurance.not_found": {"de": "Zahlung nicht gefunden", "en": "Payment not found"},

    # Summary/Report
    "health_insurance.annual_summary": {"de": "Jahresübersicht", "en": "Annual Summary"},
    "health_insurance.for_tax_return": {"de": "Für Anlage Vorsorgeaufwand", "en": "For Tax Return"},
    "health_insurance.basis_category": {"de": "Basisabsicherung (unbegrenzt)", "en": "Basic Coverage (unlimited)"},
    "health_insurance.limited_category": {"de": "Wahlleistungen (max. 2.800 €)", "en": "Optional Services (max. €2,800)"},
    "health_insurance.krankengeld_reduction": {"de": "GKV-Kürzung (4%)", "en": "GKV Reduction (4%)"},
    "health_insurance.total_deductible": {"de": "Gesamtabzug", "en": "Total Deduction"},

    # Tax hints
    "health_insurance.hint_basis": {
        "de": "Unbegrenzt absetzbar (§ 10 Abs. 1 Nr. 3 EStG)",
        "en": "Unlimited deduction (§ 10 Abs. 1 Nr. 3 EStG)"
    },
    "health_insurance.hint_wahl": {
        "de": "Limit: 2.800 EUR/Jahr für Freiberufler",
        "en": "Limit: EUR 2,800/year for freelancers"
    },
    "health_insurance.hint_krankengeld": {
        "de": "4% Kürzung bei GKV mit Krankengeldanspruch",
        "en": "4% reduction for GKV with sick pay entitlement"
    },

    # Chart labels
    "health_insurance.chart.by_coverage": {"de": "Nach Beitragsart", "en": "By Coverage Type"},
    "health_insurance.chart.by_provider": {"de": "Nach Versicherung", "en": "By Provider"},

    # Monthly breakdown
    "health_insurance.monthly_breakdown": {"de": "Monatliche Übersicht", "en": "Monthly Breakdown"},
    "health_insurance.month": {"de": "Monat", "en": "Month"},

    # Additional stats card labels
    "health_insurance.payments": {"de": "Zahlungen", "en": "payments"},
    "health_insurance.tax_benefit": {"de": "Steuerersparnis", "en": "Tax Benefit"},
    "health_insurance.of_limit": {"de": "von", "en": "of"},
    "health_insurance.limit": {"de": "Limit", "en": "limit"},
    "health_insurance.this_month": {"de": "Monat", "en": "Month"},
    "health_insurance.new": {"de": "neu", "en": "new"},

    # Limit status card
    "health_insurance.limit_status": {"de": "Wahlleistungen Limit", "en": "Optional Services Limit"},
    "health_insurance.used": {"de": "Genutzt", "en": "Used"},
    "health_insurance.remaining": {"de": "Verbleibend", "en": "Remaining"},

    # Coverage breakdown
    "health_insurance.by_coverage": {"de": "Nach Leistungsart", "en": "By Coverage Type"},

    # Tax info card
    "health_insurance.tax_info": {"de": "Steuerhinweis", "en": "Tax Info"},
    "health_insurance.basis_hint_title": {"de": "Basisabsicherung:", "en": "Basic Coverage:"},
    "health_insurance.basis_hint": {"de": "100% absetzbar, kein Limit", "en": "100% deductible, no limit"},
    "health_insurance.pflege_hint_title": {"de": "Pflegeversicherung:", "en": "Care Insurance:"},
    "health_insurance.pflege_hint": {"de": "100% absetzbar, kein Limit", "en": "100% deductible, no limit"},
    "health_insurance.wahl_hint_title": {"de": "Wahlleistungen:", "en": "Optional Services:"},
    "health_insurance.wahl_hint": {"de": "Limit 2.800 EUR/Jahr", "en": "Limit EUR 2,800/year"},
    "health_insurance.krankengeld_hint_title": {"de": "GKV mit Krankengeld:", "en": "GKV with Sick Pay:"},
    "health_insurance.krankengeld_hint": {"de": "4% Abzug vom Beitrag", "en": "4% deduction from contribution"},

    # Table and filter
    "health_insurance.coverage": {"de": "Leistungsart", "en": "Coverage"},
    "health_insurance.deductible_short": {"de": "Absetzbar", "en": "Deductible"},
    "health_insurance.all_coverage": {"de": "Alle Leistungsarten", "en": "All Coverage Types"},

    # Empty states
    "health_insurance.create_first_hint": {
        "de": "Erfasse deine erste Krankenversicherungszahlung",
        "en": "Record your first health insurance payment"
    },
    "health_insurance.no_payments_filter": {
        "de": "Keine Zahlungen für diesen Filter",
        "en": "No payments match this filter"
    },
    "health_insurance.try_other_filter": {
        "de": "Versuche einen anderen Filter",
        "en": "Try a different filter"
    },

    # Form
    "health_insurance.insurance_type": {"de": "Versicherungsart", "en": "Insurance Type"},
    "health_insurance.select_provider": {"de": "Versicherung auswählen...", "en": "Select insurance provider..."},
    "health_insurance.unlimited": {"de": "unbegrenzt", "en": "unlimited"},
    "health_insurance.limited": {"de": "begrenzt", "en": "limited"},
    "health_insurance.record_payment": {"de": "Neue Krankenversicherungszahlung", "en": "New Health Insurance Payment"},

    # Summary template (Anlage Vorsorgeaufwand)
    "health_insurance.anlage_vorsorgeaufwand": {"de": "Anlage Vorsorgeaufwand", "en": "Tax Deduction Form"},
    "health_insurance.anlage_hint": {
        "de": "Die folgenden Werte können direkt in Ihre Steuererklärung übernommen werden.",
        "en": "The following values can be transferred directly to your tax return."
    },
    "health_insurance.krankenversicherung_basis": {
        "de": "Krankenversicherung (Basisabsicherung)",
        "en": "Health Insurance (Basic Coverage)"
    },
    "health_insurance.pflegeversicherung": {"de": "Pflegeversicherung", "en": "Care Insurance"},
    "health_insurance.krankengeld_reduction_label": {
        "de": "Abzug für Krankengeld (4%)",
        "en": "Sick Pay Deduction (4%)"
    },
    "health_insurance.wahlleistungen_label": {
        "de": "Wahlleistungen/Zusatzversicherung",
        "en": "Optional/Supplementary Insurance"
    },
    "health_insurance.exceeded_limit": {"de": "Nicht absetzbar", "en": "Not deductible"},
    "health_insurance.effective_rate": {"de": "Effektive Absetzungsrate", "en": "Effective Deduction Rate"},
    "health_insurance.of_total_paid": {"de": "von", "en": "of"},

    # Provider dropdown
    "health_insurance.no_providers": {"de": "Keine Versicherungen gefunden", "en": "No insurance providers found"},
}


def t(key: str, lang: str = "de") -> str:
    """Get translation for a key.

    Args:
        key: Translation key (e.g., "nav.dashboard")
        lang: Language code ("de" or "en")

    Returns:
        Translated string, or key if not found
    """
    if key in TRANSLATIONS:
        return TRANSLATIONS[key].get(lang, TRANSLATIONS[key].get("de", key))
    return key


def get_translator(lang: str = "de") -> Callable[[str], str]:
    """Get a translator function for a specific language.

    Usage in Jinja2:
        {{ _("nav.dashboard") }}

    Args:
        lang: Language code

    Returns:
        Translation function
    """
    def translate(key: str) -> str:
        return t(key, lang)
    return translate


# Category translations helper
def get_category_name(category: str, lang: str = "de") -> str:
    """Get translated category name."""
    return t(f"category.{category}", lang)


# Status translations helper
def get_status_name(status: str, lang: str = "de") -> str:
    """Get translated status name."""
    return t(f"status.{status}", lang)
