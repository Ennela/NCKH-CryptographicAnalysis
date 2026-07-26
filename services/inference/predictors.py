"""Model-specific predictors that turn OHLCV history into price forecasts.

Each predictor wraps the artifacts produced by its training entrypoint
(services/training/train_<model>.py) and exposes one method::

    predict_steps(history: pd.DataFrame, steps: int) -> list[float]

``history`` is a chronological OHLCV frame (columns ts/open/high/low/close/
volume, ts tz-aware UTC ascending). The returned list holds absolute close
prices in original units, one per future step.

Multi-step notes:
- XGBoost / Random Forest / GRU are trained for horizon 1. Steps beyond the
  first are produced iteratively by appending a synthetic bar built from the
  previous prediction (open=high=low=close=prediction, volume carried
  forward) and recomputing features. This is a documented approximation.
- ARIMA forecasts the full horizon natively via ``forecast(steps)`` after
  appending any bars newer than its logged training history.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import numpy as np
import pandas as pd

from features import (
    RANDOM_FOREST_FEATURE_LIST,
    XGBOOST_FEATURE_LIST,
    build_random_forest_live_features,
    build_xgboost_live_features,
    latest_feature_row,
)

logger = logging.getLogger(__name__)

GRU_SEQUENCE_LENGTH = 30
GRU_MOVING_AVERAGE_WINDOW = 7


class Predictor(Protocol):
    """Common protocol implemented by all model predictors."""

    def predict_steps(self, history: pd.DataFrame, steps: int) -> list[float]: ...


def _append_synthetic_bar(frame: pd.DataFrame, predicted_close: float) -> pd.DataFrame:
    """Extend the OHLCV frame with one synthetic bar built from a prediction."""
    last = frame.iloc[-1]
    step = frame["ts"].iloc[-1] - frame["ts"].iloc[-2]
    synthetic = {
        "ts": last["ts"] + step,
        "open": predicted_close,
        "high": predicted_close,
        "low": predicted_close,
        "close": predicted_close,
        "volume": float(last["volume"]),
    }
    return pd.concat([frame, pd.DataFrame([synthetic])], ignore_index=True)


class XGBoostPredictor:
    """Serve the raw XGBRegressor + StandardScaler logged by train_xgboost."""

    def __init__(self, model: Any, scaler: Any) -> None:
        self.model = model
        self.scaler = scaler

    def predict_steps(self, history: pd.DataFrame, steps: int) -> list[float]:
        frame = history.loc[:, ["ts", "open", "high", "low", "close", "volume"]].copy()
        predictions: list[float] = []
        for _ in range(steps):
            featured = build_xgboost_live_features(frame)
            row = latest_feature_row(featured, XGBOOST_FEATURE_LIST)
            scaled = self.scaler.transform(row)
            scaled_frame = pd.DataFrame(scaled, columns=XGBOOST_FEATURE_LIST)
            value = float(np.asarray(self.model.predict(scaled_frame)).reshape(-1)[0])
            predictions.append(value)
            frame = _append_synthetic_bar(frame, value)
        return predictions


class RandomForestPredictor:
    """Serve the raw RandomForestRegressor logged by train_random_forest."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def predict_steps(self, history: pd.DataFrame, steps: int) -> list[float]:
        frame = history.loc[:, ["ts", "open", "high", "low", "close", "volume"]].copy()
        predictions: list[float] = []
        for _ in range(steps):
            featured = build_random_forest_live_features(frame)
            row = latest_feature_row(featured, RANDOM_FOREST_FEATURE_LIST)
            value = float(np.asarray(self.model.predict(row)).reshape(-1)[0])
            predictions.append(value)
            frame = _append_synthetic_bar(frame, value)
        return predictions


class GRUPredictor:
    """Serve the GRUForecaster + MinMax scalers logged by train_gru.

    Input contract (train_gru.py): sequences of the last 30 scaled
    (close, moving_average_7) rows inclusive of the current bar; output is a
    MinMax-scaled next close that must be inverse-transformed with the
    target scaler.
    """

    def __init__(
        self,
        model: Any,
        feature_scaler: Any,
        target_scaler: Any,
        sequence_length: int = GRU_SEQUENCE_LENGTH,
        moving_average_window: int = GRU_MOVING_AVERAGE_WINDOW,
    ) -> None:
        self.model = model
        self.feature_scaler = feature_scaler
        self.target_scaler = target_scaler
        self.sequence_length = sequence_length
        self.moving_average_window = moving_average_window

    def predict_steps(self, history: pd.DataFrame, steps: int) -> list[float]:
        import torch

        min_rows = self.sequence_length + self.moving_average_window - 1
        closes = history["close"].astype(float).reset_index(drop=True)
        if len(closes) < min_rows:
            raise ValueError(
                f"GRU needs at least {min_rows} bars of history, got {len(closes)}."
            )

        self.model.eval()
        predictions: list[float] = []
        for _ in range(steps):
            moving_average = closes.rolling(self.moving_average_window).mean()
            features = pd.DataFrame(
                {"close": closes, "moving_average": moving_average}
            ).tail(self.sequence_length)
            scaled = self.feature_scaler.transform(
                features.to_numpy(dtype=np.float64)
            ).astype(np.float32)
            inputs = torch.from_numpy(scaled).unsqueeze(0)
            with torch.no_grad():
                scaled_prediction = self.model(inputs).reshape(-1)[0].item()
            value = float(
                self.target_scaler.inverse_transform([[scaled_prediction]])[0][0]
            )
            predictions.append(value)
            closes = pd.concat([closes, pd.Series([value])], ignore_index=True)
        return predictions


class ArimaPredictor:
    """Serve the statsmodels ARIMAResults logged by train_arima.

    The logged state ends at ``history_end_ts`` (pre-test deployable model).
    Bars observed after that timestamp are appended with ``refit=False``
    (state advances, parameters stay fixed) before forecasting — the same
    rolling mechanism used at evaluation time.
    """

    def __init__(self, results: Any, history_end_ts: pd.Timestamp | None) -> None:
        self.results = results
        self.history_end_ts = history_end_ts

    def predict_steps(self, history: pd.DataFrame, steps: int) -> list[float]:
        results = self.results
        if self.history_end_ts is not None:
            newer = history.loc[history["ts"] > self.history_end_ts, "close"]
        else:
            newer = history["close"].iloc[0:0]
        new_values = newer.astype(float).to_numpy()
        if len(new_values) > 0:
            results = results.append(new_values, refit=False)
            logger.info(
                "ARIMA state advanced by %d observations past %s",
                len(new_values),
                self.history_end_ts,
            )
        forecast = np.asarray(results.forecast(steps=steps), dtype=float).reshape(-1)
        return [float(value) for value in forecast]
