"""Random Forest model wrapper for next-close forecasting."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

logger = logging.getLogger(__name__)

DEFAULT_RANDOM_FOREST_PARAMS: dict[str, Any] = {
    "n_estimators": 200,
    "max_depth": 10,
    "min_samples_split": 5,
    "min_samples_leaf": 2,
    "random_state": 42,
    "n_jobs": -1,
}


class RandomForestModelWrapper:
    """
    Random Forest model wrapper for multi-feature forecasting.

    Mirrors the XGBoostModelWrapper interface so that the training
    pipeline can treat both models interchangeably.
    """

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params = dict(DEFAULT_RANDOM_FOREST_PARAMS if params is None else params)
        self.model = RandomForestRegressor(**self.params)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Fits the regressor to the feature matrix and target."""
        logger.info("Training Random Forest Regressor...")
        self.model.fit(X, y)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict target values."""
        return np.asarray(self.model.predict(X), dtype=np.float64).reshape(-1)

    def save(self, path: str | Path) -> None:
        """Serialize the fitted estimator with joblib."""
        joblib.dump(self.model, path)

    def load(self, path: str | Path) -> None:
        """Load a serialized RandomForestRegressor."""
        loaded_model = joblib.load(path)
        if not isinstance(loaded_model, RandomForestRegressor):
            raise TypeError("Serialized artifact is not a RandomForestRegressor.")
        self.model = loaded_model
        self.params = dict(self.model.get_params())

    def get_params(self) -> dict[str, Any]:
        """Return live estimator hyperparameters."""
        return dict(self.model.get_params())

    def get_feature_importances(self, feature_names: list[str]) -> dict[str, float]:
        """Returns Gini/Mean Decrease Impurity feature importances."""
        importances = self.model.feature_importances_
        return dict(zip(feature_names, [float(val) for val in importances]))
