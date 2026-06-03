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
            "random_state": 42
        }
        self.model = xgb.XGBRegressor(**self.params)
        self.explainer = None

    def fit(self, X: pd.DataFrame, y: pd.Series):
        """Fits the regressor to the feature matrix and target."""
        logger.info("Training XGBoost Regressor...")
        self.model.fit(X, y)
        
        # Initialize SHAP explainer after fitting
        self.explainer = shap.TreeExplainer(self.model)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict target values."""
        return self.model.predict(X)

    def calculate_shap_values(self, X: pd.DataFrame) -> np.ndarray:
        """
        Calculates SHAP values for features matrix X to understand 
        the impact of each technical indicator (RSI, MACD, etc) on predictions.
        """
        if not self.explainer:
            raise ValueError("Model must be trained before calculating SHAP values.")
        
        # Get SHAP values
        shap_values = self.explainer.shap_values(X)
        return shap_values

    def get_feature_importances(self, feature_names: list) -> Dict[str, float]:
        """Returns standard Gini/Gain feature importances."""
        importances = self.model.feature_importances_
        return dict(zip(feature_names, [float(val) for val in importances]))
