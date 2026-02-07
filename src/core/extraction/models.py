"""Pydantic models for invoice extraction.

All monetary values use Decimal for precision, never float.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class ExtractionStatus(StrEnum):
    """Status of extraction process."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    MANUAL = "manual"


class ExtractionMethod(StrEnum):
    """Method used for extraction."""

    TEXT = "text"  # pdfplumber text extraction
    OCR = "ocr"  # pytesseract OCR
    AI = "ai"  # Claude API (future)
    MANUAL = "manual"  # User manual entry


class ExtractionConfidence(StrEnum):
    """Confidence level categories."""

    HIGH = "high"  # >= 0.8 - Auto-fill, user review
    MEDIUM = "medium"  # 0.5 - 0.79 - Highlight uncertain fields
    LOW = "low"  # < 0.5 - Manual entry suggested


def get_confidence_level(confidence: float) -> ExtractionConfidence:
    """Get confidence level category from score.

    Args:
        confidence: Confidence score (0.0 - 1.0)

    Returns:
        ExtractionConfidence category
    """
    if confidence >= 0.8:
        return ExtractionConfidence.HIGH
    elif confidence >= 0.5:
        return ExtractionConfidence.MEDIUM
    else:
        return ExtractionConfidence.LOW


class ExtractedField(BaseModel):
    """Single extracted field with confidence score.

    Tracks the extracted value, confidence, and source pattern
    that matched the extraction.
    """

    value: str | Decimal | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    source: str = ""  # Pattern name or extraction source

    @property
    def confidence_level(self) -> ExtractionConfidence:
        """Get confidence level category."""
        return get_confidence_level(self.confidence)

    @property
    def is_high_confidence(self) -> bool:
        """Check if confidence is high (>= 0.8)."""
        return self.confidence >= 0.8

    @property
    def is_low_confidence(self) -> bool:
        """Check if confidence is low (< 0.5)."""
        return self.confidence < 0.5


class ExtractedDateField(BaseModel):
    """Extracted date field with confidence."""

    value: date | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    source: str = ""
    raw_value: str = ""  # Original string before parsing

    @property
    def confidence_level(self) -> ExtractionConfidence:
        """Get confidence level category."""
        return get_confidence_level(self.confidence)


class ExtractedDecimalField(BaseModel):
    """Extracted decimal/money field with confidence.

    All monetary values stored as Decimal for precision.
    """

    value: Decimal | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    source: str = ""
    raw_value: str = ""  # Original string before parsing

    @property
    def confidence_level(self) -> ExtractionConfidence:
        """Get confidence level category."""
        return get_confidence_level(self.confidence)


class ExtractedLineItem(BaseModel):
    """Single line item extracted from invoice."""

    description: str = ""
    service_date: date | None = None  # Date when service was performed
    quantity: Decimal = Decimal("1")
    unit: str = "Stk."  # Stück, Stunden, Tage, etc.
    unit_price: Decimal | None = None
    vat_rate: str = "0.19"  # VAT rate as string: "0.19", "0.07", "0.00"
    total: Decimal | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class ExtractedClientInfo(BaseModel):
    """Extracted client information.

    All fields that can be extracted from a client/recipient section
    of an invoice, with confidence scores.
    """

    name: ExtractedField = Field(default_factory=ExtractedField)
    street: ExtractedField = Field(default_factory=ExtractedField)
    zip_code: ExtractedField = Field(default_factory=ExtractedField)
    city: ExtractedField = Field(default_factory=ExtractedField)
    country: ExtractedField = Field(default_factory=ExtractedField)
    vat_id: ExtractedField = Field(default_factory=ExtractedField)
    email: ExtractedField = Field(default_factory=ExtractedField)
    phone: ExtractedField = Field(default_factory=ExtractedField)

    @property
    def overall_confidence(self) -> float:
        """Calculate overall confidence for client info."""
        # Name is most important, then address components
        fields = [self.name, self.street, self.city]
        if not any(f.value for f in fields):
            return 0.0
        valid_fields = [f for f in fields if f.value]
        if not valid_fields:
            return 0.0
        return sum(f.confidence for f in valid_fields) / len(valid_fields)

    @property
    def has_address(self) -> bool:
        """Check if we have meaningful address data."""
        return bool(self.street.value or (self.city.value and self.zip_code.value))


class ExtractedInvoiceData(BaseModel):
    """Complete extracted invoice data.

    Contains all fields that can be extracted from an invoice PDF,
    with confidence scores for each field.
    """

    # Client Information
    client: ExtractedClientInfo = Field(default_factory=ExtractedClientInfo)

    # Invoice Details
    invoice_number: ExtractedField = Field(default_factory=ExtractedField)
    invoice_date: ExtractedDateField = Field(default_factory=ExtractedDateField)
    due_date: ExtractedDateField = Field(default_factory=ExtractedDateField)
    payment_terms: ExtractedField = Field(default_factory=ExtractedField)  # "14 days", "Net 30", etc.

    # Amounts (all Decimal)
    amount_net: ExtractedDecimalField = Field(default_factory=ExtractedDecimalField)
    amount_gross: ExtractedDecimalField = Field(default_factory=ExtractedDecimalField)
    vat_amount: ExtractedDecimalField = Field(default_factory=ExtractedDecimalField)
    vat_rate: ExtractedField = Field(default_factory=ExtractedField)  # "0.19", "0.07", "0.00"

    # Line Items (if extractable)
    line_items: list[ExtractedLineItem] = Field(default_factory=list)

    # Description (combined from line items or extracted directly)
    description: ExtractedField = Field(default_factory=ExtractedField)

    # Metadata
    overall_confidence: float = 0.0
    extraction_method: ExtractionMethod = ExtractionMethod.TEXT
    raw_text: str = ""  # Full extracted text for debugging
    page_count: int = 0

    def calculate_overall_confidence(self) -> float:
        """Calculate overall extraction confidence.

        Weighted average of key fields:
        - Invoice number: 20%
        - Date: 15%
        - Client name: 20%
        - Amount (gross or net): 25%
        - VAT rate: 10%
        - Description: 10%
        """
        weights = {
            "invoice_number": 0.20,
            "invoice_date": 0.15,
            "client_name": 0.20,
            "amount": 0.25,
            "vat_rate": 0.10,
            "description": 0.10,
        }

        weighted_sum = 0.0
        total_weight = 0.0

        # Invoice number
        if self.invoice_number.value:
            weighted_sum += self.invoice_number.confidence * weights["invoice_number"]
            total_weight += weights["invoice_number"]

        # Invoice date
        if self.invoice_date.value:
            weighted_sum += self.invoice_date.confidence * weights["invoice_date"]
            total_weight += weights["invoice_date"]

        # Client name
        if self.client.name.value:
            weighted_sum += self.client.name.confidence * weights["client_name"]
            total_weight += weights["client_name"]

        # Amount (prefer gross, fallback to net)
        amount_field = self.amount_gross if self.amount_gross.value else self.amount_net
        if amount_field.value:
            weighted_sum += amount_field.confidence * weights["amount"]
            total_weight += weights["amount"]

        # VAT rate
        if self.vat_rate.value:
            weighted_sum += self.vat_rate.confidence * weights["vat_rate"]
            total_weight += weights["vat_rate"]

        # Description
        if self.description.value:
            weighted_sum += self.description.confidence * weights["description"]
            total_weight += weights["description"]

        if total_weight == 0:
            return 0.0

        return weighted_sum / total_weight

    @property
    def confidence_level(self) -> ExtractionConfidence:
        """Get overall confidence level category."""
        return get_confidence_level(self.overall_confidence)

    @property
    def has_minimum_data(self) -> bool:
        """Check if minimum required data was extracted.

        Minimum: invoice number OR (client name AND amount)
        """
        has_invoice_number = bool(self.invoice_number.value)
        has_client_and_amount = bool(self.client.name.value) and bool(
            self.amount_gross.value or self.amount_net.value
        )
        return has_invoice_number or has_client_and_amount

    def to_form_data(self) -> dict:
        """Convert extracted data to form-compatible dict.

        Returns dict with string values ready for HTML form population.
        """
        return {
            "client_name": str(self.client.name.value or ""),
            "client_street": str(self.client.street.value or ""),
            "client_zip_code": str(self.client.zip_code.value or ""),
            "client_city": str(self.client.city.value or ""),
            "client_country": str(self.client.country.value or "DE"),
            "client_vat_id": str(self.client.vat_id.value or ""),
            "invoice_number": str(self.invoice_number.value or ""),
            "invoice_date": self.invoice_date.value.isoformat() if self.invoice_date.value else "",
            "due_date": self.due_date.value.isoformat() if self.due_date.value else "",
            "amount_gross": str(self.amount_gross.value or ""),
            "amount_net": str(self.amount_net.value or ""),
            "vat_amount": str(self.vat_amount.value or ""),
            "vat_rate": str(self.vat_rate.value or "0.19"),
            "description": str(self.description.value or ""),
        }


class ExtractionResult(BaseModel):
    """Result of extraction attempt."""

    success: bool
    data: ExtractedInvoiceData | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    method_used: ExtractionMethod = ExtractionMethod.TEXT
    processing_time_ms: int = 0

    @property
    def has_errors(self) -> bool:
        """Check if extraction had errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if extraction had warnings."""
        return len(self.warnings) > 0
