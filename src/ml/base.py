"""Base ML predictor class with model persistence and retraining logic.

All ML predictors inherit from BaseMLPredictor for consistent:
- Model loading/saving
- Retraining triggers
- Confidence scoring
- Prediction caching
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

import numpy as np

# Type variable for prediction results
T = TypeVar("T")

# Default paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
MODELS_DIR = DATA_DIR / "models"


@dataclass
class MLPrediction(Generic[T]):
    """Standard ML prediction result with confidence scoring."""

    value: T
    confidence: float  # 0.0 to 1.0
    model_version: str
    timestamp: datetime

    @property
    def is_confident(self) -> bool:
        """Check if prediction meets confidence threshold (80%)."""
        return self.confidence >= 0.8

    @property
    def confidence_level(self) -> str:
        """Human-readable confidence level."""
        if self.confidence >= 0.9:
            return "high"
        elif self.confidence >= 0.7:
            return "medium"
        else:
            return "low"


class BaseMLPredictor(ABC):
    """Abstract base class for all FiscFox ML predictors.

    Provides:
    - Model persistence (load/save)
    - Automatic retraining triggers
    - Version tracking
    - Confidence calibration

    Subclasses must implement:
    - _create_default_model()
    - _extract_features()
    - predict()
    """

    # Class-level configuration (override in subclasses)
    MODEL_NAME: str = "base"
    RETRAIN_SAMPLE_THRESHOLD: int = 50  # Retrain after N new samples
    RETRAIN_DAYS_THRESHOLD: int = 30  # Retrain after N days
    MIN_TRAINING_SAMPLES: int = 20  # Minimum samples for training

    def __init__(self, model_path: Path | None = None):
        """Initialize predictor with optional custom model path.

        Args:
            model_path: Custom path for model file. Defaults to
                        data/models/{MODEL_NAME}.pkl
        """
        self.model_path = model_path or (MODELS_DIR / f"{self.MODEL_NAME}.pkl")
        self.model: Any = None
        self.last_trained: datetime | None = None
        self.training_samples: int = 0
        self.version: str = "1.0.0"

        # Ensure models directory exists
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

        # Load existing model or create default
        self._load_or_create_model()

    def _load_or_create_model(self) -> None:
        """Load existing model from disk or create new one."""
        if self.model_path.exists():
            self._load_model()
        else:
            self.model = self._create_default_model()
            self.last_trained = None
            self.training_samples = 0

    def _load_model(self) -> None:
        """Load model and metadata from disk."""
        try:
            import joblib

            data = joblib.load(self.model_path)

            if isinstance(data, dict):
                self.model = data.get("model")
                self.last_trained = data.get("last_trained")
                self.training_samples = data.get("training_samples", 0)
                self.version = data.get("version", "1.0.0")
            else:
                # Legacy format: just the model
                self.model = data
                self.last_trained = None
                self.training_samples = 0

        except Exception as e:
            print(f"Warning: Could not load model from {self.model_path}: {e}")
            self.model = self._create_default_model()

    def _save_model(self) -> None:
        """Save model and metadata to disk."""
        import joblib

        data = {
            "model": self.model,
            "last_trained": self.last_trained,
            "training_samples": self.training_samples,
            "version": self.version,
        }
        joblib.dump(data, self.model_path)

    @abstractmethod
    def _create_default_model(self) -> Any:
        """Create a new untrained model instance.

        Returns:
            New model instance (TabPFN, sklearn, etc.)
        """
        pass

    @abstractmethod
    def _extract_features(self, data: Any) -> np.ndarray:
        """Extract features from input data.

        Args:
            data: Input data (varies by predictor type)

        Returns:
            Feature array suitable for model input
        """
        pass

    def needs_retraining(self, new_samples: int = 0) -> bool:
        """Check if model should be retrained.

        Triggers retraining if:
        - Never trained
        - Sample threshold exceeded
        - Time threshold exceeded

        Args:
            new_samples: Number of new samples since last training

        Returns:
            True if retraining is recommended
        """
        if self.last_trained is None:
            return True

        # Check sample threshold
        if new_samples >= self.RETRAIN_SAMPLE_THRESHOLD:
            return True

        # Check time threshold
        days_since_training = (datetime.now() - self.last_trained).days
        if days_since_training >= self.RETRAIN_DAYS_THRESHOLD:
            return True

        return False

    def train(self, X: np.ndarray, y: np.ndarray) -> dict[str, Any]:
        """Train the model on provided data.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Target array (n_samples,)

        Returns:
            Training metrics dict
        """
        if len(X) < self.MIN_TRAINING_SAMPLES:
            return {
                "success": False,
                "error": f"Insufficient samples: {len(X)} < {self.MIN_TRAINING_SAMPLES}",
            }

        try:
            self.model.fit(X, y)
            self.last_trained = datetime.now()
            self.training_samples = len(X)
            self._save_model()

            return {
                "success": True,
                "samples": len(X),
                "timestamp": self.last_trained.isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_confidence(self, probabilities: np.ndarray) -> float:
        """Calculate confidence score from prediction probabilities.

        Uses maximum probability as confidence, with calibration.

        Args:
            probabilities: Probability distribution from predict_proba

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if probabilities is None or len(probabilities) == 0:
            return 0.0

        max_prob = float(np.max(probabilities))

        # Apply light calibration (TabPFN tends to be well-calibrated)
        # but we slightly discount very high confidence
        if max_prob > 0.95:
            return 0.95  # Cap at 95% to maintain humility
        return max_prob

    def get_model_info(self) -> dict[str, Any]:
        """Get model metadata and status.

        Returns:
            Dict with model info (version, training date, samples, etc.)
        """
        return {
            "name": self.MODEL_NAME,
            "version": self.version,
            "path": str(self.model_path),
            "exists": self.model_path.exists(),
            "last_trained": self.last_trained.isoformat() if self.last_trained else None,
            "training_samples": self.training_samples,
            "needs_retraining": self.needs_retraining(),
        }


class ClassificationPredictor(BaseMLPredictor):
    """Base class for classification predictors.

    Extends BaseMLPredictor with classification-specific methods:
    - predict_with_alternatives() for top-k predictions
    - classes attribute for label names
    - is_trained property

    Subclasses must implement:
    - _extract_features()
    - _extract_labels()
    """

    def __init__(
        self,
        model_name: str,
        classes: list[str],
        models_dir: Path | None = None,
        min_samples_to_train: int = 20,
        retrain_every_n_samples: int = 50,
    ):
        """Initialize classification predictor.

        Args:
            model_name: Name for model persistence
            classes: List of class labels
            models_dir: Directory for model storage
            min_samples_to_train: Minimum samples required to train
            retrain_every_n_samples: Retrain after this many new samples
        """
        self.classes = classes
        self.min_samples_to_train = min_samples_to_train
        self.MODEL_NAME = model_name
        self.RETRAIN_SAMPLE_THRESHOLD = retrain_every_n_samples
        self.MIN_TRAINING_SAMPLES = min_samples_to_train

        model_path = None
        if models_dir:
            models_dir.mkdir(parents=True, exist_ok=True)
            model_path = models_dir / f"{model_name}.pkl"

        super().__init__(model_path=model_path)

    @property
    def is_trained(self) -> bool:
        """Check if model has been trained."""
        return self.last_trained is not None and self.training_samples > 0

    def _create_default_model(self) -> Any:
        """Create TabPFN classifier as default model."""
        try:
            from tabpfn import TabPFNClassifier

            return TabPFNClassifier(
                device="cpu",
                N_ensemble_configurations=16,
            )
        except ImportError:
            # Fallback to sklearn if TabPFN not available
            from sklearn.ensemble import RandomForestClassifier

            return RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
            )

    @abstractmethod
    def _extract_labels(self, data: Any) -> np.ndarray:
        """Extract class labels from training data.

        Args:
            data: Training data

        Returns:
            Array of label indices
        """
        pass

    def train(self, training_data: Any) -> dict[str, Any]:
        """Train the classifier.

        Args:
            training_data: Data with features and labels

        Returns:
            Training metrics dict
        """
        X = self._extract_features(training_data)
        y = self._extract_labels(training_data)
        return super().train(X, y)

    async def predict_with_alternatives(
        self,
        data: Any,
        top_k: int = 3,
    ) -> list[tuple[str, float]]:
        """Predict class with top-k alternatives.

        Args:
            data: Input data for prediction
            top_k: Number of top predictions to return

        Returns:
            List of (class_name, confidence) tuples, sorted by confidence
        """
        X = self._extract_features(data)

        try:
            probas = self.model.predict_proba(X)[0]
        except Exception:
            # Fallback: return first class with low confidence
            return [(self.classes[0], 0.1)]

        # Get top-k indices
        top_indices = np.argsort(probas)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if idx < len(self.classes):
                results.append((self.classes[idx], float(probas[idx])))

        return results


class TabPFNMixin:
    """Mixin providing TabPFN-specific functionality.

    Use with BaseMLPredictor subclasses for TabPFN models.
    """

    def _create_tabpfn_classifier(self, n_estimators: int = 16) -> Any:
        """Create TabPFN classifier instance.

        Args:
            n_estimators: Number of ensemble configurations

        Returns:
            TabPFNClassifier instance
        """
        try:
            from tabpfn import TabPFNClassifier

            return TabPFNClassifier(
                device="cpu",
                N_ensemble_configurations=n_estimators,
            )
        except ImportError:
            # Fallback to sklearn if TabPFN not available
            from sklearn.ensemble import RandomForestClassifier

            print("Warning: TabPFN not available, using RandomForest fallback")
            return RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
            )

    def _create_tabpfn_regressor(self, n_estimators: int = 16) -> Any:
        """Create TabPFN regressor instance.

        Args:
            n_estimators: Number of ensemble configurations

        Returns:
            TabPFNRegressor instance
        """
        try:
            from tabpfn import TabPFNRegressor

            return TabPFNRegressor(
                device="cpu",
                N_ensemble_configurations=n_estimators,
            )
        except ImportError:
            # Fallback to sklearn if TabPFN not available
            from sklearn.ensemble import RandomForestRegressor

            print("Warning: TabPFN not available, using RandomForest fallback")
            return RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42,
            )
