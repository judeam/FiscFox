"""Feature extraction utilities for ML models.

Provides reusable feature engineering components:
- Text feature extraction (TF-IDF, token counts)
- Cyclical encoding for temporal features
- Numerical transformations
- Category encoding
"""

from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np


# =============================================================================
# Simple Utility Functions
# =============================================================================


def log_transform(value: Decimal | float, offset: float = 1.0) -> float:
    """Apply log transformation to monetary values.

    Uses log(x + offset) to handle zero values.

    Args:
        value: Monetary value
        offset: Offset to add before log (default 1.0)

    Returns:
        Log-transformed value
    """
    return float(np.log(float(value) + offset))


def one_hot_encode(value: str, options: list[str]) -> list[float]:
    """One-hot encode a categorical value.

    Args:
        value: The value to encode
        options: List of all possible values

    Returns:
        One-hot encoded list
    """
    return [1.0 if opt == value else 0.0 for opt in options]


def extract_temporal_features(d: date) -> dict[str, float]:
    """Extract temporal features from a date.

    Returns a dictionary with cyclical encodings and flags.

    Args:
        d: Date to extract features from

    Returns:
        Dictionary with temporal features
    """
    angle_dow = 2 * np.pi * d.weekday() / 7
    angle_month = 2 * np.pi * (d.month - 1) / 12

    return {
        "day_of_week_sin": float(np.sin(angle_dow)),
        "day_of_week_cos": float(np.cos(angle_dow)),
        "month_sin": float(np.sin(angle_month)),
        "month_cos": float(np.cos(angle_month)),
        "is_weekend": 1.0 if d.weekday() >= 5 else 0.0,
    }


class SimpleVectorizer:
    """Simple character-based text vectorizer for ML features.

    Provides basic text vectorization without requiring sklearn fit.
    """

    def __init__(self, max_features: int = 100):
        """Initialize vectorizer.

        Args:
            max_features: Output vector dimension
        """
        self.max_features = max_features
        self.vocabulary_: dict[str, int] = {}
        self._fitted = False

    def fit(self, texts: list[str]) -> "SimpleVectorizer":
        """Fit vocabulary on text data.

        Args:
            texts: List of text strings

        Returns:
            Self for chaining
        """
        # Build vocabulary from all unique words
        word_counts: dict[str, int] = {}
        for text in texts:
            for word in text.lower().split():
                word_counts[word] = word_counts.get(word, 0) + 1

        # Take top N most common words
        sorted_words = sorted(word_counts.items(), key=lambda x: -x[1])
        self.vocabulary_ = {
            word: idx for idx, (word, _) in enumerate(sorted_words[: self.max_features])
        }
        self._fitted = True
        return self

    def transform(self, texts: list[str]) -> np.ndarray:
        """Transform texts to feature vectors.

        Args:
            texts: List of text strings

        Returns:
            Feature matrix (n_samples, max_features)
        """
        result = np.zeros((len(texts), self.max_features))

        for i, text in enumerate(texts):
            for word in text.lower().split():
                if word in self.vocabulary_:
                    idx = self.vocabulary_[word]
                    result[i, idx] += 1.0

        # L2 normalize
        norms = np.linalg.norm(result, axis=1, keepdims=True)
        norms[norms == 0] = 1  # Avoid division by zero
        result = result / norms

        return result

    def fit_transform(self, texts: list[str]) -> np.ndarray:
        """Fit and transform in one step."""
        self.fit(texts)
        return self.transform(texts)


# =============================================================================
# Cyclical Encoders
# =============================================================================


class CyclicalEncoder:
    """Encode cyclical features (day of week, month, etc.) using sin/cos.

    Cyclical encoding ensures that the model understands that:
    - December (12) is close to January (1)
    - Sunday (6) is close to Monday (0)
    """

    @staticmethod
    def encode(value: int, max_value: int) -> tuple[float, float]:
        """Encode a cyclical value using sin/cos transformation.

        Args:
            value: Current value (e.g., day=3)
            max_value: Maximum value in cycle (e.g., 7 for days of week)

        Returns:
            Tuple of (sin_component, cos_component)
        """
        angle = 2 * np.pi * value / max_value
        return (np.sin(angle), np.cos(angle))

    @staticmethod
    def encode_day_of_week(d: date) -> tuple[float, float]:
        """Encode day of week (Monday=0, Sunday=6)."""
        return CyclicalEncoder.encode(d.weekday(), 7)

    @staticmethod
    def encode_month(d: date) -> tuple[float, float]:
        """Encode month (January=1, December=12)."""
        return CyclicalEncoder.encode(d.month - 1, 12)

    @staticmethod
    def encode_day_of_month(d: date) -> tuple[float, float]:
        """Encode day of month (1-31)."""
        return CyclicalEncoder.encode(d.day - 1, 31)

    @staticmethod
    def encode_quarter(d: date) -> tuple[float, float]:
        """Encode quarter (Q1=0, Q4=3)."""
        quarter = (d.month - 1) // 3
        return CyclicalEncoder.encode(quarter, 4)

    @staticmethod
    def encode_hour(hour: int) -> tuple[float, float]:
        """Encode hour of day (0-23)."""
        return CyclicalEncoder.encode(hour, 24)


class TextFeaturizer:
    """Extract features from text using TF-IDF or simple tokenization.

    Designed for German text (vendor names, descriptions).
    """

    def __init__(self, max_features: int = 100, use_tfidf: bool = True):
        """Initialize text featurizer.

        Args:
            max_features: Maximum number of features to extract
            use_tfidf: Use TF-IDF (True) or simple count vectorizer (False)
        """
        self.max_features = max_features
        self.use_tfidf = use_tfidf
        self.vectorizer: Any = None
        self._fitted = False

    def fit(self, texts: list[str]) -> "TextFeaturizer":
        """Fit the vectorizer on text data.

        Args:
            texts: List of text strings to fit on

        Returns:
            Self for chaining
        """
        if self.use_tfidf:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self.vectorizer = TfidfVectorizer(
                max_features=self.max_features,
                lowercase=True,
                strip_accents="unicode",
                ngram_range=(1, 2),  # Unigrams and bigrams
                min_df=1,
                max_df=0.95,
            )
        else:
            from sklearn.feature_extraction.text import CountVectorizer

            self.vectorizer = CountVectorizer(
                max_features=self.max_features,
                lowercase=True,
                strip_accents="unicode",
                ngram_range=(1, 2),
            )

        self.vectorizer.fit(texts)
        self._fitted = True
        return self

    def transform(self, texts: list[str]) -> np.ndarray:
        """Transform texts to feature vectors.

        Args:
            texts: List of text strings

        Returns:
            Feature matrix (n_samples, n_features)
        """
        if not self._fitted:
            raise ValueError("Featurizer must be fitted before transform")

        return self.vectorizer.transform(texts).toarray()

    def fit_transform(self, texts: list[str]) -> np.ndarray:
        """Fit and transform in one step.

        Args:
            texts: List of text strings

        Returns:
            Feature matrix (n_samples, n_features)
        """
        self.fit(texts)
        return self.transform(texts)

    def get_feature_names(self) -> list[str]:
        """Get feature names (vocabulary terms)."""
        if not self._fitted:
            return []
        return list(self.vectorizer.get_feature_names_out())


class FeatureExtractor:
    """General-purpose feature extractor for FiscFox ML models.

    Handles common feature extraction patterns:
    - Monetary values (log transform, normalization)
    - Dates (cyclical encoding)
    - Categories (one-hot encoding)
    - Text (TF-IDF)
    """

    def __init__(self):
        """Initialize feature extractor with default components."""
        self.vendor_featurizer = TextFeaturizer(max_features=100)
        self.description_featurizer = TextFeaturizer(max_features=200)
        self._fitted = False

    def fit(
        self,
        vendors: list[str] | None = None,
        descriptions: list[str] | None = None,
    ) -> "FeatureExtractor":
        """Fit text featurizers on training data.

        Args:
            vendors: List of vendor names for fitting
            descriptions: List of descriptions for fitting

        Returns:
            Self for chaining
        """
        if vendors:
            self.vendor_featurizer.fit(vendors)
        if descriptions:
            self.description_featurizer.fit(descriptions)
        self._fitted = True
        return self

    @staticmethod
    def log_transform(value: Decimal | float, offset: float = 1.0) -> float:
        """Apply log transformation to monetary values.

        Uses log(x + offset) to handle zero values.

        Args:
            value: Monetary value
            offset: Offset to add before log (default 1.0)

        Returns:
            Log-transformed value
        """
        return float(np.log(float(value) + offset))

    @staticmethod
    def normalize_amount(
        value: Decimal | float,
        min_val: float = 0.0,
        max_val: float = 10000.0,
    ) -> float:
        """Normalize monetary value to [0, 1] range.

        Args:
            value: Monetary value
            min_val: Minimum expected value
            max_val: Maximum expected value

        Returns:
            Normalized value between 0 and 1
        """
        val = float(value)
        if max_val == min_val:
            return 0.5
        normalized = (val - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))

    @staticmethod
    def encode_vat_rate(vat_rate: str) -> list[float]:
        """One-hot encode German VAT rate.

        Args:
            vat_rate: VAT rate string ("0.19", "0.07", "0.00")

        Returns:
            One-hot encoded list [is_standard, is_reduced, is_zero]
        """
        rate = str(vat_rate)
        return [
            1.0 if rate == "0.19" else 0.0,  # Standard 19%
            1.0 if rate == "0.07" else 0.0,  # Reduced 7%
            1.0 if rate == "0.00" else 0.0,  # Zero-rated
        ]

    @staticmethod
    def encode_category(
        category: str,
        all_categories: list[str],
    ) -> list[float]:
        """One-hot encode expense category.

        Args:
            category: Category string
            all_categories: List of all possible categories

        Returns:
            One-hot encoded list
        """
        return [1.0 if cat == category else 0.0 for cat in all_categories]

    @staticmethod
    def extract_date_features(d: date) -> list[float]:
        """Extract all temporal features from a date.

        Returns:
            List of features:
            - day_of_week_sin, day_of_week_cos
            - month_sin, month_cos
            - day_of_month_sin, day_of_month_cos
            - quarter_sin, quarter_cos
            - is_month_start, is_month_end
            - is_quarter_start, is_quarter_end
        """
        features = []

        # Cyclical encodings
        dow_sin, dow_cos = CyclicalEncoder.encode_day_of_week(d)
        features.extend([dow_sin, dow_cos])

        month_sin, month_cos = CyclicalEncoder.encode_month(d)
        features.extend([month_sin, month_cos])

        dom_sin, dom_cos = CyclicalEncoder.encode_day_of_month(d)
        features.extend([dom_sin, dom_cos])

        q_sin, q_cos = CyclicalEncoder.encode_quarter(d)
        features.extend([q_sin, q_cos])

        # Binary flags
        features.append(1.0 if d.day <= 3 else 0.0)  # Month start
        features.append(1.0 if d.day >= 28 else 0.0)  # Month end

        is_quarter_start = d.month in (1, 4, 7, 10) and d.day <= 3
        is_quarter_end = d.month in (3, 6, 9, 12) and d.day >= 28
        features.append(1.0 if is_quarter_start else 0.0)
        features.append(1.0 if is_quarter_end else 0.0)

        return features

    @staticmethod
    def days_between(d1: date, d2: date) -> int:
        """Calculate days between two dates.

        Args:
            d1: First date
            d2: Second date

        Returns:
            Number of days (positive if d2 > d1)
        """
        return (d2 - d1).days

    @staticmethod
    def extract_payment_features(
        invoice_date: date,
        due_date: date | None,
        paid_date: date | None,
        today: date | None = None,
    ) -> list[float]:
        """Extract features related to invoice payment timing.

        Args:
            invoice_date: Date invoice was created
            due_date: Payment due date
            paid_date: Actual payment date (None if unpaid)
            today: Current date (defaults to today)

        Returns:
            List of payment-related features
        """
        today = today or date.today()

        features = []

        # Payment terms (days between invoice and due date)
        if due_date:
            payment_terms = FeatureExtractor.days_between(invoice_date, due_date)
            features.append(float(payment_terms))
        else:
            features.append(14.0)  # Default 14 days

        # Days since invoice
        days_since_invoice = FeatureExtractor.days_between(invoice_date, today)
        features.append(float(days_since_invoice))

        # Days until due / days overdue
        if due_date:
            days_until_due = FeatureExtractor.days_between(today, due_date)
            features.append(float(days_until_due))
            features.append(1.0 if days_until_due < 0 else 0.0)  # Is overdue
        else:
            features.append(14.0)
            features.append(0.0)

        # Actual payment timing (for training)
        if paid_date:
            days_to_payment = FeatureExtractor.days_between(invoice_date, paid_date)
            features.append(float(days_to_payment))
            if due_date:
                days_late = FeatureExtractor.days_between(due_date, paid_date)
                features.append(float(max(0, days_late)))  # Days late
            else:
                features.append(0.0)
        else:
            features.append(-1.0)  # Unpaid marker
            features.append(-1.0)

        return features

    def extract_expense_features(
        self,
        vendor: str,
        description: str,
        amount_gross: Decimal,
        vat_rate: str,
        expense_date: date,
        category: str | None = None,
        all_categories: list[str] | None = None,
    ) -> np.ndarray:
        """Extract all features for expense categorization.

        Args:
            vendor: Vendor name
            description: Expense description
            amount_gross: Gross amount
            vat_rate: VAT rate string
            expense_date: Date of expense
            category: Current category (for training)
            all_categories: All possible categories

        Returns:
            Feature array
        """
        features = []

        # Text features
        if self._fitted:
            vendor_vec = self.vendor_featurizer.transform([vendor])[0]
            desc_vec = self.description_featurizer.transform([description])[0]
            features.extend(vendor_vec)
            features.extend(desc_vec)

        # Amount features
        features.append(self.log_transform(amount_gross))
        features.append(self.normalize_amount(amount_gross))

        # VAT encoding
        features.extend(self.encode_vat_rate(vat_rate))

        # Date features
        features.extend(self.extract_date_features(expense_date))

        return np.array(features)


class ClientFeatureExtractor:
    """Feature extraction for client-related predictions."""

    @staticmethod
    def extract_client_history_features(
        invoice_count: int,
        total_revenue: Decimal,
        avg_invoice_amount: Decimal,
        avg_days_to_payment: float,
        late_payment_rate: float,
        tenure_days: int,
        revenue_trend: float,  # Positive = growing
    ) -> list[float]:
        """Extract features from client history.

        Args:
            invoice_count: Total invoices sent to client
            total_revenue: Total revenue from client
            avg_invoice_amount: Average invoice amount
            avg_days_to_payment: Average days to receive payment
            late_payment_rate: Fraction of invoices paid late
            tenure_days: Days since first invoice
            revenue_trend: Revenue growth rate

        Returns:
            List of client features
        """
        return [
            float(invoice_count),
            FeatureExtractor.log_transform(total_revenue),
            FeatureExtractor.log_transform(avg_invoice_amount),
            float(avg_days_to_payment),
            float(late_payment_rate),
            float(tenure_days) / 365.0,  # Normalize to years
            float(revenue_trend),
        ]

    @staticmethod
    def extract_concentration_features(
        client_revenue: Decimal,
        total_revenue: Decimal,
        client_count: int,
    ) -> list[float]:
        """Extract income concentration features.

        Used for Scheinselbstaendigkeit risk analysis.

        Args:
            client_revenue: Revenue from this client
            total_revenue: Total revenue from all clients
            client_count: Total number of active clients

        Returns:
            List of concentration features
        """
        if total_revenue == 0:
            concentration = 0.0
        else:
            concentration = float(client_revenue / total_revenue)

        return [
            concentration,
            float(client_count),
            1.0 if concentration > 0.83 else 0.0,  # Scheinselbst flag
            1.0 if concentration > 0.50 else 0.0,  # High concentration flag
        ]
