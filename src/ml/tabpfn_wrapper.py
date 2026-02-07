"""TabPFN 2.5 wrapper optimized for FiscFox use cases.

TabPFN (Tabular Prior-Fitted Network) is a transformer-based model
pre-trained on millions of synthetic datasets. It excels at:
- Small datasets (100-10,000 rows)
- Zero-shot or few-shot learning
- Mixed feature types (categorical + numerical)
- Built-in uncertainty quantification

For FiscFox, TabPFN is ideal because:
- Single-user app = small dataset per user
- No massive training data needed
- Fast inference (~100ms)
- Well-calibrated confidence scores
"""

from typing import Any

import numpy as np


class FiscFoxTabPFN:
    """TabPFN wrapper with fallbacks for FiscFox ML features.

    Provides factory methods for creating TabPFN classifiers and regressors
    with appropriate default settings. Falls back to sklearn models if
    TabPFN is not installed.
    """

    _tabpfn_available: bool | None = None

    @classmethod
    def is_available(cls) -> bool:
        """Check if TabPFN is installed and functional."""
        if cls._tabpfn_available is None:
            try:
                from tabpfn import TabPFNClassifier

                cls._tabpfn_available = True
            except ImportError:
                cls._tabpfn_available = False
        return cls._tabpfn_available

    @classmethod
    def create_classifier(
        cls,
        n_estimators: int = 16,
        device: str = "cpu",
    ) -> Any:
        """Create a TabPFN classifier or sklearn fallback.

        Args:
            n_estimators: Number of ensemble configurations (TabPFN)
                         or trees (RandomForest fallback)
            device: Device for TabPFN ("cpu" or "cuda")

        Returns:
            Classifier instance with fit/predict/predict_proba interface
        """
        if cls.is_available():
            from tabpfn import TabPFNClassifier

            return TabPFNClassifier(
                device=device,
                N_ensemble_configurations=n_estimators,
            )
        else:
            from sklearn.ensemble import RandomForestClassifier

            return RandomForestClassifier(
                n_estimators=n_estimators * 6,  # More trees for comparable perf
                max_depth=12,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            )

    @classmethod
    def create_regressor(
        cls,
        n_estimators: int = 16,
        device: str = "cpu",
    ) -> Any:
        """Create a TabPFN regressor or sklearn fallback.

        Args:
            n_estimators: Number of ensemble configurations (TabPFN)
                         or trees (RandomForest fallback)
            device: Device for TabPFN ("cpu" or "cuda")

        Returns:
            Regressor instance with fit/predict interface
        """
        if cls.is_available():
            from tabpfn import TabPFNRegressor

            return TabPFNRegressor(
                device=device,
                N_ensemble_configurations=n_estimators,
            )
        else:
            from sklearn.ensemble import RandomForestRegressor

            return RandomForestRegressor(
                n_estimators=n_estimators * 6,
                max_depth=12,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            )

    @classmethod
    def create_anomaly_detector(cls) -> Any:
        """Create an Isolation Forest for anomaly detection.

        Note: TabPFN doesn't have a native anomaly detector,
        so we always use sklearn's IsolationForest.

        Returns:
            IsolationForest instance
        """
        from sklearn.ensemble import IsolationForest

        return IsolationForest(
            n_estimators=100,
            contamination=0.1,  # Expected fraction of anomalies
            max_samples="auto",
            random_state=42,
            n_jobs=-1,
        )


class TabPFNEnsemble:
    """Ensemble combining TabPFN with other models for robustness.

    Useful when you want to combine TabPFN's strengths with
    traditional ML models for improved reliability.
    """

    def __init__(
        self,
        tabpfn_weight: float = 0.6,
        fallback_weight: float = 0.4,
        task: str = "classification",
    ):
        """Initialize ensemble.

        Args:
            tabpfn_weight: Weight for TabPFN predictions
            fallback_weight: Weight for fallback model predictions
            task: "classification" or "regression"
        """
        self.tabpfn_weight = tabpfn_weight
        self.fallback_weight = fallback_weight
        self.task = task

        if task == "classification":
            self.tabpfn = FiscFoxTabPFN.create_classifier()
            from sklearn.ensemble import GradientBoostingClassifier

            self.fallback = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                random_state=42,
            )
        else:
            self.tabpfn = FiscFoxTabPFN.create_regressor()
            from sklearn.ensemble import GradientBoostingRegressor

            self.fallback = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=5,
                random_state=42,
            )

        self._fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TabPFNEnsemble":
        """Fit both models.

        Args:
            X: Feature matrix
            y: Target array

        Returns:
            Self for chaining
        """
        self.tabpfn.fit(X, y)
        self.fallback.fit(X, y)
        self._fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions using weighted ensemble.

        Args:
            X: Feature matrix

        Returns:
            Predictions (weighted average for regression,
            argmax of weighted probabilities for classification)
        """
        if not self._fitted:
            raise ValueError("Ensemble must be fitted before predict")

        if self.task == "regression":
            tabpfn_pred = self.tabpfn.predict(X)
            fallback_pred = self.fallback.predict(X)
            return (
                self.tabpfn_weight * tabpfn_pred + self.fallback_weight * fallback_pred
            )
        else:
            probs = self.predict_proba(X)
            return np.argmax(probs, axis=1)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Get probability predictions (classification only).

        Args:
            X: Feature matrix

        Returns:
            Probability matrix (n_samples, n_classes)
        """
        if self.task != "classification":
            raise ValueError("predict_proba only available for classification")

        if not self._fitted:
            raise ValueError("Ensemble must be fitted before predict_proba")

        tabpfn_probs = self.tabpfn.predict_proba(X)
        fallback_probs = self.fallback.predict_proba(X)

        return (
            self.tabpfn_weight * tabpfn_probs + self.fallback_weight * fallback_probs
        )


def get_model_status() -> dict[str, Any]:
    """Get status of ML model availability.

    Returns:
        Dict with availability status and versions
    """
    status = {
        "tabpfn_available": FiscFoxTabPFN.is_available(),
        "sklearn_available": True,  # Always available
    }

    if FiscFoxTabPFN.is_available():
        try:
            import tabpfn

            status["tabpfn_version"] = getattr(tabpfn, "__version__", "unknown")
        except Exception:
            status["tabpfn_version"] = "unknown"

    try:
        import sklearn

        status["sklearn_version"] = sklearn.__version__
    except Exception:
        status["sklearn_version"] = "unknown"

    return status
