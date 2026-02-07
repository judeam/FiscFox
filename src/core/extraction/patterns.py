"""Invoice extraction patterns for English and German invoices.

Regex patterns optimized for both English (primary) and German invoice formats.
German invoices follow §14 UStG requirements.
All patterns are designed to handle common variations in international business documents.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

# =============================================================================
# Invoice Number Patterns
# =============================================================================

INVOICE_NUMBER_PATTERNS = [
    # English patterns (primary)
    (r"Invoice[\s:]*(?:No\.?|Number|#|ID)[\s:]*([A-Za-z0-9\-/]+)", 0.95),
    (r"Invoice[\s:#]*([A-Za-z0-9\-/]+)", 0.9),
    (r"Inv[\s\-:#]*([A-Za-z0-9\-/]+)", 0.85),
    (r"(?:Reference|Ref)[\s:]*(?:No\.?|#)?[\s:]*([A-Za-z0-9\-/]+)", 0.8),
    # German patterns
    (r"Rechnungs?(?:nummer|nr\.?|-)[\s:]*([A-Za-z0-9\-/]+)", 0.9),
    (r"Rechnung[\s:]*(?:Nr\.?|Nummer|#)[\s:]*([A-Za-z0-9\-/]+)", 0.9),
    (r"RE[\s\-]?(\d{4}[\-/]\d{3,6})", 0.85),  # RE-2026-001
    (r"(?:Rg\.?|RG)[\s\-:]*(\d{4}[\-/]?\d{3,6})", 0.85),
    # Generic number pattern (lower confidence)
    (r"INV[\-]?(\d{4,10})", 0.7),
    (r"(\d{4}[\-/]\d{3,6})", 0.5),
]

# =============================================================================
# Date Patterns
# =============================================================================

DATE_PATTERNS = [
    # English date patterns with labels (primary)
    (r"(?:Invoice\s*)?Date[\s:]*(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})", 0.95),
    (r"(?:Issue|Issued)[\s:]*(?:Date)?[\s:]*(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})", 0.9),
    # US format with month name: January 15, 2026 or Jan 15, 2026
    (r"(?:Invoice\s*)?Date[\s:]*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})", 0.95),
    (r"Date[\s:]*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})", 0.9),
    (r"Date[\s:]*(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})", 0.85),
    # ISO format (international standard)
    (r"(?:Invoice\s*)?Date[\s:]*(\d{4}[-/]\d{2}[-/]\d{2})", 0.9),
    (r"(\d{4}[-/]\d{2}[-/]\d{2})", 0.75),
    # German date patterns with labels
    (r"Rechnungsdatum[\s:]*(\d{1,2}[./]\d{1,2}[./]\d{2,4})", 0.9),
    (r"Datum[\s:]*(\d{1,2}[./]\d{1,2}[./]\d{2,4})", 0.85),
    (r"(?:vom|am)[\s:]*(\d{1,2}[./]\d{1,2}[./]\d{2,4})", 0.8),
    # Generic date formats (lower confidence)
    (r"(\d{1,2}\.\d{1,2}\.\d{4})", 0.6),  # DD.MM.YYYY
    (r"(\d{1,2}/\d{1,2}/\d{4})", 0.6),  # MM/DD/YYYY or DD/MM/YYYY
    # Standalone month name format
    (r"([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})", 0.5),
]

DUE_DATE_PATTERNS = [
    # English patterns (primary) - numeric dates
    (r"(?:Due\s*(?:Date)?|Payment\s*Due)[\s:]*(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})", 0.95),
    (r"(?:Pay(?:ment)?\s*)?(?:by|before)[\s:]*(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})", 0.9),
    (r"(?:Due|Payable)[\s:]*(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})", 0.85),
    # English patterns - month name format: Due Date: February 14, 2026
    (r"(?:Due\s*(?:Date)?|Payment\s*Due)[\s:]*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})", 0.95),
    (r"(?:Pay(?:ment)?\s*)?(?:by|before)[\s:]*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})", 0.9),
    (r"(?:Due|Payable)[\s:]*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})", 0.85),
    # ISO format
    (r"(?:Due\s*(?:Date)?|Payment\s*Due)[\s:]*(\d{4}[-/]\d{2}[-/]\d{2})", 0.9),
    # Payment terms with date
    (r"(?:Net\s*\d+|Terms).*?(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})", 0.75),
    # German patterns
    (r"(?:Fällig(?:keit)?(?:sdatum)?|Zahlbar bis|Zahlungsziel)[\s:]*(\d{1,2}[./]\d{1,2}[./]\d{2,4})", 0.9),
    (r"(?:bis zum|spätestens)[\s:]*(\d{1,2}[./]\d{1,2}[./]\d{2,4})", 0.8),
]

# =============================================================================
# VAT ID Patterns (§14 UStG mandatory)
# =============================================================================

VAT_ID_PATTERNS = [
    # German USt-IdNr
    (r"USt[\.\-]?(?:Id[\.\-]?)?(?:Nr\.?|Nummer)[\s:]*([A-Z]{2}\s?\d{9,12})", 0.95),
    (r"Umsatzsteuer[\-\s]?(?:Identifikations)?(?:nummer|nr\.?)[\s:]*([A-Z]{2}\s?\d{9,12})", 0.9),
    # Direct German format
    (r"(DE\s?\d{9})", 0.9),
    # English VAT
    (r"VAT[\s\-]?(?:ID|No\.?|Number)[\s:]*([A-Z]{2}\s?\d{9,12})", 0.85),
    (r"Tax[\s\-]?(?:ID|Number)[\s:]*([A-Z]{2}\s?\d{9,12})", 0.8),
]

# =============================================================================
# Amount Patterns (German number format: 1.234,56 €)
# =============================================================================

GROSS_AMOUNT_PATTERNS = [
    # English labels (primary) - supports $, €, £, or no currency
    (r"(?:Total|Grand\s*Total)[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.95),
    (r"(?:Amount\s*Due|Balance\s*Due)[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.95),
    (r"(?:Total\s*)?(?:Amount|Due)[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.9),
    (r"(?:Invoice\s*)?Total[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.9),
    (r"(?:Please\s*)?Pay[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.85),
    # German labels
    (r"(?:Gesamt)?(?:betrag|summe)[\s:]*(?:brutto)?[\s:]*€?\s*([\d.,]+)\s*€?", 0.9),
    (r"Brutto(?:betrag)?[\s:]*€?\s*([\d.,]+)\s*€?", 0.95),
    (r"(?:Rechnungs)?betrag[\s:]*€?\s*([\d.,]+)\s*€?", 0.85),
    (r"(?:Endsumme|Endbetrag)[\s:]*€?\s*([\d.,]+)\s*€?", 0.9),
    (r"(?:Zu\s*zahlen|Zahlbetrag)[\s:]*€?\s*([\d.,]+)\s*€?", 0.9),
]

NET_AMOUNT_PATTERNS = [
    # English labels (primary)
    (r"(?:Sub\s*)?Total[\s:]*(?:before\s*(?:tax|VAT))?[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.9),
    (r"Subtotal[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.9),
    (r"Net(?:\s*(?:Amount|Total))?[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.85),
    (r"(?:Amount\s*)?(?:excl(?:uding)?|ex|before)[\s.]*(?:VAT|Tax)[\s:]*[\$€£]?\s*([\d.,]+)", 0.85),
    # German labels
    (r"Netto(?:betrag)?[\s:]*€?\s*([\d.,]+)\s*€?", 0.9),
    (r"(?:Summe\s*)?(?:netto|ohne\s*(?:MwSt|USt))[\s:]*€?\s*([\d.,]+)\s*€?", 0.85),
    (r"Zwischensumme[\s:]*€?\s*([\d.,]+)\s*€?", 0.8),
]

VAT_AMOUNT_PATTERNS = [
    # English labels (primary)
    (r"VAT[\s:]*(?:@?\s*\d{1,2}\s*%)?[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.95),
    (r"(?:Sales\s*)?Tax[\s:]*(?:@?\s*\d{1,2}\s*%)?[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.9),
    (r"(?:VAT|Tax)\s*(?:Amount)?[\s:]*[\$€£]?\s*([\d.,]+)\s*[\$€£]?", 0.85),
    # German labels
    (r"(?:MwSt|USt)\.?[\s:]*(?:\d{1,2}\s*%)?[\s:]*€?\s*([\d.,]+)\s*€?", 0.9),
    (r"(?:Mehrwert|Umsatz)steuer[\s:]*(?:\d{1,2}\s*%)?[\s:]*€?\s*([\d.,]+)\s*€?", 0.9),
    (r"(?:davon\s*)?(?:MwSt|USt)[\s:]*€?\s*([\d.,]+)\s*€?", 0.85),
]

# =============================================================================
# VAT Rate Detection
# =============================================================================

VAT_RATE_PATTERNS = [
    # English patterns (primary)
    (r"(?:VAT|Tax)[\s@:]*(\d{1,2})\s*%", 0.95),
    (r"(\d{1,2})\s*%\s*(?:VAT|Tax|Sales\s*Tax)", 0.9),
    (r"(?:Tax|VAT)\s*(?:Rate)?[\s:]*(\d{1,2})\s*%", 0.85),
    (r"@\s*(\d{1,2})\s*%", 0.75),  # Common format: @ 20%
    # German patterns
    (r"(\d{1,2})\s*%\s*(?:MwSt|USt|Mehrwertsteuer|Umsatzsteuer)", 0.9),
    (r"(?:MwSt|USt)[\s.]*(\d{1,2})\s*%", 0.9),
    (r"(?:Steuersatz)[\s:]*(\d{1,2})\s*%", 0.85),
]

# Map detected rates to valid VatRate values
# Includes common international rates that map to German equivalents
VAT_RATE_MAP = {
    # Standard rates (map to 19%)
    "19": "0.19",
    "20": "0.19",  # UK, Austria, etc.
    "21": "0.19",  # Belgium, Netherlands, etc.
    "22": "0.19",
    "23": "0.19",  # Ireland, Poland, etc.
    "24": "0.19",
    "25": "0.19",  # Sweden, Denmark, etc.
    # Reduced rates (map to 7%)
    "7": "0.07",
    "5": "0.07",  # UK reduced
    "6": "0.07",
    "8": "0.07",
    "9": "0.07",
    "10": "0.07",
    # Zero rate
    "0": "0.00",
}

# =============================================================================
# Client/Address Patterns
# =============================================================================

# Email patterns
EMAIL_PATTERNS = [
    (r"(?:E[\-]?mail|Email)[\s:]*([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", 0.95),
    (r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", 0.8),
]

# Phone patterns (international formats)
PHONE_PATTERNS = [
    # Labeled phone numbers
    (r"(?:Tel(?:ephone|efon)?|Phone|Fax|Mobile|Mob|Cell)[\s.:]*(\+?[\d\s\-().]{8,20})", 0.95),
    # International format: +44 20 1234 5678
    (r"(\+\d{1,3}[\s\-]?\d{1,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4})", 0.85),
    # German format: 0123 456789 or 0123-456789
    (r"(0\d{2,4}[\s\-/]?\d{4,8})", 0.75),
]

# Street/Address patterns (enhanced)
# Patterns ordered by specificity - most specific first to avoid false positives
STREET_PATTERNS = [
    # US/UK format: Number + Street Name (most specific, preferred)
    # e.g., "71 South Parkway", "123 Main Street", "42 Oak Avenue"
    (r"(\d+\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Way|Place|Pl|Court|Ct|Close|Crescent|Cres|Terrace|Gardens?|Grove|Park|Parkway|Square|Boulevard|Blvd|Circle|Cir|Highway|Hwy))(?:\s*,|\s*$|\s+[A-Z])", 0.95),
    # German format: Straßenname Nr (e.g., Hauptstraße 42a, Berliner Allee 10)
    (r"([A-ZÄÖÜ][a-zäöüß]+(?:straße|str|weg|allee|platz|ring|gasse|damm|ufer|chaussee)\s*\d+[a-z]?)", 0.9),
    # UK format: Name + Street suffix at line start (e.g., "South Parkway,")
    (r"(?:^|\n)\s*(\d+\s+[A-Za-z][A-Za-z\s\-]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Way|Place|Pl|Court|Ct|Close|Crescent|Terrace|Gardens?|Grove|Park|Parkway|Square|Boulevard|Blvd))\s*[,\n]", 0.85),
    # Named street without number (lower confidence)
    (r"(?:^|\n)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+(?:Street|Avenue|Road|Drive|Lane|Way|Place|Court|Close|Crescent|Terrace|Gardens?|Grove|Park|Parkway|Square|Boulevard))\s*[,\n]", 0.7),
]

# Postal/ZIP code patterns (by country)
POSTAL_CODE_PATTERNS = [
    # UK postcode: SW1A 1AA, EC1A 1BB, DN14 9JW
    (r"\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b", 0.95, "GB"),
    # German PLZ: 5 digits
    (r"\b(\d{5})\b(?=\s*[A-Za-zÄÖÜäöüß])", 0.9, "DE"),
    # US ZIP: 5 or 9 digits
    (r"\b(\d{5}(?:-\d{4})?)\b", 0.85, "US"),
    # Netherlands: 4 digits + 2 letters
    (r"\b(\d{4}\s?[A-Z]{2})\b", 0.85, "NL"),
    # France/Italy/Spain: 5 digits
    (r"\b(\d{5})\b", 0.7, ""),
]

# City patterns (extract from context)
CITY_PATTERNS = [
    # City after postal code
    (r"[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\s+([A-Za-z][A-Za-z\s\-]+)", 0.9),  # UK
    (r"\d{5}\s+([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\s\-]+)", 0.85),  # German
    (r"\d{5}(?:-\d{4})?\s+([A-Za-z][A-Za-z\s\-]+)", 0.8),  # US
]

# Country detection patterns
COUNTRY_PATTERNS = [
    (r"\b(?:United\s*Kingdom|UK|Great\s*Britain|GB|England|Scotland|Wales)\b", "GB", 0.95),
    (r"\b(?:Germany|Deutschland|DE)\b", "DE", 0.95),
    (r"\b(?:France|Frankreich|FR)\b", "FR", 0.9),
    (r"\b(?:Netherlands|Nederland|Holland|NL)\b", "NL", 0.9),
    (r"\b(?:United\s*States|USA|US|America)\b", "US", 0.9),
    (r"\b(?:Austria|Österreich|AT)\b", "AT", 0.9),
    (r"\b(?:Switzerland|Schweiz|Suisse|CH)\b", "CH", 0.9),
    (r"\b(?:Belgium|Belgien|Belgique|BE)\b", "BE", 0.9),
    (r"\b(?:Ireland|Irland|IE)\b", "IE", 0.9),
    (r"\b(?:Spain|España|Spanien|ES)\b", "ES", 0.9),
    (r"\b(?:Italy|Italia|Italien|IT)\b", "IT", 0.9),
    (r"\b(?:Poland|Polska|Polen|PL)\b", "PL", 0.9),
]

# Client name is typically at the top of the invoice, after sender info
CLIENT_NAME_PATTERNS = [
    # English patterns (primary)
    (r"(?:Bill(?:ed)?\s*To|Invoice\s*To|Client|Customer|Sold\s*To)[\s:]*\n*([A-Za-z\s\-&.,]+(?:Ltd\.?|Inc\.?|LLC|Corp\.?|PLC|LLP)?)", 0.95),
    (r"(?:To|Attn|Attention)[\s:]*\n*([A-Za-z\s\-&.,]+(?:Ltd\.?|Inc\.?|LLC|Corp\.?)?)", 0.85),
    # German patterns
    (r"(?:An|Kunde|Rechnungsempfänger|Empfänger)[\s:]*\n*([A-Za-zÄÖÜäöüß\s\-&.]+(?:GmbH|AG|UG|e\.?K\.?|KG|OHG)?)", 0.9),
    # Company suffixes help identify names (international)
    (r"([A-Za-z\s\-&.,]+(?:Ltd\.?|Limited|Inc\.?|Incorporated|LLC|Corp\.?|Corporation|PLC|LLP|GmbH|AG|UG|B\.?V\.?|S\.?A\.?|S\.?L\.?))", 0.75),
]

# Address patterns (international formats)
ADDRESS_PATTERNS = [
    # US/UK format: Number Street Name
    (r"(\d+\s+[A-Za-z\s\-]+(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Drive|Dr\.?|Lane|Ln\.?|Way|Boulevard|Blvd\.?))", 0.85),
    # UK/International: City, Postcode
    (r"([A-Za-z\s\-]+)[,\s]+([A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})", 0.8),  # UK postcode
    (r"([A-Za-z\s\-]+)[,\s]+(\d{5}(?:-\d{4})?)", 0.8),  # US ZIP code
    # German format: Street Nr, PLZ City
    (r"([A-Za-zÄÖÜäöüß\-\s]+(?:straße|str\.?|weg|allee|platz|ring|gasse)\.?\s*\d+[a-z]?)", 0.85),
    (r"(\d{5})\s+([A-Za-zÄÖÜäöüß\-\s]+)", 0.8),  # German PLZ + City
]

# =============================================================================
# Parsing Utilities
# =============================================================================


def parse_decimal(value: str) -> Decimal | None:
    """Convert international number formats to Decimal.

    Supports:
    - US/UK format: 1,234.56 (comma = thousands, period = decimal)
    - German/EU format: 1.234,56 (period = thousands, comma = decimal)
    - Plain numbers: 1234.56 or 1234,56

    Args:
        value: Number string in various formats

    Returns:
        Decimal value or None if parsing fails
    """
    if not value:
        return None

    try:
        # Remove spaces and currency symbols
        cleaned = value.strip()
        cleaned = re.sub(r"[\$€£\s]", "", cleaned)

        if not cleaned:
            return None

        # Determine format by analyzing separators
        has_comma = "," in cleaned
        has_period = "." in cleaned

        if has_comma and has_period:
            # Both separators present - determine which is decimal
            last_comma = cleaned.rfind(",")
            last_period = cleaned.rfind(".")

            if last_comma > last_period:
                # German format: 1.234,56
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                # US format: 1,234.56
                cleaned = cleaned.replace(",", "")

        elif has_comma and not has_period:
            # Could be German decimal (1234,56) or US thousands (1,234)
            # Check if comma is followed by exactly 2 digits at end
            if re.match(r".*,\d{2}$", cleaned):
                # German decimal
                cleaned = cleaned.replace(",", ".")
            else:
                # US thousands separator
                cleaned = cleaned.replace(",", "")

        elif has_period and not has_comma:
            # Could be US decimal (1234.56) or German thousands (1.234)
            # Check if period is followed by exactly 2 digits at end
            if re.match(r".*\.\d{2}$", cleaned):
                # US decimal - keep as is
                pass
            elif cleaned.count(".") > 1:
                # Multiple periods = thousands separators
                cleaned = cleaned.replace(".", "")
            # Single period with not exactly 2 digits after - ambiguous
            # Default to treating as decimal (US format more common)

        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


# Alias for backwards compatibility
parse_german_decimal = parse_decimal


def parse_date(value: str) -> date | None:
    """Parse international date formats.

    Supports:
    - ISO format: YYYY-MM-DD (preferred)
    - US format: MM/DD/YYYY
    - UK/EU format: DD/MM/YYYY, DD.MM.YYYY
    - Written: January 15, 2026

    Args:
        value: Date string to parse

    Returns:
        date object or None if parsing fails
    """
    if not value:
        return None

    value = value.strip()

    # Try ISO format YYYY-MM-DD first (unambiguous)
    match = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if match:
        year, month, day = match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            pass

    # Try written format: January 15, 2026
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    match = re.match(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", value)
    if match:
        month_str, day, year = match.groups()
        month_key = month_str[:3].lower()
        if month_key in months:
            try:
                return date(int(year), months[month_key], int(day))
            except ValueError:
                pass

    # Try DD/MM/YYYY or MM/DD/YYYY or DD.MM.YYYY
    match = re.match(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})", value)
    if match:
        first, second, year = match.groups()
        first, second = int(first), int(second)
        year = int(year)

        # Handle two-digit year
        if year < 100:
            year += 2000 if year < 50 else 1900

        # Determine if DD/MM or MM/DD
        # If first > 12, must be day (DD/MM format)
        # If second > 12, must be day (MM/DD format)
        # Otherwise, assume DD/MM (EU format) as it's more common internationally
        if first > 12:
            day, month = first, second
        elif second > 12:
            month, day = first, second
        else:
            # Ambiguous - default to DD/MM (EU format)
            day, month = first, second

        try:
            return date(year, month, day)
        except ValueError:
            # Try the other interpretation
            try:
                return date(year, first, second)
            except ValueError:
                pass

    return None


# Alias for backwards compatibility
parse_german_date = parse_date


def extract_with_patterns(
    text: str,
    patterns: list[tuple[str, float]],
    flags: int = re.IGNORECASE | re.MULTILINE,
) -> tuple[str | None, float, str]:
    """Extract value using multiple regex patterns.

    Tries patterns in order, returning first match with highest confidence.

    Args:
        text: Text to search
        patterns: List of (pattern, confidence) tuples
        flags: Regex flags

    Returns:
        Tuple of (matched_value, confidence, pattern_used)
    """
    for pattern, confidence in patterns:
        match = re.search(pattern, text, flags)
        if match:
            # Return first captured group
            value = match.group(1).strip()
            if value:
                return value, confidence, pattern

    return None, 0.0, ""


def extract_all_amounts(text: str) -> dict[str, tuple[Decimal | None, float]]:
    """Extract all monetary amounts from text.

    Returns dict with gross, net, and vat amounts if found.

    Args:
        text: Invoice text

    Returns:
        Dict mapping amount type to (value, confidence) tuples
    """
    results = {}

    # Extract gross amount
    value, conf, _ = extract_with_patterns(text, GROSS_AMOUNT_PATTERNS)
    if value:
        results["gross"] = (parse_german_decimal(value), conf)

    # Extract net amount
    value, conf, _ = extract_with_patterns(text, NET_AMOUNT_PATTERNS)
    if value:
        results["net"] = (parse_german_decimal(value), conf)

    # Extract VAT amount
    value, conf, _ = extract_with_patterns(text, VAT_AMOUNT_PATTERNS)
    if value:
        results["vat"] = (parse_german_decimal(value), conf)

    return results


def detect_vat_rate(text: str) -> tuple[str | None, float]:
    """Detect VAT rate from text.

    Args:
        text: Invoice text

    Returns:
        Tuple of (vat_rate_string, confidence)
        vat_rate_string is one of: "0.19", "0.07", "0.00"
    """
    value, conf, _ = extract_with_patterns(text, VAT_RATE_PATTERNS)
    if value:
        rate = VAT_RATE_MAP.get(value)
        if rate:
            return rate, conf

    # Try to infer from amounts
    # If we have gross and net, calculate rate
    amounts = extract_all_amounts(text)
    gross = amounts.get("gross", (None, 0))[0]
    net = amounts.get("net", (None, 0))[0]

    if gross and net and net > 0:
        try:
            calculated_rate = (gross - net) / net
            # Round to nearest standard rate
            if calculated_rate > Decimal("0.15"):
                return "0.19", 0.7
            elif calculated_rate > Decimal("0.03"):
                return "0.07", 0.7
            else:
                return "0.00", 0.6
        except (ValueError, ZeroDivisionError, ArithmeticError):
            pass

    return None, 0.0


def is_likely_scanned_pdf(text: str, page_count: int) -> bool:
    """Determine if PDF is likely scanned (needs OCR).

    Heuristics:
    - Very little text extracted
    - High ratio of garbled/non-word characters
    - Short average line length

    Args:
        text: Extracted text from PDF
        page_count: Number of pages in PDF

    Returns:
        True if PDF is likely scanned/image-based
    """
    if not text:
        return True

    # Minimal text per page suggests scanned
    words = text.split()
    words_per_page = len(words) / max(page_count, 1)
    if words_per_page < 20:
        return True

    # Check for garbled text (high non-letter ratio)
    letters = sum(1 for c in text if c.isalpha())
    total = len(text.replace(" ", "").replace("\n", ""))
    if total > 0 and letters / total < 0.5:
        return True

    return False
