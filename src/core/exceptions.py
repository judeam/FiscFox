"""Domain-specific exception hierarchy for FiscFox.

Provides structured error handling across all application layers:
- DomainError: Business logic and validation errors
- RepositoryError: Data access layer errors
- ExtractionError: PDF extraction and processing errors

All exceptions include an error code for client-side handling.
"""

from typing import Any


class FiscFoxError(Exception):
    """Base exception for all FiscFox errors.

    Attributes:
        code: Machine-readable error code
        message: Human-readable error message
        details: Additional error context
    """

    code: str = "FISCFOX_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


# =============================================================================
# Domain Errors (Business Logic)
# =============================================================================


class DomainError(FiscFoxError):
    """Base for business logic errors."""

    code = "DOMAIN_ERROR"


class ValidationError(DomainError):
    """Input validation failures."""

    code = "VALIDATION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if field:
            details["field"] = field
        super().__init__(message, details=details)


class TaxCalculationError(DomainError):
    """Tax calculation failures."""

    code = "TAX_CALCULATION_ERROR"


class InvalidTaxYearError(TaxCalculationError):
    """Invalid or unsupported tax year."""

    code = "INVALID_TAX_YEAR"

    def __init__(self, year: int, supported_years: list[int]) -> None:
        super().__init__(
            f"Tax configuration for year {year} not available. "
            f"Supported years: {supported_years}",
            details={"year": year, "supported_years": supported_years},
        )


class InconsistentTaxDataError(TaxCalculationError):
    """Tax data is inconsistent or corrupted."""

    code = "INCONSISTENT_TAX_DATA"


class SettingsError(DomainError):
    """Settings operation failures."""

    code = "SETTINGS_ERROR"


class InvalidSettingsError(SettingsError):
    """Settings validation failed."""

    code = "INVALID_SETTINGS"


class SettingsMigrationError(SettingsError):
    """Settings migration failed."""

    code = "SETTINGS_MIGRATION_ERROR"


# =============================================================================
# Repository Errors (Data Access)
# =============================================================================


class RepositoryError(FiscFoxError):
    """Data access layer errors."""

    code = "REPOSITORY_ERROR"


class NotFoundError(RepositoryError):
    """Entity not found in database."""

    code = "NOT_FOUND"

    def __init__(
        self,
        entity_type: str,
        entity_id: int | str,
    ) -> None:
        super().__init__(
            f"{entity_type} with ID {entity_id} not found",
            details={"entity_type": entity_type, "entity_id": entity_id},
        )


class DuplicateError(RepositoryError):
    """Entity already exists (unique constraint violation)."""

    code = "DUPLICATE"

    def __init__(
        self,
        entity_type: str,
        field: str,
        value: str,
    ) -> None:
        super().__init__(
            f"{entity_type} with {field}='{value}' already exists",
            details={"entity_type": entity_type, "field": field, "value": value},
        )


class DatabaseError(RepositoryError):
    """Database operation failed."""

    code = "DATABASE_ERROR"


# =============================================================================
# Extraction Errors (PDF Processing)
# =============================================================================


class ExtractionError(FiscFoxError):
    """PDF extraction and processing errors."""

    code = "EXTRACTION_ERROR"


class UnsupportedFileFormatError(ExtractionError):
    """File format not supported for extraction."""

    code = "UNSUPPORTED_FILE_FORMAT"

    def __init__(self, filename: str, expected_format: str = "PDF") -> None:
        super().__init__(
            f"File '{filename}' is not a valid {expected_format}",
            details={"filename": filename, "expected_format": expected_format},
        )


class ExtractionFailedError(ExtractionError):
    """Extraction process failed."""

    code = "EXTRACTION_FAILED"

    def __init__(
        self,
        reason: str,
        *,
        method: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if method:
            details["method"] = method
        super().__init__(f"Extraction failed: {reason}", details=details)


class OCRNotAvailableError(ExtractionError):
    """OCR extraction requested but not available."""

    code = "OCR_NOT_AVAILABLE"

    def __init__(self) -> None:
        super().__init__(
            "OCR extraction not available. Install tesseract and required dependencies.",
        )


# =============================================================================
# Invoice/Expense Errors
# =============================================================================


class InvoiceError(DomainError):
    """Invoice operation errors."""

    code = "INVOICE_ERROR"


class InvoiceNotFoundError(InvoiceError, NotFoundError):
    """Invoice not found."""

    code = "INVOICE_NOT_FOUND"

    def __init__(self, invoice_id: int) -> None:
        NotFoundError.__init__(self, "Invoice", invoice_id)


class InvoiceDuplicateError(InvoiceError, DuplicateError):
    """Invoice number already exists."""

    code = "INVOICE_DUPLICATE"

    def __init__(self, invoice_number: str) -> None:
        DuplicateError.__init__(self, "Invoice", "invoice_number", invoice_number)


class ExpenseError(DomainError):
    """Expense operation errors."""

    code = "EXPENSE_ERROR"


class ExpenseNotFoundError(ExpenseError, NotFoundError):
    """Expense not found."""

    code = "EXPENSE_NOT_FOUND"

    def __init__(self, expense_id: int) -> None:
        NotFoundError.__init__(self, "Expense", expense_id)


class ClientError(DomainError):
    """Client operation errors."""

    code = "CLIENT_ERROR"


class ClientNotFoundError(ClientError, NotFoundError):
    """Client not found."""

    code = "CLIENT_NOT_FOUND"

    def __init__(self, client_id: int) -> None:
        NotFoundError.__init__(self, "Client", client_id)


# =============================================================================
# Upload Errors (Keeping UploadError for backward compatibility)
# =============================================================================


class UploadError(FiscFoxError):
    """Upload operation errors."""

    code = "UPLOAD_ERROR"


class FileTooLargeError(UploadError):
    """Uploaded file exceeds size limit."""

    code = "FILE_TOO_LARGE"

    def __init__(self, file_size: int, max_size: int) -> None:
        super().__init__(
            f"File size ({file_size // 1024}KB) exceeds maximum allowed ({max_size // 1024}KB)",
            details={"file_size": file_size, "max_size": max_size},
        )


class InvalidFileTypeError(UploadError):
    """Uploaded file type not allowed."""

    code = "INVALID_FILE_TYPE"

    def __init__(self, content_type: str, allowed_types: list[str]) -> None:
        super().__init__(
            f"File type '{content_type}' not allowed. Allowed types: {allowed_types}",
            details={"content_type": content_type, "allowed_types": allowed_types},
        )


class DuplicateUploadError(UploadError):
    """File has already been uploaded."""

    code = "DUPLICATE_UPLOAD"

    def __init__(self, existing_invoice_id: int) -> None:
        super().__init__(
            f"This file has already been uploaded and linked to invoice {existing_invoice_id}",
            details={"existing_invoice_id": existing_invoice_id},
        )
