import logging
import xgboost as xgb
import shap
import pandas as pd
import numpy as np
from typing import Dict, Any

logger = logging.getLogger(__name__)


class XGBoostModelWrapper:
    """
    XGBoost model wrapper for multi-feature forecasting.
    Includes SHAP integration for model explainability.
    """

    def __init__(self, params: Dict[str, Any] = None):
        self.params = params or {
            "n_estimators": 100,
            "max_depth": 5,
            "learning_rate": 0.1,
            "objective": "reg:squarederror",
            "random_state": 42,
        }
        self.model = xgb.XGBRegressor(**self.params)
        self.explainer = None

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        X_val: pd.DataFrame | None = None,
        y_val: pd.Series | None = None,
        early_stopping_rounds: int = 50,
    ) -> None:
        """Fits the regressor to the feature matrix and target."""
        logger.info("Training XGBoost Regressor...")
        if (X_val is None) != (y_val is None):
            raise ValueError("X_val and y_val must be provided together.")
        self.explainer = None

        if X_val is not None and y_val is not None:
            self.model.set_params(early_stopping_rounds=early_stopping_rounds)
            self.model.fit(
                X,
                y,
                eval_set=[(X_val, y_val)],
            )
        else:
            # Clear stale state when the same wrapper is fitted again without
            # a validation set. XGBoost requires an eval_set when this option
            # is enabled.
            self.model.set_params(early_stopping_rounds=None)
            self.model.fit(X, y)

    def save(self, path: str) -> None:
        """Save the fitted model in XGBoost's native format."""
        self.model.save_model(path)

    def load(self, path: str) -> None:
        """Load a native XGBoost model and reset its lazy SHAP explainer."""
        self.model.load_model(path)
        self.explainer = None

    @property
    def best_iteration(self) -> int | None:
        """Return the best boosting iteration when early stopping was used."""
        return getattr(self.model, "best_iteration", None)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict target values."""
        return self.model.predict(X)

    def calculate_shap_values(self, X: pd.DataFrame) -> np.ndarray:
        """
        Calculates SHAP values for features matrix X to understand
        the impact of each technical indicator (RSI, MACD, etc) on predictions.
        """
        if self.explainer is None:
            self.explainer = shap.TreeExplainer(self.model)

        shap_values = self.explainer.shap_values(X)
        return shap_values

    def get_feature_importances(self, feature_names: list) -> Dict[str, float]:
        """Returns standard Gini/Gain feature importances."""
        importances = self.model.feature_importances_
        return dict(zip(feature_names, [float(val) for val in importances]))
