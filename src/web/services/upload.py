"""Upload service for handling PDF invoice uploads.

Orchestrates file storage, extraction, and database operations
for the invoice upload workflow.
"""

import hashlib
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import aiofiles
import aiofiles.os

from src.core.exceptions import (
    DuplicateUploadError,
    FileTooLargeError,
    InvalidFileTypeError,
    UploadError,
)
from src.core.extraction import (
    ExtractedInvoiceData,
    ExtractionResult,
    extract_invoice_from_bytes,
)
from src.core.models import VatRate
from src.db.repository import UploadedDocumentRepository
from src.web.routes.settings import load_settings

# Base upload directory (relative to app root)
UPLOAD_BASE_DIR = Path("data/uploads/invoices")

# Maximum file size (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024

# Allowed MIME types (browsers may send various types)
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/octet-stream",  # Generic binary, verify with magic bytes
    "application/x-pdf",  # Older PDF MIME type
}


logger = logging.getLogger(__name__)


class UploadService:
    """Service for handling invoice PDF uploads."""

    def __init__(self, repo: UploadedDocumentRepository):
        """Initialize upload service.

        Args:
            repo: UploadedDocumentRepository instance
        """
        self.repo = repo

    async def process_upload(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> tuple[int, ExtractionResult]:
        """Process an uploaded PDF file.

        1. Validate file
        2. Calculate content hash
        3. Check for duplicates
        4. Store file
        5. Extract invoice data
        6. Save to database

        Args:
            file_content: PDF file bytes
            filename: Original filename
            content_type: MIME type of the file

        Returns:
            Tuple of (document_id, ExtractionResult)

        Raises:
            UploadError: If upload fails validation or processing
        """
        # Step 0: Load user settings to get sender's VAT ID
        settings = load_settings()
        sender_vat_id = settings.vat_id if settings.vat_id else None

        # Step 1: Validate file
        self._validate_file(file_content, filename, content_type)

        # Step 2: Calculate content hash
        content_hash = self._calculate_hash(file_content)

        # Step 3: Check for duplicates
        existing = await self.repo.get_by_hash(content_hash)
        if existing:
            # If already linked to an invoice, reject
            if existing.get("invoice_id"):
                raise DuplicateUploadError(existing["invoice_id"])

            # Reuse existing upload but always re-run extraction (patterns may have improved)
            logger.info(f"Reusing existing upload ID {existing['id']} (not yet confirmed) - re-extracting")
            doc_id = existing["id"]

            # Always re-run extraction to use latest patterns
            result = extract_invoice_from_bytes(file_content, sender_vat_id=sender_vat_id)
            await self.repo.update_extraction(
                doc_id=doc_id,
                status="completed" if result.success else "failed",
                confidence=result.data.overall_confidence if result.data else None,
                method=result.method_used.value,
                extracted_data=result.data.model_dump_json() if result.data else None,
                errors=result.errors if result.errors else None,
            )
            result.warnings.append("Re-extracted from previously uploaded file.")

            return doc_id, result

        # Step 4: Store file
        stored_filename, file_path = await self._store_file(file_content, filename)

        # Step 5: Create initial database record
        doc_id = await self.repo.create(
            filename=filename,
            stored_filename=stored_filename,
            file_path=str(file_path),
            file_size=len(file_content),
            content_hash=content_hash,
        )

        # Step 6: Extract invoice data
        try:
            result = extract_invoice_from_bytes(file_content, sender_vat_id=sender_vat_id)

            # Update database with extraction results
            await self.repo.update_extraction(
                doc_id=doc_id,
                status="completed" if result.success else "failed",
                confidence=result.data.overall_confidence if result.data else None,
                method=result.method_used.value,
                extracted_data=result.data.model_dump_json() if result.data else None,
                errors=result.errors if result.errors else None,
            )

            return doc_id, result

        except Exception as e:
            # Update database with error
            await self.repo.update_extraction(
                doc_id=doc_id,
                status="failed",
                errors=[f"Extraction error: {str(e)}"],
            )
            raise UploadError(f"Failed to extract invoice data: {str(e)}")

    async def get_extraction_data(self, doc_id: int) -> tuple[dict | None, ExtractedInvoiceData | None]:
        """Get uploaded document and its extracted data.

        Args:
            doc_id: Document ID

        Returns:
            Tuple of (document_dict, ExtractedInvoiceData or None)
        """
        doc = await self.repo.get_by_id(doc_id)
        if not doc:
            return None, None

        extracted_data = None
        if doc["extracted_data"]:
            import json
            data_dict = json.loads(doc["extracted_data"])
            extracted_data = ExtractedInvoiceData.model_validate(data_dict)

        return doc, extracted_data

    async def find_matching_clients(
        self,
        extracted_data: ExtractedInvoiceData,
        client_repo,
    ) -> list[tuple]:
        """Find existing clients that match the extracted data.

        Uses extracted client name, VAT ID, and city to find potential matches.
        Returns matches with confidence scores.

        Args:
            extracted_data: Extracted invoice data with client info
            client_repo: ClientRepository instance

        Returns:
            List of (Client, confidence) tuples, sorted by confidence desc
        """
        if not extracted_data or not extracted_data.client:
            return []

        client_info = extracted_data.client

        # Extract search criteria
        name = str(client_info.name.value) if client_info.name.value else None
        vat_id = str(client_info.vat_id.value) if client_info.vat_id.value else None
        city = str(client_info.city.value) if client_info.city.value else None

        # Use the repository's find_matches method
        matches = await client_repo.find_matches(
            name=name,
            vat_id=vat_id,
            city=city,
            limit=5
        )

        return matches

    async def retry_extraction(self, doc_id: int, force_ocr: bool = False) -> ExtractionResult:
        """Retry extraction for a document.

        Args:
            doc_id: Document ID
            force_ocr: Whether to force OCR extraction

        Returns:
            ExtractionResult from retry

        Raises:
            UploadError: If document not found or extraction fails
        """
        doc = await self.repo.get_by_id(doc_id)
        if not doc:
            raise UploadError(f"Document not found: {doc_id}")

        # Read file from storage - file_path is stored as relative path from app root
        file_path = Path(doc["file_path"])
        logger.info(f"Retry extraction for doc {doc_id}, file_path: {file_path}")
        if not file_path.exists():
            raise UploadError(f"File not found on disk: {file_path}")

        async with aiofiles.open(file_path, "rb") as f:
            file_content = await f.read()

        # Load user settings to get sender's VAT ID
        settings = load_settings()
        sender_vat_id = settings.vat_id if settings.vat_id else None

        # Extract with specified method
        from src.core.extraction.extractor import invoice_extractor
        result = invoice_extractor.extract_from_bytes(file_content, force_ocr=force_ocr, sender_vat_id=sender_vat_id)

        # Update database
        await self.repo.update_extraction(
            doc_id=doc_id,
            status="completed" if result.success else "failed",
            confidence=result.data.overall_confidence if result.data else None,
            method=result.method_used.value,
            extracted_data=result.data.model_dump_json() if result.data else None,
            errors=result.errors if result.errors else None,
        )

        return result

    async def confirm_and_create_invoice(
        self,
        doc_id: int,
        form_data: dict,
        invoice_repo,
        client_repo,
    ) -> int:
        """Confirm extraction and create invoice from uploaded document.

        Args:
            doc_id: Uploaded document ID
            form_data: Form data with corrected/confirmed values
            invoice_repo: InvoiceRepository instance
            client_repo: ClientRepository instance

        Returns:
            Created invoice ID

        Raises:
            UploadError: If document not found or invoice creation fails
        """
        doc = await self.repo.get_by_id(doc_id)
        if not doc:
            raise UploadError(f"Document not found: {doc_id}")

        if doc["invoice_id"]:
            raise UploadError(f"Document already linked to invoice {doc['invoice_id']}")

        # Find or create client
        client_id, client_name = await self._resolve_client(form_data, client_repo)

        # Create invoice
        from datetime import date

        from src.core.models import InvoiceInput

        # Parse VAT rate
        vat_rate_str = form_data.get("vat_rate", "0.19")
        vat_rate = self._parse_vat_rate(vat_rate_str)

        # Parse dates
        invoice_date = self._parse_date(form_data.get("invoice_date"))
        due_date = self._parse_date(form_data.get("due_date"))

        # Parse amount
        amount_str = form_data.get("amount_gross") or form_data.get("amount_net", "0")
        amount = Decimal(amount_str.replace(",", ".")) if amount_str else Decimal("0")

        # Generate description from line items if not provided
        description = form_data.get("description", "")
        if not description or len(description) < 3:
            # Build description from line items
            line_item_descriptions = []
            i = 0
            while f"line_items[{i}][description]" in form_data:
                item_desc = form_data.get(f"line_items[{i}][description]", "")
                if item_desc:
                    line_item_descriptions.append(item_desc)
                i += 1

            if line_item_descriptions:
                description = "; ".join(line_item_descriptions)
            else:
                description = "Invoice"  # Fallback

            # Truncate if too long
            if len(description) > 1000:
                description = description[:997] + "..."

        invoice_input = InvoiceInput(
            client=client_name,
            invoice_number=form_data.get("invoice_number", ""),
            date=invoice_date or date.today(),
            due_date=due_date,
            amount=amount,
            vat_rate=vat_rate,
            description=description,
        )

        # Create invoice with link to uploaded document
        invoice = await invoice_repo.create(
            invoice_input,
            client_id=client_id,
            uploaded_document_id=doc_id,
        )

        # Update document with invoice link
        await self.repo.link_to_invoice(doc_id, invoice.id)

        return invoice.id

    async def delete_upload(self, doc_id: int) -> bool:
        """Delete an uploaded document and its file.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted, False if not found
        """
        doc = await self.repo.get_by_id(doc_id)
        if not doc:
            return False

        # Don't delete if already linked to an invoice
        if doc["invoice_id"]:
            raise UploadError(
                f"Cannot delete: document is linked to invoice {doc['invoice_id']}"
            )

        # Delete file from disk - file_path is stored as relative path from app root
        file_path = Path(doc["file_path"])
        if file_path.exists():
            await aiofiles.os.remove(file_path)

        # Hard delete from database (since not linked to invoice)
        await self.repo.hard_delete(doc_id)

        return True

    def _validate_file(self, content: bytes, filename: str, content_type: str) -> None:
        """Validate uploaded file.

        Args:
            content: File bytes
            filename: Original filename
            content_type: MIME type

        Raises:
            FileTooLargeError: If file exceeds size limit
            InvalidFileTypeError: If MIME type not allowed
            UploadError: For other validation failures
        """
        logger.info(f"Validating upload: filename={filename}, content_type={content_type}, size={len(content)}")

        # Check file size
        if len(content) > MAX_FILE_SIZE:
            logger.warning(f"File too large: {len(content)} bytes")
            raise FileTooLargeError(len(content), MAX_FILE_SIZE)

        if len(content) == 0:
            logger.warning("Empty file uploaded")
            raise UploadError("File is empty.")

        # Check MIME type
        if content_type not in ALLOWED_MIME_TYPES:
            logger.warning(f"Invalid MIME type: {content_type}")
            raise InvalidFileTypeError(content_type, list(ALLOWED_MIME_TYPES))

        # Check file extension
        if not filename.lower().endswith(".pdf"):
            logger.warning(f"Invalid extension: {filename}")
            raise UploadError("File must have .pdf extension.")

        # Verify PDF magic bytes
        if not content[:4] == b"%PDF":
            logger.warning(f"Invalid PDF magic bytes: {content[:4]!r}")
            raise UploadError("File does not appear to be a valid PDF.")

        logger.info("File validation passed")

    def _calculate_hash(self, content: bytes) -> str:
        """Calculate SHA-256 hash of file content.

        Args:
            content: File bytes

        Returns:
            Hex-encoded hash string
        """
        return hashlib.sha256(content).hexdigest()

    async def _store_file(self, content: bytes, filename: str) -> tuple[str, Path]:
        """Store file in upload directory.

        Files are stored in year/month subdirectories with UUID filenames.

        Args:
            content: File bytes
            filename: Original filename (preserved in database)

        Returns:
            Tuple of (stored_filename, relative_path)
        """
        now = datetime.now()
        year_month_dir = UPLOAD_BASE_DIR / str(now.year) / f"{now.month:02d}"

        # Create directory if needed
        await aiofiles.os.makedirs(year_month_dir, exist_ok=True)

        # Generate unique filename
        stored_filename = f"{uuid.uuid4()}.pdf"
        file_path = year_month_dir / stored_filename

        # Write file
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        return stored_filename, file_path

    async def _resolve_client(self, form_data: dict, client_repo) -> tuple[int, str]:
        """Find or create client from form data.

        If existing_client_id is provided, uses that client directly.
        Otherwise, creates a new client with the provided details.

        Args:
            form_data: Form data with client fields
            client_repo: ClientRepository instance

        Returns:
            Tuple of (Client ID, Client Name)
        """
        # Check if user selected an existing client
        existing_client_id = form_data.get("existing_client_id")
        if existing_client_id:
            existing_client = await client_repo.get_by_id(existing_client_id)
            if existing_client:
                return existing_client.id, existing_client.name
            # If not found, fall through to create new client

        client_name = form_data.get("client_name", "").strip()
        if not client_name:
            raise UploadError("Client name is required.")

        # Check if client with same VAT ID already exists
        client_vat_id = form_data.get("client_vat_id", "").strip()
        if client_vat_id:
            vat_client = await client_repo.find_by_vat_id(client_vat_id)
            if vat_client:
                return vat_client.id, vat_client.name

        # Check if client with exact same name already exists
        existing_clients = await client_repo.search(client_name, limit=5)
        for client in existing_clients:
            if client.name.lower() == client_name.lower():
                return client.id, client.name

        # Create new client with all provided details
        from src.core.models import ClientInput
        client_input = ClientInput(
            name=client_name,
            street=form_data.get("client_street", ""),
            zip_code=form_data.get("client_zip_code", ""),
            city=form_data.get("client_city", ""),
            country=form_data.get("client_country", "DE"),
            vat_id=client_vat_id,
            email=form_data.get("client_email", ""),
            phone=form_data.get("client_phone", ""),
        )

        new_client = await client_repo.create(client_input)
        return new_client.id, new_client.name

    def _parse_vat_rate(self, rate_str: str) -> VatRate:
        """Parse VAT rate string to VatRate enum.

        Args:
            rate_str: VAT rate as string (e.g., "0.19", "19", "19%")

        Returns:
            VatRate enum value
        """
        # Normalize rate string
        rate_str = rate_str.strip().rstrip("%")
        try:
            rate = Decimal(rate_str.replace(",", "."))
            # Convert percentage to decimal if needed
            if rate > 1:
                rate = rate / 100

            # Map to nearest VatRate
            if rate <= Decimal("0.01"):
                return VatRate.ZERO
            elif rate <= Decimal("0.10"):
                return VatRate.REDUCED
            else:
                return VatRate.STANDARD
        except (ValueError, TypeError, ArithmeticError):
            return VatRate.STANDARD

    def _parse_date(self, date_str: str | None):
        """Parse date string to date object.

        Args:
            date_str: Date string (ISO format or various formats)

        Returns:
            date object or None
        """
        if not date_str:
            return None

        from datetime import date

        from src.core.extraction.patterns import parse_date

        # Try ISO format first
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            pass

        # Try extraction pattern parser
        return parse_date(date_str)


# Dependency injection helper
def get_upload_service(repo: UploadedDocumentRepository) -> UploadService:
    """Get UploadService instance.

    Args:
        repo: UploadedDocumentRepository instance

    Returns:
        UploadService instance
    """
    return UploadService(repo)
