import logging
import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from typing import List

logger = logging.getLogger(__name__)

class ARIMABaseline:
    """
    ARIMA model wrapper for univariate time series forecasting.
    """
    def __init__(self, p: int = 1, d: int = 1, q: int = 1):
        self.order = (p, d, q)
        self.model_fit = None

    def fit(self, prices: pd.Series):
        """Fits the ARIMA model on closing price series."""
        logger.info(f"Fitting ARIMA{self.order} model...")
        # TODO: Handle non-stationary series warning
        try:
            model = ARIMA(prices.values, order=self.order)
            self.model_fit = model.fit()
        except Exception as e:
            logger.error(f"Failed to fit ARIMA model: {str(e)}")
            raise e

    def predict(self, steps: int = 5) -> List[float]:
        """
        Forecasts the next N steps.
        """
        if not self.model_fit:
            raise ValueError("Model is not fitted yet.")
        
        forecast = self.model_fit.forecast(steps=steps)
        return list(forecast)
