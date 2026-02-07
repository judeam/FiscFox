"""OCR-based PDF extraction using pytesseract.

Fallback extraction method for scanned/image-based PDFs.
Converts PDF pages to images, then applies OCR to extract text.
"""

import time
from decimal import Decimal
from pathlib import Path

try:
    import pytesseract
    from pdf2image import convert_from_bytes, convert_from_path
    from PIL import Image

    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from src.core.extraction.models import (
    ExtractedClientInfo,
    ExtractedDateField,
    ExtractedDecimalField,
    ExtractedField,
    ExtractedInvoiceData,
    ExtractionMethod,
    ExtractionResult,
)
from src.core.extraction.patterns import (
    CLIENT_NAME_PATTERNS,
    COUNTRY_PATTERNS,
    DATE_PATTERNS,
    DUE_DATE_PATTERNS,
    EMAIL_PATTERNS,
    GROSS_AMOUNT_PATTERNS,
    INVOICE_NUMBER_PATTERNS,
    NET_AMOUNT_PATTERNS,
    PHONE_PATTERNS,
    POSTAL_CODE_PATTERNS,
    STREET_PATTERNS,
    VAT_AMOUNT_PATTERNS,
    detect_vat_rate,
    extract_with_patterns,
    parse_date,
    parse_decimal,
)


class OCRExtractor:
    """Extract invoice data from scanned PDFs using OCR."""

    # Default DPI for PDF to image conversion
    DEFAULT_DPI = 300

    # OCR configuration for better invoice text recognition
    OCR_CONFIG = "--oem 3 --psm 6"  # LSTM engine, assume uniform block of text

    # Unicode ligature replacements
    LIGATURE_MAP = {
        "\ufb00": "ff",   # ﬀ
        "\ufb01": "fi",   # ﬁ
        "\ufb02": "fl",   # ﬂ
        "\ufb03": "ffi",  # ﬃ
        "\ufb04": "ffl",  # ﬄ
        "\ufb05": "st",   # ﬅ (long s + t)
        "\ufb06": "st",   # ﬆ
    }

    def __init__(self, dpi: int = DEFAULT_DPI, lang: str = "eng+deu"):
        """Initialize the OCR extractor.

        Args:
            dpi: Resolution for PDF to image conversion (higher = better quality but slower)
            lang: Tesseract language codes (eng for English, deu for German)
        """
        if not OCR_AVAILABLE:
            raise RuntimeError(
                "OCR dependencies not available. Install with: "
                "pip install pytesseract pdf2image Pillow"
            )

        self.dpi = dpi
        self.lang = lang

    def extract(self, pdf_path: str | Path) -> ExtractionResult:
        """Extract invoice data from a scanned PDF file using OCR.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            ExtractionResult with extracted data or errors
        """
        start_time = time.time()
        errors: list[str] = []
        warnings: list[str] = []

        try:
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                return ExtractionResult(
                    success=False,
                    errors=[f"File not found: {pdf_path}"],
                    method_used=ExtractionMethod.OCR,
                )

            # Convert PDF to images
            try:
                images = convert_from_path(pdf_path, dpi=self.dpi)
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    errors=[f"Failed to convert PDF to images: {str(e)}"],
                    method_used=ExtractionMethod.OCR,
                )

            # Extract text from all pages using OCR
            full_text = ""
            page_count = len(images)

            for i, image in enumerate(images):
                try:
                    page_text = pytesseract.image_to_string(
                        image, lang=self.lang, config=self.OCR_CONFIG
                    )
                    full_text += page_text + "\n"
                except Exception as e:
                    warnings.append(f"OCR failed for page {i + 1}: {str(e)}")

            if not full_text.strip():
                return ExtractionResult(
                    success=False,
                    errors=["OCR produced no text. PDF may be empty or corrupted."],
                    method_used=ExtractionMethod.OCR,
                )

            # Extract invoice data from OCR text
            data = self._extract_from_text(full_text, page_count)
            data.raw_text = full_text
            data.extraction_method = ExtractionMethod.OCR

            # Calculate overall confidence (reduce by 10% for OCR uncertainty)
            base_confidence = data.calculate_overall_confidence()
            data.overall_confidence = base_confidence * 0.9  # OCR penalty

            # Add OCR-specific warnings
            warnings.append("Extracted using OCR. Please verify all fields carefully.")

            if data.overall_confidence < 0.5:
                warnings.append(
                    "Low OCR extraction confidence. Manual review strongly recommended."
                )

            if not data.has_minimum_data:
                warnings.append("Could not extract minimum required data (invoice number or client + amount).")

            processing_time = int((time.time() - start_time) * 1000)

            return ExtractionResult(
                success=True,
                data=data,
                errors=errors,
                warnings=warnings,
                method_used=ExtractionMethod.OCR,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            return ExtractionResult(
                success=False,
                errors=[f"OCR extraction failed: {str(e)}"],
                method_used=ExtractionMethod.OCR,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    def extract_from_bytes(self, pdf_bytes: bytes, sender_vat_id: str | None = None) -> ExtractionResult:
        """Extract invoice data from PDF bytes using OCR.

        Args:
            pdf_bytes: PDF file contents as bytes
            sender_vat_id: User's own VAT ID to exclude from client detection

        Returns:
            ExtractionResult with extracted data or errors
        """
        start_time = time.time()
        errors: list[str] = []
        warnings: list[str] = []

        try:
            # Convert PDF bytes to images
            try:
                images = convert_from_bytes(pdf_bytes, dpi=self.dpi)
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    errors=[f"Failed to convert PDF to images: {str(e)}"],
                    method_used=ExtractionMethod.OCR,
                )

            # Extract text from all pages using OCR
            full_text = ""
            page_count = len(images)

            for i, image in enumerate(images):
                try:
                    page_text = pytesseract.image_to_string(
                        image, lang=self.lang, config=self.OCR_CONFIG
                    )
                    full_text += page_text + "\n"
                except Exception as e:
                    warnings.append(f"OCR failed for page {i + 1}: {str(e)}")

            if not full_text.strip():
                return ExtractionResult(
                    success=False,
                    errors=["OCR produced no text. PDF may be empty or corrupted."],
                    method_used=ExtractionMethod.OCR,
                )

            # Extract invoice data from OCR text
            data = self._extract_from_text(full_text, page_count, sender_vat_id=sender_vat_id)
            data.raw_text = full_text
            data.extraction_method = ExtractionMethod.OCR

            # Calculate overall confidence (reduce by 10% for OCR uncertainty)
            base_confidence = data.calculate_overall_confidence()
            data.overall_confidence = base_confidence * 0.9  # OCR penalty

            # Add OCR-specific warnings
            warnings.append("Extracted using OCR. Please verify all fields carefully.")

            if data.overall_confidence < 0.5:
                warnings.append(
                    "Low OCR extraction confidence. Manual review strongly recommended."
                )

            if not data.has_minimum_data:
                warnings.append("Could not extract minimum required data (invoice number or client + amount).")

            processing_time = int((time.time() - start_time) * 1000)

            return ExtractionResult(
                success=True,
                data=data,
                errors=errors,
                warnings=warnings,
                method_used=ExtractionMethod.OCR,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            return ExtractionResult(
                success=False,
                errors=[f"OCR extraction failed: {str(e)}"],
                method_used=ExtractionMethod.OCR,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    def extract_from_image(self, image: "Image.Image", sender_vat_id: str | None = None) -> ExtractionResult:
        """Extract invoice data from a single image.

        Useful for processing individual invoice images or screenshots.

        Args:
            image: PIL Image object
            sender_vat_id: User's own VAT ID to exclude from client detection

        Returns:
            ExtractionResult with extracted data or errors
        """
        start_time = time.time()
        warnings: list[str] = []

        try:
            # Extract text using OCR
            text = pytesseract.image_to_string(image, lang=self.lang, config=self.OCR_CONFIG)

            if not text.strip():
                return ExtractionResult(
                    success=False,
                    errors=["OCR produced no text from image."],
                    method_used=ExtractionMethod.OCR,
                )

            # Extract invoice data
            data = self._extract_from_text(text, page_count=1, sender_vat_id=sender_vat_id)
            data.raw_text = text
            data.extraction_method = ExtractionMethod.OCR

            # Calculate confidence with OCR penalty
            base_confidence = data.calculate_overall_confidence()
            data.overall_confidence = base_confidence * 0.9

            warnings.append("Extracted using OCR. Please verify all fields carefully.")

            if data.overall_confidence < 0.5:
                warnings.append(
                    "Low OCR extraction confidence. Manual review strongly recommended."
                )

            processing_time = int((time.time() - start_time) * 1000)

            return ExtractionResult(
                success=True,
                data=data,
                warnings=warnings,
                method_used=ExtractionMethod.OCR,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            return ExtractionResult(
                success=False,
                errors=[f"OCR extraction from image failed: {str(e)}"],
                method_used=ExtractionMethod.OCR,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    def _extract_from_text(self, text: str, page_count: int, sender_vat_id: str | None = None) -> ExtractedInvoiceData:
        """Extract invoice fields from OCR text.

        Uses same extraction logic as text extractor but with
        slightly more lenient matching for OCR artifacts.

        Args:
            text: Full text extracted via OCR
            page_count: Number of pages in PDF
            sender_vat_id: User's own VAT ID to exclude from client detection

        Returns:
            ExtractedInvoiceData with all extracted fields
        """
        # Clean up common OCR artifacts
        text = self._clean_ocr_text(text)

        data = ExtractedInvoiceData(page_count=page_count)

        # Extract invoice number
        value, conf, pattern = extract_with_patterns(text, INVOICE_NUMBER_PATTERNS)
        if value:
            # Reduce confidence slightly for OCR
            data.invoice_number = ExtractedField(value=value, confidence=conf * 0.95, source=pattern)

        # Extract invoice date
        value, conf, pattern = extract_with_patterns(text, DATE_PATTERNS)
        if value:
            parsed_date = parse_date(value)
            data.invoice_date = ExtractedDateField(
                value=parsed_date,
                confidence=(conf * 0.95) if parsed_date else 0.0,
                source=pattern,
                raw_value=value,
            )

        # Extract due date
        value, conf, pattern = extract_with_patterns(text, DUE_DATE_PATTERNS)
        if value:
            parsed_date = parse_date(value)
            data.due_date = ExtractedDateField(
                value=parsed_date,
                confidence=(conf * 0.95) if parsed_date else 0.0,
                source=pattern,
                raw_value=value,
            )

        # Extract amounts
        value, conf, pattern = extract_with_patterns(text, GROSS_AMOUNT_PATTERNS)
        if value:
            parsed_amount = parse_decimal(value)
            data.amount_gross = ExtractedDecimalField(
                value=parsed_amount,
                confidence=(conf * 0.95) if parsed_amount else 0.0,
                source=pattern,
                raw_value=value,
            )

        value, conf, pattern = extract_with_patterns(text, NET_AMOUNT_PATTERNS)
        if value:
            parsed_amount = parse_decimal(value)
            data.amount_net = ExtractedDecimalField(
                value=parsed_amount,
                confidence=(conf * 0.95) if parsed_amount else 0.0,
                source=pattern,
                raw_value=value,
            )

        value, conf, pattern = extract_with_patterns(text, VAT_AMOUNT_PATTERNS)
        if value:
            parsed_amount = parse_decimal(value)
            data.vat_amount = ExtractedDecimalField(
                value=parsed_amount,
                confidence=(conf * 0.95) if parsed_amount else 0.0,
                source=pattern,
                raw_value=value,
            )

        # Detect VAT rate
        vat_rate, vat_conf = detect_vat_rate(text)
        if vat_rate:
            data.vat_rate = ExtractedField(
                value=vat_rate, confidence=vat_conf * 0.95, source="vat_rate_detection"
            )

        # Extract client information (pass sender VAT to exclude it)
        data.client = self._extract_client_info(text, sender_vat_id=sender_vat_id)

        # Extract line items and description
        data.line_items, data.description = self._extract_line_items(text)

        # Extract payment terms
        data.payment_terms = self._extract_payment_terms(text)

        return data

    def _clean_ocr_text(self, text: str) -> str:
        """Clean common OCR artifacts from text.

        Handles:
        - Unicode ligatures (fi, fl, ff, ffi, ffl)
        - Null characters
        - Common OCR misreadings

        Args:
            text: Raw OCR text

        Returns:
            Cleaned text
        """
        import re

        # Replace Unicode ligatures
        for ligature, replacement in self.LIGATURE_MAP.items():
            text = text.replace(ligature, replacement)

        # Remove null characters
        text = text.replace("\x00", "")

        # Fix common ligature artifacts where character is lost
        # "f l" -> "fl" when it looks like a broken ligature
        text = re.sub(r"\bf\s+l(?=[aeiouäöü])", "fl", text, flags=re.IGNORECASE)
        text = re.sub(r"\bf\s+i(?=[aeioulnrstdgckmb])", "fi", text, flags=re.IGNORECASE)

        # Handle cases where ligature became a different character or was dropped
        common_fl_words = [
            (r"Freiberu\s*icher", "Freiberuflicher"),
            (r"Au\s*age", "Auflage"),
            (r"emp\s*ehlen", "empfehlen"),
            (r"Emp\s*ehlung", "Empfehlung"),
            (r"ver\s*ichten", "verpflichten"),
            (r"P\s*icht", "Pflicht"),
        ]
        for pattern, replacement in common_fl_words:
            text = re.sub(pattern, replacement, text)

        # Fix common OCR misreadings
        replacements = [
            (r"\bl\b", "1"),  # Standalone 'l' often means '1' in numbers
            (r"O(?=\d)", "0"),  # 'O' before digit likely '0'
            (r"(?<=\d)O", "0"),  # 'O' after digit likely '0'
            (r"\bS(?=\d{2,})", "$"),  # 'S' before numbers might be '$'
            (r"(?<=\d),(?=\d{3})", ""),  # Remove thousand separators for parsing
        ]

        for pattern, replacement in replacements:
            # Only apply in numeric contexts
            text = re.sub(pattern, replacement, text)

        # Normalize whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text

    def _extract_client_info(self, text: str, sender_vat_id: str | None = None) -> ExtractedClientInfo:
        """Extract client/recipient information from OCR text.

        Uses multiple strategies to find client info:
        1. Look for company names by suffix (Ltd, GmbH, Inc, etc.)
        2. Find address blocks associated with client VAT ID
        3. Use recipient section headers if present
        4. Extract full address details (street, zip, city, country)

        Args:
            text: Cleaned OCR text
            sender_vat_id: User's own VAT ID to exclude from client detection

        Returns:
            ExtractedClientInfo with extracted fields
        """

        client = ExtractedClientInfo()
        sender_vat_normalized = sender_vat_id.replace(" ", "").upper() if sender_vat_id else None

        # Step 1: Find client VAT ID first (helps locate client address block)
        client_vat_id, client_vat_country = self._find_client_vat(text, sender_vat_normalized)
        if client_vat_id:
            client.vat_id = ExtractedField(
                value=client_vat_id,
                confidence=0.90,  # Slightly lower for OCR
                source="vat_id_exclusion"
            )

        # Step 2: Find client address block using VAT context or company suffixes
        client_block = self._find_client_address_block(text, client_vat_id, sender_vat_normalized)

        # Step 3: Extract company name - prioritize company suffix detection
        company_name = self._extract_company_name(text, client_block, sender_vat_normalized)
        if company_name:
            # Apply OCR confidence penalty
            client.name = ExtractedField(
                value=company_name["name"],
                confidence=company_name["confidence"] * 0.95,
                source=company_name["source"]
            )

        # Step 4: Extract full address from client block
        if client_block:
            address = self._extract_full_address(client_block, client_vat_country)
            if address.get("street"):
                client.street = ExtractedField(value=address["street"], confidence=0.80, source="client_block")
            if address.get("zip_code"):
                client.zip_code = ExtractedField(value=address["zip_code"], confidence=0.85, source="client_block")
            if address.get("city"):
                client.city = ExtractedField(value=address["city"], confidence=0.80, source="client_block")
            if address.get("country"):
                client.country = ExtractedField(value=address["country"], confidence=0.85, source="client_block")

            # Extract email and phone from client block
            email = self._extract_email(client_block)
            if email:
                client.email = ExtractedField(value=email, confidence=0.85, source="client_block")

            phone = self._extract_phone(client_block)
            if phone:
                client.phone = ExtractedField(value=phone, confidence=0.80, source="client_block")

        # Step 5: If no country yet, infer from VAT prefix
        if not client.country.value and client_vat_country:
            client.country = ExtractedField(value=client_vat_country, confidence=0.75, source="vat_prefix")

        return client

    def _find_client_vat(self, text: str, sender_vat_normalized: str | None) -> tuple[str | None, str | None]:
        """Find client VAT ID, excluding sender's VAT.

        Returns:
            Tuple of (vat_id, country_code) or (None, None)
        """
        import re

        # Find all VAT IDs in document
        vat_patterns = [
            r"VAT[\s\-]?(?:ID|No\.?|Number|number)?[\s:]*([A-Z]{2}\s?\d{9,12})",
            r"USt[\.\-]?(?:Id[\.\-]?)?(?:Nr\.?|Nummer)?[\s:]*([A-Z]{2}\s?\d{9,12})",
            r"\b([A-Z]{2}\s?\d{9,12})\b",
        ]

        all_vat_ids = []
        for pattern in vat_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            all_vat_ids.extend(matches)

        # Find first VAT that isn't sender's
        for vat in all_vat_ids:
            vat_clean = vat.replace(" ", "").upper()
            if vat_clean != sender_vat_normalized:
                country = vat_clean[:2] if len(vat_clean) >= 2 else None
                return vat_clean, country

        return None, None

    def _find_client_address_block(self, text: str, client_vat_id: str | None, sender_vat_normalized: str | None) -> str | None:
        """Find the text block containing client address info.

        Strategies:
        1. Find block near client VAT ID
        2. Find block with company suffix not near sender VAT
        3. Find labeled recipient section

        Returns:
            Text block containing client address, or None
        """
        import re

        lines = text.split("\n")

        # Strategy 1: Find lines near client VAT ID
        if client_vat_id:
            for i, line in enumerate(lines):
                if client_vat_id.replace(" ", "") in line.replace(" ", "").upper():
                    # Extract surrounding context (5 lines before, 3 after)
                    start = max(0, i - 5)
                    end = min(len(lines), i + 4)
                    block = "\n".join(lines[start:end])
                    return block

        # Strategy 2: Find block with company suffix (Ltd, Limited, GmbH, etc.)
        company_suffixes = [
            r"\bLtd\.?\b", r"\bLimited\b", r"\bInc\.?\b", r"\bIncorporated\b",
            r"\bLLC\b", r"\bCorp\.?\b", r"\bCorporation\b", r"\bPLC\b", r"\bLLP\b",
            r"\bGmbH\b", r"\bAG\b", r"\bUG\b", r"\be\.?K\.?\b", r"\bKG\b", r"\bOHG\b",
            r"\bB\.?V\.?\b", r"\bS\.?A\.?\b", r"\bS\.?L\.?\b",
        ]

        for i, line in enumerate(lines):
            for suffix_pattern in company_suffixes:
                if re.search(suffix_pattern, line, re.IGNORECASE):
                    # Check this isn't near sender's VAT
                    context_start = max(0, i - 3)
                    context_end = min(len(lines), i + 6)
                    block = "\n".join(lines[context_start:context_end])

                    # Skip if sender's VAT is in this block
                    if sender_vat_normalized and sender_vat_normalized in block.replace(" ", "").upper():
                        continue

                    return block

        # Strategy 3: Labeled recipient section
        recipient_patterns = [
            r"(?:Bill(?:ed)?\s*To|Invoice\s*To|Client|Customer|Sold\s*To)[\s:]*\n",
            r"(?:An|Kunde|Rechnungsempfänger|Empfänger)[\s:]*\n",
        ]

        for pattern in recipient_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = match.end()
                # Find end of section
                end_match = re.search(r"\n\n|\n(?:From|Invoice|Date|Amount|Total|Description)", text[start:], re.IGNORECASE)
                end = start + (end_match.start() if end_match else 200)
                section = text[start:end].strip()
                if len(section) > 10:
                    return section

        return None

    def _extract_company_name(self, text: str, client_block: str | None, sender_vat_normalized: str | None) -> dict | None:
        """Extract company name, prioritizing suffix-based detection.

        Returns:
            Dict with name, confidence, source or None
        """
        import re

        # Company suffix patterns - look for company names at start of line or after newline
        # Use non-greedy matching and limit to reasonable company name words (2-6 words before suffix)
        company_patterns = [
            # Full company names with suffixes - match from line start or capital letter
            (r"(?:^|\n)\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,5}\s+(?:Ltd\.?|Limited))", 0.95),
            (r"(?:^|\n)\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,5}\s+(?:Inc\.?|Incorporated))", 0.95),
            (r"(?:^|\n)\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,5}\s+(?:LLC|LLP|PLC|Corp\.?|Corporation))", 0.95),
            (r"(?:^|\n)\s*([A-ZÄÖÜ][A-Za-zÄÖÜäöüß]+(?:\s+[A-Za-zÄÖÜäöüß]+){0,5}\s+(?:GmbH|AG|UG|KG|OHG|e\.?K\.?))", 0.95),
            (r"(?:^|\n)\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,5}\s+(?:B\.?V\.?|S\.?A\.?|S\.?L\.?))", 0.9),
            # Fallback: more permissive but only capital-letter-starting words
            (r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}\s+(?:Ltd\.?|Limited|GmbH|Inc\.?|LLC))\b", 0.85),
        ]

        # First search in client block if available
        search_texts = []
        if client_block:
            search_texts.append((client_block, 1.0))  # Full confidence in client block
        search_texts.append((text, 0.85))  # Lower confidence in full text

        for search_text, conf_multiplier in search_texts:
            for pattern, base_confidence in company_patterns:
                match = re.search(pattern, search_text, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                    # Clean up the name
                    name = re.sub(r"^(?:To|Bill\s*To|Client|Customer)[\s:]*", "", name, flags=re.IGNORECASE).strip()
                    name = re.sub(r"\s+", " ", name)

                    # Skip if this looks like sender info (contains common sender keywords)
                    sender_keywords = ["freiberuflich", "freelance", "engineer", "consultant", "berater", "entwickler", "machine learning", "software engineer"]
                    if any(kw in name.lower() for kw in sender_keywords):
                        continue

                    # Skip very short names or ones that are just suffixes
                    if len(name) < 5:
                        continue

                    return {
                        "name": name,
                        "confidence": base_confidence * conf_multiplier,
                        "source": "company_suffix_detection"
                    }

        # Fallback: Try labeled patterns
        if client_block:
            value, conf, pattern = extract_with_patterns(client_block, CLIENT_NAME_PATTERNS)
            if value:
                name = re.sub(r"^(?:To|Bill\s*To|Client|Customer)[\s:]*", "", value, flags=re.IGNORECASE).strip()
                if len(name) > 3:
                    return {"name": name, "confidence": conf * 0.8, "source": pattern}

        return None

    def _extract_full_address(self, block: str, country_hint: str | None = None) -> dict:
        """Extract full address components from a text block.

        Args:
            block: Text block containing address
            country_hint: Country code hint (e.g., from VAT prefix)

        Returns:
            Dict with street, zip_code, city, country
        """
        import re

        result = {}

        # Detect country first (helps with format detection)
        country = country_hint
        for pattern, code, confidence in COUNTRY_PATTERNS:
            if re.search(pattern, block, re.IGNORECASE):
                country = code
                result["country"] = code
                break

        # Extract postal code (format depends on country)
        for pattern, conf, country_code in POSTAL_CODE_PATTERNS:
            match = re.search(pattern, block, re.IGNORECASE)
            if match:
                result["zip_code"] = match.group(1)
                if not result.get("country") and country_code:
                    result["country"] = country_code
                    country = country_code
                break

        # Extract street address
        for pattern, conf in STREET_PATTERNS:
            match = re.search(pattern, block, re.IGNORECASE)
            if match:
                street = match.group(1).strip()
                # Clean up
                street = re.sub(r"\s+", " ", street)
                if len(street) > 5:
                    result["street"] = street
                    break

        # Extract city - strategy depends on what we found
        if result.get("zip_code"):
            # Look for city near postal code
            zip_code = result["zip_code"]
            lines = block.split("\n")
            for line in lines:
                if zip_code in line:
                    # City might be after postal code on same line
                    after_zip = re.search(rf"{re.escape(zip_code)}\s+([A-Za-z][A-Za-z\s\-]+)", line)
                    if after_zip:
                        city = after_zip.group(1).strip()
                        # Remove country names from city
                        city = re.sub(r"\s*(United Kingdom|UK|Germany|Deutschland|France|USA|US).*$", "", city, flags=re.IGNORECASE)
                        if city and len(city) > 2:
                            result["city"] = city
                            break

        # If no city found yet, look for common city patterns
        if not result.get("city"):
            lines = block.split("\n")
            for line in lines:
                line = line.strip()
                # Skip lines with company suffixes, VAT IDs, postal codes, numbers only
                if len(line) > 2 and len(line) < 50:
                    if not re.search(r"Ltd|Limited|GmbH|VAT|[A-Z]{2}\d{9}|\d{5}", line, re.IGNORECASE):
                        if re.match(r"^[A-Za-z][A-Za-z\s\-]+$", line):
                            # This could be a city name
                            result["city"] = line
                            break

        return result

    def _extract_email(self, block: str) -> str | None:
        """Extract email address from text block."""
        import re

        for pattern, conf in EMAIL_PATTERNS:
            match = re.search(pattern, block, re.IGNORECASE)
            if match:
                return match.group(1).lower()
        return None

    def _extract_phone(self, block: str) -> str | None:
        """Extract phone number from text block."""
        import re

        for pattern, conf in PHONE_PATTERNS:
            match = re.search(pattern, block, re.IGNORECASE)
            if match:
                phone = match.group(1).strip()
                # Normalize: remove extra spaces
                phone = re.sub(r"\s+", " ", phone)
                return phone
        return None

    def _parse_amount(self, amount_str: str) -> "Decimal | None":
        """Parse amount string handling various formats.

        Handles:
        - €10,050.00 (comma as thousand separator, period as decimal)
        - 10.050,00 € (period as thousand separator, comma as decimal - German)
        - 50.00 (simple decimal)

        Args:
            amount_str: Raw amount string

        Returns:
            Decimal or None if parsing fails
        """
        from decimal import Decimal, InvalidOperation

        if not amount_str:
            return None

        # Remove currency symbols and whitespace
        cleaned = amount_str.strip()
        cleaned = cleaned.replace("€", "").replace("$", "").replace("£", "").strip()

        if not cleaned:
            return None

        try:
            # Detect format based on position of comma and period
            has_comma = "," in cleaned
            has_period = "." in cleaned

            if has_comma and has_period:
                # Both present - determine which is decimal separator
                comma_pos = cleaned.rfind(",")
                period_pos = cleaned.rfind(".")

                if comma_pos > period_pos:
                    # German format: 10.050,00 - comma is decimal
                    cleaned = cleaned.replace(".", "").replace(",", ".")
                else:
                    # US/UK format: 10,050.00 - period is decimal
                    cleaned = cleaned.replace(",", "")
            elif has_comma and not has_period:
                # Could be German decimal (50,00) or thousand separator (1,000)
                # If 2 digits after comma, treat as decimal
                parts = cleaned.split(",")
                if len(parts) == 2 and len(parts[1]) == 2:
                    cleaned = cleaned.replace(",", ".")
                else:
                    cleaned = cleaned.replace(",", "")
            # If only period, it's already in correct format

            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None

    def _extract_payment_terms(self, text: str) -> ExtractedField:
        """Extract payment terms from invoice.

        Looks for patterns like:
        - "Payment terms: 14 days"
        - "Net 30"
        - "Due within 30 days"
        - "Zahlungsziel: 14 Tage"

        Args:
            text: Cleaned OCR text

        Returns:
            ExtractedField with payment terms
        """
        import re

        payment_patterns = [
            # English patterns
            (r"Payment\s*terms?[\s:]+(\d+\s*days?)", 0.95),
            (r"Payment\s*terms?[\s:]+([Nn]et\s*\d+)", 0.95),
            (r"Terms?[\s:]+(\d+\s*days?)", 0.85),
            (r"Terms?[\s:]+([Nn]et\s*\d+)", 0.85),
            (r"(?:Due|Payable)\s+(?:within|in)\s+(\d+\s*days?)", 0.8),
            (r"([Nn]et\s*\d+)\s*(?:days?)?", 0.7),
            # German patterns
            (r"Zahlungs(?:ziel|frist|bedingung(?:en)?)[\s:]+(\d+\s*Tage?)", 0.95),
            (r"Zahlbar\s+(?:innerhalb|binnen)\s+(\d+\s*Tage?n?)", 0.85),
            (r"(?:Innerhalb|Binnen)\s+(\d+\s*Tage?n?)", 0.7),
        ]

        for pattern, confidence in payment_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                terms = match.group(1).strip()
                # Normalize
                terms = re.sub(r"\s+", " ", terms)
                # Apply OCR confidence penalty
                return ExtractedField(value=terms, confidence=confidence * 0.95, source=pattern)

        return ExtractedField()

    def _extract_line_items(self, text: str) -> tuple[list, ExtractedField]:
        """Extract invoice line items with structured data.

        Parses the line items table to extract:
        - Description
        - Date
        - Quantity
        - Unit (h, Stk, etc.)
        - Unit price
        - VAT %
        - Total

        Args:
            text: Cleaned OCR text

        Returns:
            Tuple of (list of ExtractedLineItem, ExtractedField with combined description)
        """
        import re

        from src.core.extraction.models import ExtractedLineItem

        # Clean null characters and normalize whitespace
        text = text.replace("\x00", "")

        lines = text.split("\n")
        line_items = []
        descriptions = []

        # Strategy 1: Find "Description" header and extract lines until "Total"
        in_items_section = False
        pending_description = None

        for i, line in enumerate(lines):
            line_clean = line.strip().replace("\x00", "")

            # Detect start of line items section
            if re.match(r"^Description\s+Date\s+Qty", line_clean, re.IGNORECASE):
                in_items_section = True
                continue

            # German table header
            if re.match(
                r"^(?:Beschreibung|Leistung|Position)\s+(?:Datum|Menge|Anzahl)",
                line_clean,
                re.IGNORECASE
            ):
                in_items_section = True
                continue

            # Detect end of line items section
            if in_items_section and re.match(
                r"^(?:Total|Summe|Subtotal|Zwischensumme|Netto|Brutto)",
                line_clean,
                re.IGNORECASE
            ):
                break

            if in_items_section and line_clean:
                # Try to parse line item using flexible pattern
                # Format: Description Date Qty Unit €Price VAT% €Total
                # Example: "Claude Max 5x Subscription 16.12.2025 1.00 Stk. €90.00 0.00% €90.00"

                # Pattern to extract the numeric tail: Date Qty Unit €Price VAT% €Total
                tail_pattern = re.search(
                    r"(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s+"  # Date
                    r"([\d.,]+)\s+"                         # Quantity
                    r"([A-Za-z.]+)\s+"                      # Unit
                    r"[€$£]?([\d.,]+)\s+"                   # Unit price
                    r"([\d.,]+)\s*%\s+"                     # VAT %
                    r"[€$£]?([\d.,]+)\s*[€$£]?\s*$",        # Total
                    line_clean
                )

                if tail_pattern:
                    # Everything before the date is the description
                    date_start = tail_pattern.start()
                    desc = line_clean[:date_start].strip()

                    # If we have a pending multi-line description, prepend it
                    if pending_description:
                        desc = pending_description + " " + desc
                        pending_description = None

                    date_str = tail_pattern.group(1)
                    qty = self._parse_amount(tail_pattern.group(2))
                    unit = tail_pattern.group(3).rstrip(".")  # Remove trailing period
                    unit_price = self._parse_amount(tail_pattern.group(4))
                    vat_pct = self._parse_amount(tail_pattern.group(5))
                    total = self._parse_amount(tail_pattern.group(6))

                    # Parse the date
                    from datetime import date as date_type
                    service_date = None
                    try:
                        parts = re.split(r"[./]", date_str)
                        if len(parts) == 3:
                            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                            if year < 100:
                                year += 2000
                            service_date = date_type(year, month, day)
                    except (ValueError, IndexError):
                        pass

                    # Convert VAT percentage to rate string
                    vat_rate = "0.19"  # Default
                    if vat_pct is not None:
                        vat_float = float(vat_pct)
                        if vat_float == 0:
                            vat_rate = "0.00"
                        elif vat_float <= 7.5:
                            vat_rate = "0.07"
                        else:
                            vat_rate = "0.19"

                    if qty is not None and total is not None:
                        # Look ahead for description continuation on next line
                        # (some PDFs put multi-line descriptions after the numbers)
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip().replace("\x00", "")
                            # Check if next line is text continuation (no date pattern)
                            if next_line and len(next_line) > 3:
                                has_date = re.search(
                                    r"\d{1,2}[./]\d{1,2}[./]\d{2,4}",
                                    next_line
                                )
                                is_end = re.match(
                                    r"^(?:Total|Summe|Subtotal)",
                                    next_line,
                                    re.IGNORECASE
                                )
                                is_numbers_only = re.match(
                                    r"^[\d€$£.,\s%]+$",
                                    next_line
                                )
                                if not has_date and not is_end and not is_numbers_only:
                                    # This is a description continuation
                                    desc = desc + " " + next_line
                                    # Mark it as consumed so we skip it
                                    lines[i + 1] = ""

                        line_items.append(ExtractedLineItem(
                            description=desc,
                            service_date=service_date,
                            quantity=qty,
                            unit=unit or "Stk.",
                            unit_price=unit_price,
                            vat_rate=vat_rate,
                            total=total,
                            confidence=0.85  # Slightly lower for OCR
                        ))
                        descriptions.append(desc)
                        continue

                # Try simpler pattern: just look for date and total at end
                simple_pattern = re.search(
                    r"(\d{1,2}[./]\d{1,2}[./]\d{2,4}).+?"  # Date somewhere
                    r"[€$£]?([\d.,]+)\s*[€$£]?\s*$",       # Total at end
                    line_clean
                )

                if simple_pattern:
                    date_start = simple_pattern.start()
                    desc = line_clean[:date_start].strip()

                    if pending_description:
                        desc = pending_description + " " + desc
                        pending_description = None

                    # Parse the date from simple pattern
                    from datetime import date as date_type
                    simple_date_str = simple_pattern.group(1)
                    simple_service_date = None
                    try:
                        parts = re.split(r"[./]", simple_date_str)
                        if len(parts) == 3:
                            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                            if year < 100:
                                year += 2000
                            simple_service_date = date_type(year, month, day)
                    except (ValueError, IndexError):
                        pass

                    total = self._parse_amount(simple_pattern.group(2))

                    if desc and len(desc) > 3:
                        line_items.append(ExtractedLineItem(
                            description=desc,
                            service_date=simple_service_date,
                            total=total,
                            confidence=0.70  # Lower for OCR + simple match
                        ))
                        descriptions.append(desc)
                        continue

                # Line without date pattern - might be description continuation
                if not re.match(r"^[\d€$£.,\s%]+$", line_clean):
                    if len(line_clean) > 3 and not re.match(r"^\d", line_clean):
                        # This could be start/continuation of multi-line description
                        if pending_description:
                            pending_description += " " + line_clean
                        else:
                            pending_description = line_clean

        # Build description field from extracted items
        if descriptions:
            if len(descriptions) == 1:
                desc_text = descriptions[0]
            else:
                desc_text = "; ".join(descriptions)

            desc_text = re.sub(r"\s+", " ", desc_text).strip()
            if len(desc_text) > 500:
                desc_text = desc_text[:497] + "..."

            # Apply OCR confidence penalty
            description_field = ExtractedField(
                value=desc_text, confidence=0.85, source="line_items_table"
            )
            return line_items, description_field

        # Strategy 2: Fallback patterns for description only
        description_patterns = [
            (r"(?:For|Regarding|Re|Subject)[\s:]+(.+?)(?:\n\n|\nDate|\nInvoice)", 0.70),
            (r"(?:Betreff|Für)[\s:]+(.+?)(?:\n\n|\nDatum|\nRechnung)", 0.70),
        ]

        for pattern, confidence in description_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                desc = match.group(1).strip()
                desc = " ".join(desc.split())
                if len(desc) > 500:
                    desc = desc[:497] + "..."
                if len(desc) > 10:
                    return [], ExtractedField(value=desc, confidence=confidence, source=pattern)

        # Strategy 3: Fallback - find substantial text
        for line in lines:
            line = line.strip()
            if len(line) > 30 and not any(
                skip in line.lower()
                for skip in [
                    "invoice", "date", "total", "amount", "vat", "tax",
                    "bill to", "from:", "address", "phone", "email", "iban",
                    "rechnung", "datum", "summe", "betrag", "mwst", "bank",
                    "payment", "due", "terms", "number", "united kingdom",
                    "germany", "parkway", "street", "limited", "gmbh",
                ]
            ):
                return [], ExtractedField(value=line, confidence=0.35, source="fallback")

        return [], ExtractedField()


def is_ocr_available() -> bool:
    """Check if OCR dependencies are available."""
    return OCR_AVAILABLE


# Only create singleton if OCR is available
ocr_extractor: OCRExtractor | None = None
if OCR_AVAILABLE:
    try:
        ocr_extractor = OCRExtractor()
    except Exception:
        pass  # OCR not available (tesseract not installed)
