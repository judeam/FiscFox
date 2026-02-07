"""Expense receipt OCR using PaddleOCR-VL.

Provides text extraction from receipt images with German language support.
Falls back to pytesseract if PaddleOCR is not available.
"""

from __future__ import annotations

import io
import logging
import re
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from src.core.extraction.expense_models import (
    ExpenseExtractionResult,
    ExtractedDateField,
    ExtractedDecimalField,
    ExtractedExpenseData,
    ExtractedField,
)

if TYPE_CHECKING:
    from paddleocr import PaddleOCR

logger = logging.getLogger(__name__)


# =============================================================================
# PaddleOCR Availability Check
# =============================================================================


def is_paddleocr_available() -> bool:
    """Check if PaddleOCR is installed and working."""
    try:
        from paddleocr import PaddleOCR  # noqa: F401

        return True
    except ImportError:
        return False


def is_tesseract_available() -> bool:
    """Check if pytesseract is installed and tesseract binary is available."""
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


# =============================================================================
# German Receipt Patterns
# =============================================================================


# Date patterns common in German receipts
DATE_PATTERNS = [
    # DD.MM.YYYY (most common German format)
    r"(\d{1,2})[./](\d{1,2})[./](\d{4})",
    # DD.MM.YY
    r"(\d{1,2})[./](\d{1,2})[./](\d{2})\b",
    # YYYY-MM-DD (ISO)
    r"(\d{4})-(\d{1,2})-(\d{1,2})",
]

# Amount patterns for German currency (comma as decimal separator)
AMOUNT_PATTERNS = [
    # EUR prefix: EUR 19,99 or EUR 19.99
    r"EUR\s*(\d+[,.]?\d*)",
    # € symbol: €19,99 or € 19.99
    r"€\s*(\d+[,.]?\d*)",
    # Summe/Gesamt/Total patterns
    r"(?:Summe|Gesamt|Total|SUMME|TOTAL|Brutto|BRUTTO|Endbetrag|Zu zahlen)[:\s]*(\d+[,.]?\d*)",
    # Amount with EUR suffix: 19,99 EUR
    r"(\d+[,.]?\d*)\s*(?:EUR|€)",
    # German format: 19,99
    r"\b(\d{1,6},\d{2})\b",
    # International format: 19.99
    r"\b(\d{1,6}\.\d{2})\b",
]

# VAT patterns
VAT_PATTERNS = [
    # MwSt./USt. with rate
    r"(?:MwSt|USt|Mwst|Ust|MWST|UST)[.:]?\s*(\d{1,2})\s*%",
    # Percentage mentions
    r"(\d{1,2})\s*%\s*(?:MwSt|USt|VAT|Steuer)",
    # Explicit rates
    r"(?:Steuersatz|VAT Rate)[:\s]*(\d{1,2})\s*%",
]

# Common German receipt keywords for vendor detection
VENDOR_KEYWORDS = [
    "GmbH", "AG", "KG", "OHG", "e.K.", "UG", "GbR",
    "Filiale", "Store", "Shop", "Markt", "Center",
]


# =============================================================================
# Expense OCR Extractor
# =============================================================================


class ExpenseOCRExtractor:
    """Extract expense data from receipt images using PaddleOCR.

    Features:
    - PaddleOCR-VL for accurate German text recognition
    - Fallback to pytesseract if PaddleOCR unavailable
    - Pattern-based extraction for amounts, dates, VAT
    - Confidence scoring for all extracted fields
    """

    def __init__(
        self,
        use_gpu: bool = False,
        lang: str = "de",
    ):
        """Initialize the expense OCR extractor.

        Args:
            use_gpu: Whether to use GPU acceleration
            lang: Language for OCR (de, en, etc.)
        """
        self.use_gpu = use_gpu
        self.lang = lang
        self._paddle_ocr: PaddleOCR | None = None
        self._use_paddleocr = is_paddleocr_available()
        self._use_tesseract = is_tesseract_available()

        if not self._use_paddleocr and not self._use_tesseract:
            logger.warning(
                "No OCR engine available. Install paddleocr or pytesseract."
            )

    @property
    def paddle_ocr(self) -> PaddleOCR | None:
        """Lazy-load PaddleOCR instance."""
        if self._paddle_ocr is None and self._use_paddleocr:
            try:
                from paddleocr import PaddleOCR

                self._paddle_ocr = PaddleOCR(
                    use_angle_cls=True,  # Detect rotated text
                    lang="german" if self.lang == "de" else self.lang,
                    use_gpu=self.use_gpu,
                    show_log=False,
                )
                logger.info("PaddleOCR initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize PaddleOCR: {e}")
                self._use_paddleocr = False
        return self._paddle_ocr

    def extract(self, image_path: str | Path) -> ExpenseExtractionResult:
        """Extract expense data from a receipt image file.

        Args:
            image_path: Path to the image file

        Returns:
            ExpenseExtractionResult with extracted data
        """
        image_path = Path(image_path)

        if not image_path.exists():
            return ExpenseExtractionResult(
                success=False,
                errors=[f"File not found: {image_path}"],
            )

        try:
            with Image.open(image_path) as img:
                return self._extract_from_image(img)
        except Exception as e:
            logger.error(f"Failed to open image: {e}")
            return ExpenseExtractionResult(
                success=False,
                errors=[f"Failed to open image: {e}"],
            )

    def extract_from_bytes(self, image_bytes: bytes) -> ExpenseExtractionResult:
        """Extract expense data from image bytes.

        Args:
            image_bytes: Image file contents as bytes

        Returns:
            ExpenseExtractionResult with extracted data
        """
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                return self._extract_from_image(img)
        except Exception as e:
            logger.error(f"Failed to process image bytes: {e}")
            return ExpenseExtractionResult(
                success=False,
                errors=[f"Failed to process image: {e}"],
            )

    def _extract_from_image(self, img: Image.Image) -> ExpenseExtractionResult:
        """Extract expense data from PIL Image.

        Args:
            img: PIL Image object

        Returns:
            ExpenseExtractionResult with extracted data
        """
        start_time = time.time()

        # Run OCR
        raw_text, ocr_results = self._run_ocr(img)

        if not raw_text:
            return ExpenseExtractionResult(
                success=False,
                errors=["No text detected in image"],
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

        # Extract structured data from OCR text
        extracted_data = self._parse_ocr_results(raw_text, ocr_results)
        extracted_data.raw_text = raw_text
        extracted_data.overall_confidence = extracted_data.calculate_overall_confidence()

        processing_time = int((time.time() - start_time) * 1000)
        extracted_data.processing_time_ms = processing_time

        # Determine success based on minimum data
        success = extracted_data.has_minimum_data

        warnings = []
        if not extracted_data.receipt_date.value:
            warnings.append("Could not extract receipt date")
        if not extracted_data.vat_rate.value:
            warnings.append("VAT rate not detected, defaulting to 19%")

        return ExpenseExtractionResult(
            success=success,
            data=extracted_data,
            warnings=warnings,
            processing_time_ms=processing_time,
        )

    def _run_ocr(self, img: Image.Image) -> tuple[str, list[Any]]:
        """Run OCR on the image.

        Args:
            img: PIL Image object

        Returns:
            Tuple of (raw_text, structured_results)
        """
        # Try PaddleOCR first
        if self._use_paddleocr and self.paddle_ocr is not None:
            return self._run_paddleocr(img)

        # Fall back to tesseract
        if self._use_tesseract:
            return self._run_tesseract(img)

        return "", []

    def _run_paddleocr(self, img: Image.Image) -> tuple[str, list[Any]]:
        """Run PaddleOCR on the image.

        Args:
            img: PIL Image object

        Returns:
            Tuple of (raw_text, ocr_results)
        """
        try:
            import numpy as np

            # Convert PIL to numpy array
            img_array = np.array(img.convert("RGB"))

            # Run PaddleOCR
            result = self.paddle_ocr.ocr(img_array, cls=True)

            if not result or not result[0]:
                return "", []

            # Extract text and build structured results
            lines = []
            ocr_results = []

            for line in result[0]:
                if line and len(line) >= 2:
                    box = line[0]  # Bounding box coordinates
                    text_info = line[1]  # (text, confidence)
                    text = text_info[0]
                    confidence = text_info[1]

                    lines.append(text)
                    ocr_results.append({
                        "text": text,
                        "confidence": confidence,
                        "box": box,
                    })

            raw_text = "\n".join(lines)
            return raw_text, ocr_results

        except Exception as e:
            logger.error(f"PaddleOCR failed: {e}")
            # Fall back to tesseract
            if self._use_tesseract:
                return self._run_tesseract(img)
            return "", []

    def _run_tesseract(self, img: Image.Image) -> tuple[str, list[Any]]:
        """Run Tesseract OCR on the image.

        Args:
            img: PIL Image object

        Returns:
            Tuple of (raw_text, empty_results)
        """
        try:
            import pytesseract

            # Configure for German
            config = "--oem 3 --psm 6"
            lang = "deu" if self.lang == "de" else self.lang

            raw_text = pytesseract.image_to_string(
                img, lang=lang, config=config
            )
            return raw_text, []

        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            return "", []

    def _parse_ocr_results(
        self,
        raw_text: str,
        ocr_results: list[Any],
    ) -> ExtractedExpenseData:
        """Parse OCR results into structured expense data.

        Args:
            raw_text: Full OCR text
            ocr_results: Structured OCR results with confidence

        Returns:
            ExtractedExpenseData with parsed fields
        """
        data = ExtractedExpenseData()
        data.ocr_engine = "paddleocr" if ocr_results else "tesseract"

        # Extract vendor (usually first line or line with company suffix)
        data.vendor = self._extract_vendor(raw_text, ocr_results)

        # Extract date
        data.receipt_date = self._extract_date(raw_text)

        # Extract amounts
        amounts = self._extract_amounts(raw_text)
        if amounts:
            # Largest amount is usually the total
            data.amount_gross = amounts[0]

            # If we have multiple amounts, smaller ones might be net/vat
            if len(amounts) > 1:
                # Try to identify VAT amount
                for amt in amounts[1:]:
                    if amt.value and data.amount_gross.value:
                        ratio = amt.value / data.amount_gross.value
                        # VAT is typically 7-19% of gross
                        if Decimal("0.05") < ratio < Decimal("0.20"):
                            data.vat_amount = amt
                            break

        # Extract VAT rate
        data.vat_rate = self._extract_vat_rate(raw_text)

        # Extract description (combine line items or use middle section)
        data.description = self._extract_description(raw_text, ocr_results)

        # Store line items if detected
        data.line_items = self._extract_line_items(raw_text)

        return data

    def _extract_vendor(
        self,
        raw_text: str,
        ocr_results: list[Any],
    ) -> ExtractedField:
        """Extract vendor name from receipt.

        Vendor is typically in the first few lines, often contains
        company suffixes like GmbH, AG, etc.
        """
        lines = raw_text.strip().split("\n")[:5]  # First 5 lines

        # Look for lines with company keywords
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue

            for keyword in VENDOR_KEYWORDS:
                if keyword.lower() in line.lower():
                    confidence = 0.9 if ocr_results else 0.7
                    return ExtractedField(
                        value=line,
                        confidence=confidence,
                        source="keyword_match",
                    )

        # Fall back to first non-empty line
        for line in lines:
            line = line.strip()
            if line and len(line) >= 3:
                return ExtractedField(
                    value=line,
                    confidence=0.5,
                    source="first_line",
                )

        return ExtractedField()

    def _extract_date(self, raw_text: str) -> ExtractedDateField:
        """Extract date from receipt text."""
        for pattern in DATE_PATTERNS:
            matches = re.findall(pattern, raw_text)
            for match in matches:
                try:
                    if len(match) == 3:
                        if len(match[0]) == 4:  # YYYY-MM-DD format
                            year, month, day = int(match[0]), int(match[1]), int(match[2])
                        elif len(match[2]) == 2:  # DD.MM.YY format
                            day, month, year = int(match[0]), int(match[1]), int(match[2])
                            year = 2000 + year if year < 50 else 1900 + year
                        else:  # DD.MM.YYYY format
                            day, month, year = int(match[0]), int(match[1]), int(match[2])

                        parsed_date = date(year, month, day)

                        # Sanity check: date should be reasonable
                        today = date.today()
                        if parsed_date <= today and parsed_date.year >= 2000:
                            return ExtractedDateField(
                                value=parsed_date,
                                confidence=0.85,
                                source="pattern_match",
                                raw_value="-".join(str(x) for x in match),
                            )
                except (ValueError, TypeError):
                    continue

        return ExtractedDateField()

    def _extract_amounts(self, raw_text: str) -> list[ExtractedDecimalField]:
        """Extract monetary amounts from receipt text."""
        amounts: list[ExtractedDecimalField] = []
        seen_values: set[str] = set()

        for pattern in AMOUNT_PATTERNS:
            matches = re.findall(pattern, raw_text, re.IGNORECASE)
            for match in matches:
                try:
                    # Normalize decimal separator
                    amount_str = match.replace(",", ".")

                    # Skip if already seen
                    if amount_str in seen_values:
                        continue
                    seen_values.add(amount_str)

                    # Parse as Decimal
                    amount = Decimal(amount_str).quantize(Decimal("0.01"))

                    # Skip unreasonable amounts
                    if amount <= 0 or amount > Decimal("100000"):
                        continue

                    amounts.append(ExtractedDecimalField(
                        value=amount,
                        confidence=0.8,
                        source="pattern_match",
                        raw_value=match,
                    ))

                except (InvalidOperation, ValueError):
                    continue

        # Sort by value descending (largest first = total)
        amounts.sort(key=lambda x: x.value or Decimal("0"), reverse=True)
        return amounts

    def _extract_vat_rate(self, raw_text: str) -> ExtractedField:
        """Extract VAT rate from receipt text."""
        for pattern in VAT_PATTERNS:
            matches = re.findall(pattern, raw_text, re.IGNORECASE)
            for match in matches:
                try:
                    rate = int(match)
                    if rate in (7, 19, 0):
                        return ExtractedField(
                            value=f"0.{rate:02d}" if rate > 0 else "0.00",
                            confidence=0.9,
                            source="pattern_match",
                        )
                except (ValueError, TypeError):
                    continue

        # Check for keywords indicating reduced rate
        if any(kw in raw_text.lower() for kw in ["erm.", "ermäßigt", "7%", "7 %"]):
            return ExtractedField(
                value="0.07",
                confidence=0.7,
                source="keyword_inference",
            )

        return ExtractedField()

    def _extract_description(
        self,
        raw_text: str,
        ocr_results: list[Any],
    ) -> ExtractedField:
        """Extract a description from receipt items."""
        lines = raw_text.strip().split("\n")

        # Skip header (first 2-3 lines) and footer (last 3-4 lines)
        middle_lines = lines[2:-3] if len(lines) > 6 else lines

        # Filter out amount-only lines and very short lines
        item_lines = []
        for line in middle_lines:
            line = line.strip()
            # Skip lines that are just numbers/amounts
            if re.match(r"^[\d.,\s€EUR]+$", line):
                continue
            # Skip very short lines
            if len(line) < 3:
                continue
            item_lines.append(line)

        if item_lines:
            # Join first few item lines as description
            description = "; ".join(item_lines[:3])
            return ExtractedField(
                value=description[:200],  # Limit length
                confidence=0.6,
                source="line_extraction",
            )

        return ExtractedField()

    def _extract_line_items(self, raw_text: str) -> list[str]:
        """Extract individual line items from receipt."""
        items = []
        lines = raw_text.strip().split("\n")

        for line in lines:
            line = line.strip()
            # Look for lines that have both text and amount
            if re.search(r"\d+[,.]?\d*\s*(?:€|EUR)?$", line):
                # Remove the amount part for cleaner item description
                item = re.sub(r"\s*\d+[,.]?\d*\s*(?:€|EUR)?$", "", line).strip()
                if item and len(item) >= 3:
                    items.append(item)

        return items[:10]  # Limit to 10 items

    def get_available_engines(self) -> list[str]:
        """Get list of available OCR engines.

        Returns:
            List of engine names
        """
        engines = []
        if self._use_paddleocr:
            engines.append("paddleocr")
        if self._use_tesseract:
            engines.append("tesseract")
        return engines


# =============================================================================
# Singleton Instance
# =============================================================================


_extractor: ExpenseOCRExtractor | None = None


def get_expense_ocr_extractor() -> ExpenseOCRExtractor:
    """Get or create the expense OCR extractor singleton."""
    global _extractor
    if _extractor is None:
        _extractor = ExpenseOCRExtractor()
    return _extractor


def extract_expense_from_image(
    image_path: str | Path,
) -> ExpenseExtractionResult:
    """Convenience function to extract expense data from image.

    Args:
        image_path: Path to image file

    Returns:
        ExpenseExtractionResult with extracted data
    """
    return get_expense_ocr_extractor().extract(image_path)


def extract_expense_from_bytes(
    image_bytes: bytes,
) -> ExpenseExtractionResult:
    """Convenience function to extract expense data from image bytes.

    Args:
        image_bytes: Image file contents

    Returns:
        ExpenseExtractionResult with extracted data
    """
    return get_expense_ocr_extractor().extract_from_bytes(image_bytes)
