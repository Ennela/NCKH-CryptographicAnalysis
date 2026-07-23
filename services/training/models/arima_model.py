"""Small deterministic ARIMA wrapper for rolling one-step forecasts."""

from __future__ import annotations

import logging
import pickle
import warnings
from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

logger = logging.getLogger(__name__)

DEFAULT_ARIMA_ORDER: tuple[int, int, int] = (1, 1, 1)


class ARIMAResult(Protocol):
    """Subset of the statsmodels fitted-result API used by this wrapper."""

    def forecast(self, steps: int) -> Any:
        """Return forecasts for the requested number of steps."""

    def append(self, values: Sequence[float], refit: bool) -> ARIMAResult:
        """Return results with new observations appended to model state."""

    @property
    def nobs(self) -> int:
        """Return the number of observations held by the fitted result."""


def _finite_price_vector(
    prices: pd.Series | np.ndarray | Sequence[float],
) -> np.ndarray:
    """Return a non-empty one-dimensional vector containing finite prices."""
    values = np.asarray(prices, dtype=np.float64)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("ARIMA prices must be a non-empty one-dimensional vector.")
    if not np.isfinite(values).all():
        raise ValueError("ARIMA prices must contain only finite values.")
    return values


class ARIMABaseline:
    """Deterministic univariate ARIMA model with explicit state updates."""

    def __init__(self, p: int = 1, d: int = 1, q: int = 1) -> None:
        order = (p, d, q)
        if len(order) != 3 or any(value < 0 for value in order):
            raise ValueError("ARIMA order must contain three non-negative integers.")
        self.order = order
        self._model_fit: ARIMAResult | None = None

    @property
    def fitted_model(self) -> ARIMAResult:
        """Return the fitted statsmodels result used for MLflow logging."""
        if self._model_fit is None:
            raise ValueError("ARIMA model is not fitted.")
        return self._model_fit

    def fit(
        self,
        prices: pd.Series | np.ndarray | Sequence[float],
    ) -> ARIMABaseline:
        """Fit the fixed ARIMA order on chronological training close prices."""
        values = _finite_price_vector(prices)
        minimum_samples = max(self.order) + self.order[1] + 2
        if len(values) < minimum_samples:
            raise ValueError(
                f"ARIMA{self.order} requires at least {minimum_samples} prices."
            )

        logger.info(
            "Fitting deterministic ARIMA%s on %d chronological observations.",
            self.order,
            len(values),
        )
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                model = ARIMA(
                    values,
                    order=self.order,
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                )
                self._model_fit = model.fit()
        except Exception:
            logger.exception("Failed to fit ARIMA%s.", self.order)
            raise
        return self

    def forecast_one(self) -> float:
        """Forecast the close immediately after the latest observed history row."""
        return self.predict(steps=1)[0]

    def snapshot(self) -> ARIMABaseline:
        """Return an independent fitted-state snapshot via pickle round-trip."""
        try:
            serialized = pickle.dumps(
                self.fitted_model,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
            restored = pickle.loads(serialized)  # noqa: S301 - trusted local object
        except Exception:
            logger.exception("Failed to snapshot the fitted ARIMA state.")
            raise

        snapshot = ARIMABaseline(*self.order)
        snapshot._model_fit = restored
        if snapshot.fitted_model is self.fitted_model:
            raise RuntimeError(
                "ARIMA snapshot must not reuse the fitted result object."
            )
        if snapshot.observation_count != self.observation_count:
            raise RuntimeError("ARIMA snapshot changed the observation count.")
        return snapshot

    @property
    def observation_count(self) -> int:
        """Return the fitted history length used for artifact-boundary checks."""
        count = int(self.fitted_model.nobs)
        if count <= 0:
            raise ValueError("ARIMA fitted history must contain observations.")
        return count

    @property
    def last_observed_value(self) -> float:
        """Return the final fitted endog value for artifact-boundary checks."""
        model = getattr(self.fitted_model, "model", None)
        values = np.asarray(getattr(model, "endog", None), dtype=np.float64).reshape(-1)
        if values.size == 0 or not np.isfinite(values[-1]):
            raise ValueError("ARIMA fitted history has no finite final observation.")
        return float(values[-1])

    def predict(self, steps: int = 1) -> list[float]:
        """Return finite forecasts for compatibility with the legacy runner."""
        if steps <= 0:
            raise ValueError("ARIMA forecast steps must be positive.")
        forecast = np.asarray(
            self.fitted_model.forecast(steps=steps),
            dtype=np.float64,
        )
        if forecast.shape != (steps,) or not np.isfinite(forecast).all():
            raise ValueError("ARIMA forecast must contain one finite value per step.")
        return forecast.tolist()

    def update(self, actual_close: float) -> None:
        """Append one newly observed close without re-estimating fixed parameters."""
        actual = float(actual_close)
        if not np.isfinite(actual):
            raise ValueError("ARIMA history update must be finite.")
        try:
            self._model_fit = self.fitted_model.append([actual], refit=False)
        except Exception:
            logger.exception("Failed to append an observed close to ARIMA history.")
            raise
