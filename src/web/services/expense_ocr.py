"""Expense Receipt OCR Service.

Orchestrates the complete receipt scanning pipeline:
1. OCR text extraction (PaddleOCR or Tesseract)
2. Optional LLM-enhanced parsing for complex receipts
3. Category prediction using existing ML model
4. Confidence-scored results for user review
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from src.core.extraction.expense_models import (
    ExpenseExtractionResult,
    ExtractedDateField,
    ExtractedDecimalField,
    ExtractedExpenseData,
    ExtractedField,
    ReceiptLLMSchema,
)
from src.core.extraction.expense_ocr import (
    ExpenseOCRExtractor,
    get_expense_ocr_extractor,
)
from src.core.models import ExpenseCategory
from src.web.services.ml_expense import (
    ExpenseCategoryPredictor,
    get_expense_category_predictor,
)

logger = logging.getLogger(__name__)


class ExpenseReceiptService:
    """Service for processing expense receipts with OCR.

    Combines OCR extraction with optional LLM enhancement and
    automatic category prediction.

    Features:
    - PaddleOCR-VL for German receipt text extraction
    - Optional local LLM for complex receipt parsing
    - TabPFN category prediction
    - Confidence scoring for all fields
    """

    def __init__(
        self,
        ocr_extractor: ExpenseOCRExtractor | None = None,
        category_predictor: ExpenseCategoryPredictor | None = None,
        enable_llm_enhancement: bool = True,
    ):
        """Initialize the receipt service.

        Args:
            ocr_extractor: OCR extractor instance (or singleton)
            category_predictor: Category predictor instance (or singleton)
            enable_llm_enhancement: Whether to use LLM for complex receipts
        """
        self._ocr_extractor = ocr_extractor
        self._category_predictor = category_predictor
        self._enable_llm = enable_llm_enhancement
        self._llm_generator = None

    @property
    def ocr_extractor(self) -> ExpenseOCRExtractor:
        """Get OCR extractor (lazy load singleton)."""
        if self._ocr_extractor is None:
            self._ocr_extractor = get_expense_ocr_extractor()
        return self._ocr_extractor

    @property
    def category_predictor(self) -> ExpenseCategoryPredictor:
        """Get category predictor (lazy load singleton)."""
        if self._category_predictor is None:
            self._category_predictor = get_expense_category_predictor()
        return self._category_predictor

    async def process_receipt_image(
        self,
        image_bytes: bytes,
        use_llm: bool | None = None,
    ) -> ExpenseExtractionResult:
        """Process a receipt image and extract expense data.

        Args:
            image_bytes: Image file contents
            use_llm: Override LLM enhancement setting

        Returns:
            ExpenseExtractionResult with extracted and predicted data
        """
        # Step 1: Run OCR extraction
        result = self.ocr_extractor.extract_from_bytes(image_bytes)

        if not result.success or not result.data:
            return result

        # Step 2: Optionally enhance with LLM for low-confidence results
        should_use_llm = use_llm if use_llm is not None else self._enable_llm

        if should_use_llm and result.data.overall_confidence < 0.6:
            result = await self._enhance_with_llm(result)

        # Step 3: Predict category
        if result.data:
            result.data = await self._predict_category(result.data)

        return result

    async def process_receipt_file(
        self,
        file_path: str,
        use_llm: bool | None = None,
    ) -> ExpenseExtractionResult:
        """Process a receipt image file.

        Args:
            file_path: Path to image file
            use_llm: Override LLM enhancement setting

        Returns:
            ExpenseExtractionResult with extracted and predicted data
        """
        # Step 1: Run OCR extraction
        result = self.ocr_extractor.extract(file_path)

        if not result.success or not result.data:
            return result

        # Step 2: Optionally enhance with LLM for low-confidence results
        should_use_llm = use_llm if use_llm is not None else self._enable_llm

        if should_use_llm and result.data.overall_confidence < 0.6:
            result = await self._enhance_with_llm(result)

        # Step 3: Predict category
        if result.data:
            result.data = await self._predict_category(result.data)

        return result

    async def _enhance_with_llm(
        self,
        result: ExpenseExtractionResult,
    ) -> ExpenseExtractionResult:
        """Enhance extraction results using local LLM.

        Used when OCR confidence is low to improve field extraction.
        """
        if not result.data or not result.data.raw_text:
            return result

        try:
            # Import LLM components lazily to avoid circular imports
            from src.llm.manager import get_model_manager
            from src.llm.structured import get_structured_generator

            manager = get_model_manager()
            if not manager.is_loaded:
                logger.debug("LLM not loaded, skipping enhancement")
                return result

            generator = get_structured_generator()

            # Build prompt for receipt parsing
            prompt = self._build_llm_prompt(result.data.raw_text)

            # Generate structured output
            llm_result = await generator.generate(
                prompt=prompt,
                schema=ReceiptLLMSchema,
                system_prompt=self._get_system_prompt(),
                temperature=0.1,
                max_tokens=500,
            )

            # Merge LLM results with OCR results
            result.data = self._merge_llm_results(result.data, llm_result)
            result.data.overall_confidence = result.data.calculate_overall_confidence()

            logger.debug("LLM enhancement completed successfully")

        except Exception as e:
            logger.warning(f"LLM enhancement failed: {e}")
            result.warnings.append(f"LLM enhancement unavailable: {e}")

        return result

    def _build_llm_prompt(self, ocr_text: str) -> str:
        """Build prompt for LLM receipt parsing."""
        return f"""Analysiere diesen deutschen Kassenbon/Beleg-Text und extrahiere die Informationen:

--- BELEG-TEXT ---
{ocr_text[:2000]}
--- ENDE ---

Extrahiere:
1. Händler/Geschäftsname (meist oben auf dem Beleg)
2. Datum (im Format YYYY-MM-DD)
3. Gesamtbetrag (Brutto, mit 2 Dezimalstellen, z.B. "19.99")
4. Nettobetrag (falls separat angegeben)
5. MwSt-Betrag (falls separat angegeben)
6. MwSt-Satz (19, 7, oder 0)
7. Kurze Beschreibung der gekauften Artikel/Dienstleistungen

Antworte im vorgegebenen JSON-Format."""

    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM receipt parsing."""
        return """Du bist ein Experte für die Analyse deutscher Kassenbons und Belege.
Deine Aufgabe ist es, strukturierte Daten aus OCR-Text zu extrahieren.

Wichtige Regeln:
- Beträge immer mit Punkt als Dezimaltrennzeichen: "19.99" nicht "19,99"
- Datum im ISO-Format: YYYY-MM-DD
- MwSt-Satz als Zahl: 19, 7, oder 0
- Bei Unsicherheit: leeren String ("") zurückgeben
- Confidence: "high" wenn alle Hauptfelder klar, "medium" bei Teilinformationen, "low" bei Unsicherheit"""

    def _merge_llm_results(
        self,
        ocr_data: ExtractedExpenseData,
        llm_result: ReceiptLLMSchema,
    ) -> ExtractedExpenseData:
        """Merge LLM extraction results with OCR results.

        LLM results are used to fill gaps or improve low-confidence fields.
        """
        # Vendor: prefer LLM if OCR confidence is low
        if llm_result.vendor_name and (
            not ocr_data.vendor.value or ocr_data.vendor.confidence < 0.7
        ):
            ocr_data.vendor = ExtractedField(
                value=llm_result.vendor_name,
                confidence=0.85,
                source="llm_extraction",
            )

        # Date: prefer LLM if OCR didn't find date
        if llm_result.receipt_date and not ocr_data.receipt_date.value:
            try:
                from datetime import datetime

                parsed_date = datetime.strptime(
                    llm_result.receipt_date, "%Y-%m-%d"
                ).date()
                ocr_data.receipt_date = ExtractedDateField(
                    value=parsed_date,
                    confidence=0.8,
                    source="llm_extraction",
                    raw_value=llm_result.receipt_date,
                )
            except ValueError:
                pass

        # Amount: prefer LLM if OCR confidence is low
        if llm_result.total_amount and (
            not ocr_data.amount_gross.value or ocr_data.amount_gross.confidence < 0.7
        ):
            try:
                amount = Decimal(llm_result.total_amount).quantize(Decimal("0.01"))
                ocr_data.amount_gross = ExtractedDecimalField(
                    value=amount,
                    confidence=0.85,
                    source="llm_extraction",
                    raw_value=llm_result.total_amount,
                )
            except InvalidOperation:
                pass

        # VAT rate: prefer LLM if OCR didn't find rate
        if llm_result.vat_rate and not ocr_data.vat_rate.value:
            rate = llm_result.vat_rate
            if rate in ("19", "7", "0"):
                ocr_data.vat_rate = ExtractedField(
                    value=f"0.{int(rate):02d}" if int(rate) > 0 else "0.00",
                    confidence=0.8,
                    source="llm_extraction",
                )

        # Description: prefer LLM if more detailed
        if llm_result.items_description and (
            not ocr_data.description.value
            or len(llm_result.items_description) > len(ocr_data.description.value or "")
        ):
            ocr_data.description = ExtractedField(
                value=llm_result.items_description[:200],
                confidence=0.75,
                source="llm_extraction",
            )

        return ocr_data

    async def _predict_category(
        self,
        data: ExtractedExpenseData,
    ) -> ExtractedExpenseData:
        """Predict expense category using ML model.

        Args:
            data: Extracted expense data

        Returns:
            Data with predicted category added
        """
        try:
            vendor = data.vendor.value or ""
            description = data.description.value or ""
            amount = data.amount_gross.value or Decimal("0")
            vat_rate = data.vat_rate.value or "0.19"
            expense_date = data.receipt_date.value or date.today()

            prediction = await self.category_predictor.predict(
                vendor=vendor,
                description=description,
                amount_gross=amount,
                vat_rate=vat_rate,
                expense_date=expense_date,
            )

            data.predicted_category = ExpenseCategory(prediction.predicted_category)
            data.category_confidence = prediction.confidence

        except Exception as e:
            logger.warning(f"Category prediction failed: {e}")
            data.predicted_category = ExpenseCategory.SONSTIGES
            data.category_confidence = 0.0

        return data

    def get_supported_formats(self) -> list[str]:
        """Get list of supported image formats.

        Returns:
            List of supported file extensions
        """
        return [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"]

    def get_available_engines(self) -> dict[str, bool]:
        """Get availability status of OCR engines.

        Returns:
            Dict mapping engine name to availability
        """
        engines = self.ocr_extractor.get_available_engines()
        return {
            "paddleocr": "paddleocr" in engines,
            "tesseract": "tesseract" in engines,
        }


# =============================================================================
# Singleton Instance
# =============================================================================


_service: ExpenseReceiptService | None = None


def get_expense_receipt_service() -> ExpenseReceiptService:
    """Get or create the expense receipt service singleton."""
    global _service
    if _service is None:
        _service = ExpenseReceiptService()
    return _service
