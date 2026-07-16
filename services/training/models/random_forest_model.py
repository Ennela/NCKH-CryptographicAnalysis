"""Random Forest model wrapper for multi-feature price forecasting.

Mirrors the ``XGBoostModelWrapper`` interface so the training pipeline can
treat both models interchangeably.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

logger = logging.getLogger(__name__)


class RandomForestModelWrapper:
    """Thin wrapper around :class:`sklearn.ensemble.RandomForestRegressor`.

    Provides ``fit``, ``predict``, ``save``, ``load``, ``get_params``, and
    ``get_feature_importances`` so the Random Forest training pipeline can
    reuse the same helper functions as the XGBoost pipeline.
    """

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        """Initialise the wrapper.

        Input:
            params: keyword arguments forwarded to
                :class:`~sklearn.ensemble.RandomForestRegressor`.
                Defaults to a reasonable starting configuration.
        """
        self.params: dict[str, Any] = params or {
            "n_estimators": 200,
            "max_depth": 10,
            "min_samples_split": 5,
            "min_samples_leaf": 2,
            "max_features": 1.0,
            "random_state": 42,
            "n_jobs": -1,
        }
        self.model: RandomForestRegressor = RandomForestRegressor(**self.params)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Fit the regressor to the feature matrix and target series.

        Input:
            X: feature matrix (n_samples × n_features).
            y: target series (n_samples,).
        """
        logger.info(
            "Training RandomForestRegressor with params: %s", self.params
        )
        self.model.fit(X, y)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Return predicted target values.

        Input:
            X: feature matrix (n_samples × n_features).

        Output:
            Numpy array of shape (n_samples,).
        """
        return self.model.predict(X)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Serialise the fitted model to disk via joblib.

        Input:
            path: file path (string or Path) to write the model.
        """
        joblib.dump(self.model, path)
        logger.info("RandomForestRegressor saved to %s", path)

    def load(self, path: str | Path) -> None:
        """Deserialise a previously saved model from disk.

        Input:
            path: file path (string or Path) to read the model from.
        """
        self.model = joblib.load(path)
        logger.info("RandomForestRegressor loaded from %s", path)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_params(self) -> dict[str, Any]:
        """Return the *live* parameters from the fitted sklearn estimator.

        Mirrors :meth:`XGBoostModelWrapper.model.get_params` so that
        ``log_training_run`` can log the actual (post-fit) configuration.

        Output:
            Dict of parameter name → value (``None`` values excluded by
            the caller).
        """
        return self.model.get_params()

    def get_feature_importances(self, feature_names: list[str]) -> dict[str, float]:
        """Return Mean Decrease Impurity (Gini) feature importances.

        Input:
            feature_names: ordered list of feature column names.  Must
                match the columns used during ``fit``.

        Output:
            Dict mapping feature name → importance score.
        """
        importances = self.model.feature_importances_
        return dict(zip(feature_names, [float(v) for v in importances]))
