"""Machine Learning module for FiscFox.

Provides ML-powered insights for German freelance tax management using TabPFN 2.5
and other models optimized for small tabular datasets.

Features:
1. Expense Auto-Categorization
2. Invoice Payment Risk Scoring
3. Cash Flow Forecasting
4. Mid-Quarter Tax Estimation
5. Audit Risk Scoring
6. Vendor Deduplication
7. Expense Anomaly Detection
8. Client Lifetime Value Prediction
9. Optimal Invoice Timing
10. Tax Deduction Opportunity Detection
"""

from src.ml.base import BaseMLPredictor, MLPrediction
from src.ml.features import CyclicalEncoder, FeatureExtractor, TextFeaturizer

__all__ = [
    "BaseMLPredictor",
    "MLPrediction",
    "FeatureExtractor",
    "CyclicalEncoder",
    "TextFeaturizer",
]
