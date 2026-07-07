import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

logger = logging.getLogger(__name__)


class RandomForestModelWrapper:
    """
    Random Forest model wrapper for multi-feature forecasting.

    Mirrors the XGBoostModelWrapper interface so that the training
    pipeline can treat both models interchangeably.
    """

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        self.params: Dict[str, Any] = params or {
            "n_estimators": 200,
            "max_depth": 10,
            "min_samples_split": 5,
            "min_samples_leaf": 2,
            "random_state": 42,
            "n_jobs": -1,
        }
        self.model = RandomForestRegressor(**self.params)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Fits the regressor to the feature matrix and target."""
        logger.info("Training Random Forest Regressor...")
        self.model.fit(X, y)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict target values."""
        return self.model.predict(X)

    def get_feature_importances(self, feature_names: List[str]) -> Dict[str, float]:
        """Returns Gini/Mean Decrease Impurity feature importances."""
        importances = self.model.feature_importances_
        return dict(zip(feature_names, [float(val) for val in importances]))
