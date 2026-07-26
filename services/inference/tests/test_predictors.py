"""Unit tests for the model-specific predictors (all model stubs, no MLflow)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features import RANDOM_FOREST_FEATURE_LIST, XGBOOST_FEATURE_LIST
from predictors import (
    ArimaPredictor,
    GRUPredictor,
    RandomForestPredictor,
    XGBoostPredictor,
)


def _history(rows: int = 120) -> pd.DataFrame:
    index = np.arange(rows, dtype=float)
    close = 50.0 + 0.3 * index
    return pd.DataFrame(
        {
            "ts": pd.date_range("2025-01-01", periods=rows, freq="D", tz="UTC"),
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(rows, 1_000.0),
        }
    )


class _RecordingModel:
    """Stub estimator that records every frame passed to predict()."""

    def __init__(self, value: float = 42.0) -> None:
        self.value = value
        self.received: list[pd.DataFrame] = []

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        self.received.append(frame.copy())
        return np.array([self.value])


class _IdentityScaler:
    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        return np.asarray(frame, dtype=float)


def test_xgboost_predictor_feeds_scaled_named_features() -> None:
    model = _RecordingModel(value=42.0)
    predictor = XGBoostPredictor(model, _IdentityScaler())

    values = predictor.predict_steps(_history(), steps=3)

    assert values == [42.0, 42.0, 42.0]
    assert len(model.received) == 3
    for frame in model.received:
        assert list(frame.columns) == XGBOOST_FEATURE_LIST
        assert len(frame) == 1


def test_xgboost_predictor_iterates_on_its_own_predictions() -> None:
    class _EchoModel:
        """Predict close_lag_1 so each step reveals which bar it was fed."""

        def predict(self, frame: pd.DataFrame) -> np.ndarray:
            return np.array([float(frame["close_lag_1"].iloc[0])])

    history = _history()
    predictor = XGBoostPredictor(_EchoModel(), _IdentityScaler())
    values = predictor.predict_steps(history, steps=2)

    # Step 1 runs on the real latest bar (lag_1 = second-to-last close).
    # Step 2 must run on the synthetic bar appended from step 1's prediction,
    # so its lag_1 is the real latest close.
    assert values[0] == pytest.approx(history["close"].iloc[-2])
    assert values[1] == pytest.approx(history["close"].iloc[-1])


def test_random_forest_predictor_feeds_raw_features() -> None:
    model = _RecordingModel(value=77.0)
    predictor = RandomForestPredictor(model)

    values = predictor.predict_steps(_history(), steps=2)

    assert values == [77.0, 77.0]
    for frame in model.received:
        assert list(frame.columns) == RANDOM_FOREST_FEATURE_LIST
        assert len(frame) == 1


def test_gru_predictor_round_trips_scalers() -> None:
    torch = pytest.importorskip("torch", reason="torch not installed")
    from gru_net import GRUForecaster

    class _HalfScaler:
        """MinMax stand-in: scale = value / 100 both ways."""

        def transform(self, values: np.ndarray) -> np.ndarray:
            return np.asarray(values, dtype=float) / 100.0

        def inverse_transform(self, values: list[list[float]]) -> np.ndarray:
            return np.asarray(values, dtype=float) * 100.0

    torch.manual_seed(0)
    model = GRUForecaster(input_size=2, hidden_size=4, num_layers=1, dropout=0.0)
    predictor = GRUPredictor(
        model,
        feature_scaler=_HalfScaler(),
        target_scaler=_HalfScaler(),
        sequence_length=30,
        moving_average_window=7,
    )

    values = predictor.predict_steps(_history(60), steps=2)

    assert len(values) == 2
    assert all(np.isfinite(value) for value in values)


def test_gru_predictor_rejects_short_history() -> None:
    pytest.importorskip("torch", reason="torch not installed")
    from gru_net import GRUForecaster
    import torch

    torch.manual_seed(0)
    model = GRUForecaster(input_size=2, hidden_size=4, num_layers=1, dropout=0.0)
    predictor = GRUPredictor(model, _IdentityScaler(), _IdentityScaler())

    with pytest.raises(ValueError, match="at least"):
        predictor.predict_steps(_history(20), steps=1)


class _FakeArimaResults:
    def __init__(self) -> None:
        self.appended: list[float] = []

    def append(self, values: np.ndarray, refit: bool) -> "_FakeArimaResults":
        assert refit is False
        extended = _FakeArimaResults()
        extended.appended = self.appended + [float(v) for v in values]
        return extended

    def forecast(self, steps: int) -> np.ndarray:
        base = 100.0 + len(self.appended)
        return base + np.arange(steps, dtype=float)


def test_arima_predictor_appends_only_newer_bars() -> None:
    history = _history(50)
    cutoff = history["ts"].iloc[39]  # logged state ends at bar 40 of 50
    results = _FakeArimaResults()
    predictor = ArimaPredictor(results, history_end_ts=cutoff)

    values = predictor.predict_steps(history, steps=3)

    # 10 newer bars must be appended; the original results object stays unmutated.
    assert results.appended == []
    assert values == [110.0, 111.0, 112.0]


def test_arima_predictor_without_metadata_appends_nothing() -> None:
    predictor = ArimaPredictor(_FakeArimaResults(), history_end_ts=None)
    values = predictor.predict_steps(_history(30), steps=2)
    assert values == [100.0, 101.0]
