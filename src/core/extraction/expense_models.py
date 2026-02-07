"""Pydantic models for expense receipt extraction.

All monetary values use Decimal for precision, never float.
Designed for German receipts with VAT (Mehrwertsteuer) handling.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field

from src.core.models import ExpenseCategory, VatRate


class ExtractionConfidence(StrEnum):
    """Confidence level categories for extracted fields."""

    HIGH = "high"      # >= 0.8 - Auto-fill, user review optional
    MEDIUM = "medium"  # 0.5 - 0.79 - Highlight uncertain fields
    LOW = "low"        # < 0.5 - Manual entry suggested


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
    """Single extracted field with confidence score."""

    value: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    source: str = ""  # OCR engine or extraction method

    @property
    def confidence_level(self) -> ExtractionConfidence:
        """Get confidence level category."""
        return get_confidence_level(self.confidence)

    @property
    def is_high_confidence(self) -> bool:
        """Check if confidence is high (>= 0.8)."""
        return self.confidence >= 0.8


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


class ExtractedExpenseData(BaseModel):
    """Complete extracted expense data from receipt.

    Contains all fields that can be extracted from an expense receipt,
    with confidence scores for each field.
    """

    # Vendor Information
    vendor: ExtractedField = Field(default_factory=ExtractedField)
    vendor_address: ExtractedField = Field(default_factory=ExtractedField)
    vendor_vat_id: ExtractedField = Field(default_factory=ExtractedField)  # Seller's USt-IdNr

    # Receipt Details
    receipt_number: ExtractedField = Field(default_factory=ExtractedField)
    receipt_date: ExtractedDateField = Field(default_factory=ExtractedDateField)

    # Amounts (all Decimal for financial precision)
    amount_gross: ExtractedDecimalField = Field(default_factory=ExtractedDecimalField)
    amount_net: ExtractedDecimalField = Field(default_factory=ExtractedDecimalField)
    vat_amount: ExtractedDecimalField = Field(default_factory=ExtractedDecimalField)
    vat_rate: ExtractedField = Field(default_factory=ExtractedField)  # "0.19", "0.07", "0.00"

    # Description / Line items summary
    description: ExtractedField = Field(default_factory=ExtractedField)
    line_items: list[str] = Field(default_factory=list)  # Individual items if detected

    # Category (auto-predicted)
    predicted_category: ExpenseCategory | None = None
    category_confidence: float = 0.0

    # Metadata
    overall_confidence: float = 0.0
    raw_text: str = ""  # Full OCR text for debugging
    ocr_engine: str = "paddleocr"  # paddleocr, tesseract, etc.
    processing_time_ms: int = 0

    def calculate_overall_confidence(self) -> float:
        """Calculate overall extraction confidence.

        Weighted average of key fields:
        - Vendor: 25%
        - Date: 15%
        - Amount gross: 35%
        - VAT rate: 15%
        - Description: 10%
        """
        weights = {
            "vendor": 0.25,
            "date": 0.15,
            "amount": 0.35,
            "vat_rate": 0.15,
            "description": 0.10,
        }

        weighted_sum = 0.0
        total_weight = 0.0

        # Vendor
        if self.vendor.value:
            weighted_sum += self.vendor.confidence * weights["vendor"]
            total_weight += weights["vendor"]

        # Date
        if self.receipt_date.value:
            weighted_sum += self.receipt_date.confidence * weights["date"]
            total_weight += weights["date"]

        # Amount (gross preferred)
        if self.amount_gross.value:
            weighted_sum += self.amount_gross.confidence * weights["amount"]
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

        Minimum: vendor AND amount_gross, OR just amount with high confidence
        """
        has_vendor_and_amount = bool(self.vendor.value) and bool(self.amount_gross.value)
        has_high_conf_amount = bool(self.amount_gross.value) and self.amount_gross.confidence >= 0.8
        return has_vendor_and_amount or has_high_conf_amount

    @computed_field
    @property
    def calculated_vat_rate(self) -> VatRate:
        """Determine VAT rate from extracted data or calculate from amounts."""
        # Use extracted rate if available
        if self.vat_rate.value:
            rate_str = self.vat_rate.value
            if rate_str in ("0.19", "19", "19%"):
                return VatRate.STANDARD
            elif rate_str in ("0.07", "7", "7%"):
                return VatRate.REDUCED
            elif rate_str in ("0.00", "0", "0%"):
                return VatRate.ZERO

        # Calculate from gross/net if both available
        if self.amount_gross.value and self.amount_net.value:
            gross = self.amount_gross.value
            net = self.amount_net.value
            if net > 0:
                rate = (gross / net) - 1
                if abs(rate - Decimal("0.19")) < Decimal("0.02"):
                    return VatRate.STANDARD
                elif abs(rate - Decimal("0.07")) < Decimal("0.02"):
                    return VatRate.REDUCED

        # Default to standard German VAT
        return VatRate.STANDARD

    def to_form_data(self) -> dict:
        """Convert extracted data to form-compatible dict.

        Returns dict with string values ready for HTML form population.
        """
        return {
            "vendor": str(self.vendor.value or ""),
            "description": str(self.description.value or ""),
            "amount_gross": str(self.amount_gross.value or ""),
            "date": self.receipt_date.value.isoformat() if self.receipt_date.value else "",
            "vat_rate": self.calculated_vat_rate.value,
            "category": self.predicted_category.value if self.predicted_category else ExpenseCategory.SONSTIGES.value,
        }


class ExpenseExtractionResult(BaseModel):
    """Result of expense extraction attempt."""

    success: bool
    data: ExtractedExpenseData | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    processing_time_ms: int = 0

    @property
    def has_errors(self) -> bool:
        """Check if extraction had errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if extraction had warnings."""
        return len(self.warnings) > 0

    @property
    def needs_review(self) -> bool:
        """Check if extraction needs manual review."""
        if not self.success or not self.data:
            return True
        return self.data.overall_confidence < 0.7


class ReceiptLLMSchema(BaseModel):
    """Schema for LLM structured extraction from OCR text.

    Used with the local LLM for parsing raw OCR text into structured data.
    All monetary fields use string with pattern to preserve precision.
    """

    vendor_name: str = Field(
        default="",
        max_length=200,
        description="Name of the vendor/store from receipt header"
    )
    receipt_date: str = Field(
        default="",
        description="Date in YYYY-MM-DD format, or original format if unclear"
    )
    total_amount: str = Field(
        default="",
        description="Total/gross amount with 2 decimal places (e.g., '19.99')"
    )
    net_amount: str = Field(
        default="",
        description="Net amount before VAT, if shown separately"
    )
    vat_amount: str = Field(
        default="",
        description="VAT/MwSt amount if shown separately"
    )
    vat_rate: str = Field(
        default="19",
        description="VAT rate as percentage: 19, 7, or 0"
    )
    items_description: str = Field(
        default="",
        max_length=500,
        description="Brief summary of purchased items/services"
    )
    confidence: str = Field(
        default="medium",
        description="Extraction confidence: high, medium, or low"
    )
