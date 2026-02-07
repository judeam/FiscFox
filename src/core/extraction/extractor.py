"""Main invoice extractor with intelligent routing.

Routes extraction to the most appropriate method based on PDF content:
- Digital PDFs → Text extraction (fast, accurate)
- Scanned PDFs → OCR extraction (slower, handles images)
- Future: AI extraction for complex layouts
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.core.extraction.models import (
    ExtractionMethod,
    ExtractionResult,
)
from src.core.extraction.text_extractor import TextExtractor

if TYPE_CHECKING:
    from src.core.extraction.ocr_extractor import OCRExtractor


class InvoiceExtractor:
    """Main invoice extractor with automatic method selection.

    Provides a tiered extraction approach:
    1. Try text extraction first (fast, works for digital PDFs)
    2. Fall back to OCR if text extraction yields poor results
    3. Future: AI extraction for complex/ambiguous cases
    """

    # Confidence threshold below which we try OCR
    OCR_FALLBACK_THRESHOLD = 0.4

    # Minimum text characters to consider text extraction successful
    MIN_TEXT_CHARS = 50

    def __init__(self, enable_ocr: bool = True) -> None:
        """Initialize the invoice extractor.

        Args:
            enable_ocr: Whether to enable OCR fallback (requires tesseract)
        """
        self.text_extractor = TextExtractor()
        self.enable_ocr = enable_ocr
        self._ocr_extractor: OCRExtractor | None = None

    @property
    def ocr_extractor(self) -> OCRExtractor | None:
        """Lazy-load OCR extractor only when needed."""
        if self._ocr_extractor is None and self.enable_ocr:
            try:
                from src.core.extraction.ocr_extractor import OCRExtractor, is_ocr_available

                if is_ocr_available():
                    self._ocr_extractor = OCRExtractor()
            except ImportError:
                pass
        return self._ocr_extractor

    def extract(self, pdf_path: str | Path, force_ocr: bool = False) -> ExtractionResult:
        """Extract invoice data from a PDF file.

        Automatically selects the best extraction method based on content.

        Args:
            pdf_path: Path to the PDF file
            force_ocr: If True, skip text extraction and use OCR directly

        Returns:
            ExtractionResult with extracted data
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            return ExtractionResult(
                success=False,
                errors=[f"File not found: {pdf_path}"],
                method_used=ExtractionMethod.TEXT,
            )

        # If OCR is forced, skip text extraction
        if force_ocr:
            return self._try_ocr(pdf_path)

        # Step 1: Try text extraction first
        text_result = self.text_extractor.extract(pdf_path)

        # Check if text extraction was successful and useful
        if self._is_extraction_adequate(text_result):
            return text_result

        # Step 2: Fall back to OCR if available
        if self.enable_ocr and self.ocr_extractor is not None:
            ocr_result = self.ocr_extractor.extract(pdf_path)

            # Return the better result
            return self._choose_best_result(text_result, ocr_result)

        # No OCR available, return text result with warning
        if text_result.success and text_result.data:
            text_result.warnings.append(
                "Text extraction had low confidence. OCR not available for fallback."
            )

        return text_result

    def extract_from_bytes(self, pdf_bytes: bytes, force_ocr: bool = False, sender_vat_id: str | None = None) -> ExtractionResult:
        """Extract invoice data from PDF bytes.

        Args:
            pdf_bytes: PDF file contents as bytes
            force_ocr: If True, skip text extraction and use OCR directly
            sender_vat_id: User's own VAT ID to exclude from client detection

        Returns:
            ExtractionResult with extracted data
        """
        # If OCR is forced, skip text extraction
        if force_ocr:
            return self._try_ocr_bytes(pdf_bytes, sender_vat_id=sender_vat_id)

        # Step 1: Try text extraction first
        text_result = self.text_extractor.extract_from_bytes(pdf_bytes, sender_vat_id=sender_vat_id)

        # Check if text extraction was successful and useful
        if self._is_extraction_adequate(text_result):
            return text_result

        # Step 2: Fall back to OCR if available
        if self.enable_ocr and self.ocr_extractor is not None:
            ocr_result = self.ocr_extractor.extract_from_bytes(pdf_bytes)

            # Return the better result
            return self._choose_best_result(text_result, ocr_result)

        # No OCR available, return text result with warning
        if text_result.success and text_result.data:
            text_result.warnings.append(
                "Text extraction had low confidence. OCR not available for fallback."
            )

        return text_result

    def _is_extraction_adequate(self, result: ExtractionResult) -> bool:
        """Check if extraction result is adequate or needs OCR fallback.

        Args:
            result: ExtractionResult to evaluate

        Returns:
            True if extraction is adequate, False if OCR should be tried
        """
        if not result.success:
            return False

        if result.data is None:
            return False

        # Check raw text length
        if result.data.raw_text and len(result.data.raw_text.strip()) < self.MIN_TEXT_CHARS:
            return False

        # Check confidence threshold
        if result.data.overall_confidence < self.OCR_FALLBACK_THRESHOLD:
            return False

        # Check if minimum data was extracted
        if not result.data.has_minimum_data:
            return False

        return True

    def _try_ocr(self, pdf_path: Path) -> ExtractionResult:
        """Try OCR extraction.

        Args:
            pdf_path: Path to PDF file

        Returns:
            ExtractionResult from OCR or error result
        """
        if not self.enable_ocr or self.ocr_extractor is None:
            return ExtractionResult(
                success=False,
                errors=["OCR not available. Install tesseract and required dependencies."],
                method_used=ExtractionMethod.OCR,
            )
        return self.ocr_extractor.extract(pdf_path)

    def _try_ocr_bytes(self, pdf_bytes: bytes, sender_vat_id: str | None = None) -> ExtractionResult:
        """Try OCR extraction from bytes.

        Args:
            pdf_bytes: PDF file contents
            sender_vat_id: User's own VAT ID to exclude from client detection

        Returns:
            ExtractionResult from OCR or error result
        """
        if not self.enable_ocr or self.ocr_extractor is None:
            return ExtractionResult(
                success=False,
                errors=["OCR not available. Install tesseract and required dependencies."],
                method_used=ExtractionMethod.OCR,
            )
        return self.ocr_extractor.extract_from_bytes(pdf_bytes, sender_vat_id=sender_vat_id)

    def _choose_best_result(
        self, text_result: ExtractionResult, ocr_result: ExtractionResult
    ) -> ExtractionResult:
        """Choose the best result between text and OCR extraction.

        Args:
            text_result: Result from text extraction
            ocr_result: Result from OCR extraction

        Returns:
            The better ExtractionResult
        """
        # If one failed, return the other
        if not text_result.success:
            return ocr_result
        if not ocr_result.success:
            return text_result

        # Both succeeded - compare quality
        text_conf = text_result.data.overall_confidence if text_result.data else 0
        ocr_conf = ocr_result.data.overall_confidence if ocr_result.data else 0

        # Check minimum data extraction
        text_has_min = text_result.data.has_minimum_data if text_result.data else False
        ocr_has_min = ocr_result.data.has_minimum_data if ocr_result.data else False

        # Prefer result with minimum data
        if ocr_has_min and not text_has_min:
            ocr_result.warnings.append("OCR extraction used (text extraction incomplete).")
            return ocr_result

        if text_has_min and not ocr_has_min:
            return text_result

        # Both have minimum data or neither does - use confidence
        # Give slight preference to text extraction (faster, more reliable when it works)
        if ocr_conf > text_conf + 0.1:  # OCR needs to be notably better
            ocr_result.warnings.append("OCR extraction used (higher confidence than text).")
            return ocr_result

        return text_result

    def get_extraction_methods(self) -> list[str]:
        """Get available extraction methods.

        Returns:
            List of available method names
        """
        methods = ["text"]
        if self.enable_ocr and self.ocr_extractor is not None:
            methods.append("ocr")
        return methods


# Singleton instance for convenience
invoice_extractor = InvoiceExtractor()


def extract_invoice(pdf_path: str | Path, force_ocr: bool = False) -> ExtractionResult:
    """Convenience function to extract invoice data.

    Args:
        pdf_path: Path to PDF file
        force_ocr: If True, use OCR directly

    Returns:
        ExtractionResult with extracted data
    """
    return invoice_extractor.extract(pdf_path, force_ocr=force_ocr)


def extract_invoice_from_bytes(pdf_bytes: bytes, force_ocr: bool = False, sender_vat_id: str | None = None) -> ExtractionResult:
    """Convenience function to extract invoice data from bytes.

    Args:
        pdf_bytes: PDF file contents
        force_ocr: If True, use OCR directly
        sender_vat_id: User's own VAT ID to exclude from client detection

    Returns:
        ExtractionResult with extracted data
    """
    return invoice_extractor.extract_from_bytes(pdf_bytes, force_ocr=force_ocr, sender_vat_id=sender_vat_id)
