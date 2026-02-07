"""Invoice PDF extraction module.

Provides tiered extraction of invoice data from PDF files:
- Tier 1: Text extraction using pdfplumber (digital PDFs)
- Tier 2: OCR extraction using pytesseract (scanned PDFs)
- Future Tier 3: AI extraction using Claude API (complex layouts)
"""

from src.core.extraction.extractor import (
    InvoiceExtractor,
    extract_invoice,
    extract_invoice_from_bytes,
    invoice_extractor,
)
from src.core.extraction.models import (
    ExtractedClientInfo,
    ExtractedDateField,
    ExtractedDecimalField,
    ExtractedField,
    ExtractedInvoiceData,
    ExtractionConfidence,
    ExtractionMethod,
    ExtractionResult,
    ExtractionStatus,
)

__all__ = [
    # Models
    "ExtractionConfidence",
    "ExtractionMethod",
    "ExtractionStatus",
    "ExtractedField",
    "ExtractedDateField",
    "ExtractedDecimalField",
    "ExtractedClientInfo",
    "ExtractedInvoiceData",
    "ExtractionResult",
    # Extractor
    "InvoiceExtractor",
    "invoice_extractor",
    "extract_invoice",
    "extract_invoice_from_bytes",
]
