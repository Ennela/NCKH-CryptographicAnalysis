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


class _HalfScaler:
    """MinMax stand-in: scale = value / 100 both ways (same mapping for all columns)."""

    def transform(self, values: np.ndarray) -> np.ndarray:
        return np.asarray(values, dtype=float) / 100.0

    def inverse_transform(self, values: list[list[float]]) -> np.ndarray:
        return np.asarray(values, dtype=float) * 100.0


def _gru_model(torch, seed: int = 0):
    from gru_net import GRUForecaster

    torch.manual_seed(seed)
    model = GRUForecaster(input_size=8, hidden_size=4, num_layers=1, dropout=0.0)
    # Give the zero-initialised residual head a non-trivial correction.
    with torch.no_grad():
        model.output_layer.weight.fill_(0.05)
        model.output_layer.bias.fill_(0.01)
    return model


def test_gru_predictor_round_trips_scalers() -> None:
    torch = pytest.importorskip("torch", reason="torch not installed")

    predictor = GRUPredictor(
        _gru_model(torch),
        feature_scaler=_HalfScaler(),
        target_scaler=_HalfScaler(),
        sequence_length=7,
    )

    values = predictor.predict_steps(_history(60), steps=2)

    assert len(values) == 2
    assert all(np.isfinite(value) for value in values)


def test_gru_predictor_feeds_eight_features_in_training_order() -> None:
    """The window handed to the network must match train_gru.FEATURE_LIST."""
    torch = pytest.importorskip("torch", reason="torch not installed")
    from features import GRU_FEATURE_LIST, build_gru_live_features

    class _RecordingScaler(_HalfScaler):
        def __init__(self) -> None:
            self.received: list[np.ndarray] = []

        def transform(self, values: np.ndarray) -> np.ndarray:
            self.received.append(np.asarray(values, dtype=float))
            return super().transform(values)

    scaler = _RecordingScaler()
    predictor = GRUPredictor(
        _gru_model(torch), scaler, _HalfScaler(), sequence_length=7
    )
    history = _history(60)

    predictor.predict_steps(history, steps=1)

    assert len(scaler.received) == 1
    window = scaler.received[0]
    assert window.shape == (7, len(GRU_FEATURE_LIST)) == (7, 8)
    expected = (
        build_gru_live_features(history["close"]).loc[:, GRU_FEATURE_LIST].tail(7)
    )
    np.testing.assert_allclose(window, expected.to_numpy(dtype=float))
    # Column 0 is the raw close of the newest bar — what the residual head adds to.
    assert window[-1, 0] == history["close"].iloc[-1]


def test_gru_predictor_rejects_short_history() -> None:
    torch = pytest.importorskip("torch", reason="torch not installed")

    predictor = GRUPredictor(
        _gru_model(torch), _HalfScaler(), _HalfScaler(), sequence_length=7
    )

    assert predictor.min_history_rows == 20
    with pytest.raises(ValueError, match="at least 20"):
        predictor.predict_steps(_history(19), steps=1)
    assert len(predictor.predict_steps(_history(20), steps=1)) == 1


def test_gru_net_matches_training_forecaster() -> None:
    """The inference mirror must reproduce the training network bit-for-bit."""
    torch = pytest.importorskip("torch", reason="torch not installed")
    training = pytest.importorskip(
        "services.training.models.gru_model", reason="training package not importable"
    )
    from gru_net import GRUForecaster

    torch.manual_seed(1)
    reference = training.GRUForecaster(
        input_size=8, hidden_size=16, num_layers=1, dropout=0.0
    )
    with torch.no_grad():
        reference.output_layer.weight.normal_()
        reference.output_layer.bias.normal_()
    mirror = GRUForecaster(input_size=8, hidden_size=16, num_layers=1, dropout=0.0)
    mirror.load_state_dict(reference.state_dict())

    inputs = torch.rand(3, 7, 8)
    with torch.no_grad():
        expected = reference(inputs)
        actual = mirror(inputs)
        correction = mirror.output_layer(mirror.gru(inputs)[0][:, -1, :]).squeeze(-1)

    torch.testing.assert_close(actual, expected)
    # Residual head: output = last scaled close (column 0) + correction.
    torch.testing.assert_close(actual, inputs[:, -1, 0] + correction)


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
