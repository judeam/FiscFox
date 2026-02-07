"""Feature 1: Expense Auto-Categorization Service.

Uses TabPFN to predict expense categories based on:
- Vendor name
- Description text
- Amount
- VAT rate
- Temporal patterns

Reduces manual categorization effort and improves consistency.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from src.core.models import Expense, ExpenseCategory
from src.ml.base import ClassificationPredictor
from src.ml.features import (
    SimpleVectorizer,
    extract_temporal_features,
    log_transform,
    one_hot_encode,
)
from src.ml.models import CategoryPrediction

# All expense categories for classification
EXPENSE_CATEGORIES = [cat.value for cat in ExpenseCategory]
VAT_RATES = ["0.19", "0.07", "0.00"]


class ExpenseCategoryPredictor(ClassificationPredictor):
    """Predicts expense categories using TabPFN.

    Features:
    - TF-IDF vectors from vendor + description
    - Log-transformed amount
    - One-hot encoded VAT rate
    - Cyclical temporal features
    """

    def __init__(self, models_dir: Path | None = None):
        """Initialize predictor.

        Args:
            models_dir: Directory for model storage
        """
        self.vendor_vectorizer = SimpleVectorizer(max_features=50)
        self.desc_vectorizer = SimpleVectorizer(max_features=100)
        self._vectorizers_fitted = False

        super().__init__(
            model_name="expense_category",
            classes=EXPENSE_CATEGORIES,
            models_dir=models_dir,
            min_samples_to_train=30,
            retrain_every_n_samples=50,
        )

    def _extract_features(self, data: Any) -> np.ndarray:
        """Extract features from expense data.

        Args:
            data: Single expense dict/model or list of expenses

        Returns:
            Feature matrix
        """
        if isinstance(data, (dict, Expense)):
            expenses = [data]
        else:
            expenses = list(data)

        features_list = []
        for exp in expenses:
            if isinstance(exp, Expense):
                vendor = exp.vendor
                desc = exp.description
                amount = exp.amount_gross
                vat = exp.vat_rate.value
                exp_date = exp.date
            else:
                vendor = exp.get("vendor", "")
                desc = exp.get("description", "")
                amount = exp.get("amount_gross", Decimal("0"))
                vat = exp.get("vat_rate", "0.19")
                exp_date = exp.get("date", date.today())

            # Text features (simplified when vectorizers not fitted)
            if self._vectorizers_fitted:
                vendor_vec = self.vendor_vectorizer.transform([vendor])[0]
                desc_vec = self.desc_vectorizer.transform([desc])[0]
            else:
                # Fallback: simple character-based features
                vendor_vec = np.zeros(50)
                desc_vec = np.zeros(100)

            # Amount feature
            amount_log = log_transform(amount)

            # VAT rate one-hot
            vat_vec = one_hot_encode(str(vat), VAT_RATES)

            # Temporal features
            temporal = extract_temporal_features(exp_date)
            temporal_vec = [
                temporal["day_of_week_sin"],
                temporal["day_of_week_cos"],
                temporal["month_sin"],
                temporal["month_cos"],
                temporal["is_weekend"],
            ]

            # Combine all features
            feature_vec = np.concatenate([
                vendor_vec,
                desc_vec,
                [amount_log],
                vat_vec,
                temporal_vec,
            ])
            features_list.append(feature_vec)

        return np.array(features_list)

    def _extract_labels(self, data: Any) -> np.ndarray:
        """Extract category labels from expense data.

        Args:
            data: List of expenses with categories

        Returns:
            Label indices array
        """
        labels = []
        for exp in data:
            if isinstance(exp, Expense):
                cat = exp.category.value
            else:
                cat = exp.get("category", ExpenseCategory.SONSTIGES.value)

            # Convert category to index
            if cat in EXPENSE_CATEGORIES:
                labels.append(EXPENSE_CATEGORIES.index(cat))
            else:
                labels.append(EXPENSE_CATEGORIES.index(ExpenseCategory.SONSTIGES.value))

        return np.array(labels)

    def train(self, training_data: list[Expense]) -> dict[str, Any]:
        """Train the category predictor.

        Args:
            training_data: List of expenses with known categories

        Returns:
            Training metrics
        """
        if len(training_data) < self.min_samples_to_train:
            return {
                "success": False,
                "error": f"Need at least {self.min_samples_to_train} samples",
                "current_samples": len(training_data),
            }

        # Fit vectorizers
        vendors = [exp.vendor for exp in training_data]
        descriptions = [exp.description for exp in training_data]

        self.vendor_vectorizer.fit(vendors)
        self.desc_vectorizer.fit(descriptions)
        self._vectorizers_fitted = True

        # Now train the model
        return super().train(training_data)

    async def predict(
        self,
        vendor: str,
        description: str,
        amount_gross: Decimal,
        vat_rate: str = "0.19",
        expense_date: date | None = None,
    ) -> CategoryPrediction:
        """Predict category for an expense.

        Args:
            vendor: Vendor name
            description: Expense description
            amount_gross: Gross amount
            vat_rate: VAT rate string
            expense_date: Date of expense

        Returns:
            CategoryPrediction with predicted category and confidence
        """
        expense_data = {
            "vendor": vendor,
            "description": description,
            "amount_gross": amount_gross,
            "vat_rate": vat_rate,
            "date": expense_date or date.today(),
        }

        if not self.is_trained:
            # Return heuristic-based prediction
            category = self._heuristic_predict(vendor, description)
            return CategoryPrediction(
                predicted_category=category,
                confidence=0.3,
                alternatives=[],
                needs_review=True,
            )

        # Get prediction with alternatives
        alternatives = await self.predict_with_alternatives(expense_data, top_k=3)
        predicted_category, confidence = alternatives[0]

        return CategoryPrediction(
            predicted_category=predicted_category,
            confidence=confidence,
            alternatives=alternatives[1:],
            needs_review=confidence < 0.7,
        )

    def _heuristic_predict(self, vendor: str, description: str) -> str:
        """Simple heuristic-based category prediction.

        Used as fallback when model isn't trained.
        """
        text = f"{vendor} {description}".lower()

        # Simple keyword matching
        if any(kw in text for kw in ["amazon", "büro", "office", "papier", "toner"]):
            return ExpenseCategory.BUERO.value
        if any(kw in text for kw in ["software", "license", "subscription", "saas"]):
            return ExpenseCategory.SOFTWARE.value
        if any(kw in text for kw in ["laptop", "computer", "hardware", "monitor"]):
            return ExpenseCategory.HARDWARE.value
        if any(kw in text for kw in ["bahn", "flug", "hotel", "reise", "travel"]):
            return ExpenseCategory.REISE.value
        if any(kw in text for kw in ["telefon", "internet", "vodafone", "telekom"]):
            return ExpenseCategory.KOMMUNIKATION.value
        if any(kw in text for kw in ["versicherung", "insurance", "haftpflicht"]):
            return ExpenseCategory.VERSICHERUNG.value
        if any(kw in text for kw in ["kurs", "seminar", "training", "weiterbildung"]):
            return ExpenseCategory.FORTBILDUNG.value
        if any(kw in text for kw in ["restaurant", "essen", "bewirtung", "mittag"]):
            return ExpenseCategory.BEWIRTUNG.value
        if any(kw in text for kw in ["geschenk", "gift", "präsent"]):
            return ExpenseCategory.GESCHENKE.value

        return ExpenseCategory.SONSTIGES.value


# Singleton instance
_predictor: ExpenseCategoryPredictor | None = None


def get_expense_category_predictor() -> ExpenseCategoryPredictor:
    """Get or create the expense category predictor singleton."""
    global _predictor
    if _predictor is None:
        _predictor = ExpenseCategoryPredictor()
    return _predictor
