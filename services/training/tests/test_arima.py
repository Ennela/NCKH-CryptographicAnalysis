"""Alignment and benchmark-contract tests for the ARIMA rolling pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from services.training import train_arima
from services.training.models import arima_model
from services.training.models.arima_model import ARIMABaseline


class TrackingForecaster:
    """Predict from the latest observation while recording every history state."""

    def __init__(self, forecast_offset: float = 0.25) -> None:
        self.forecast_offset = forecast_offset
        self.history: list[float] = []
        self.forecast_histories: list[tuple[float, ...]] = []

    def fit(self, prices: Sequence[float] | np.ndarray) -> TrackingForecaster:
        self.history = [float(value) for value in prices]
        return self

    def forecast_one(self) -> float:
        self.forecast_histories.append(tuple(self.history))
        return self.history[-1] + self.forecast_offset

    def update(self, actual_close: float) -> None:
        self.history.append(float(actual_close))

    def snapshot(self) -> TrackingForecaster:
        snapshot = TrackingForecaster(self.forecast_offset)
        snapshot.history = list(self.history)
        snapshot.forecast_histories = list(self.forecast_histories)
        return snapshot


def _require(condition: bool, message: str) -> None:
    """Fail explicitly so critical checks remain active under python -O."""
    if not condition:
        pytest.fail(message)


def _small_locked_frame() -> pd.DataFrame:
    """Return splits with distinct levels so cross-split mistakes are visible."""
    timestamps = pd.date_range("2026-01-01", periods=14, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "ts": timestamps,
            "close": [
                10.0,
                11.0,
                12.0,
                13.0,
                14.0,
                50.0,
                51.0,
                52.0,
                53.0,
                100.0,
                101.0,
                102.0,
                103.0,
                104.0,
            ],
            "split": ["train"] * 5 + ["val"] * 4 + ["test"] * 5,
        }
    )
    frame["next_close"] = frame.groupby("split", sort=False)["close"].shift(-1)
    return frame


def _metadata() -> train_arima.DatasetMetadata:
    return train_arima.DatasetMetadata(
        dataset_version="group_dataset_v1",
        snapshot_name="ohlcv_full_current",
    )


def _run_tracking_evaluation() -> tuple[
    train_arima.PreparedRollingData,
    train_arima.RollingEvaluation,
    TrackingForecaster,
]:
    prepared = train_arima.prepare_rolling_data(_small_locked_frame())
    instances: list[TrackingForecaster] = []

    def factory() -> TrackingForecaster:
        model = TrackingForecaster()
        instances.append(model)
        return model

    evaluation = train_arima.run_rolling_evaluation(prepared, factory)
    evaluator = evaluation.evaluation_model
    _require(
        isinstance(evaluator, TrackingForecaster),
        "Rolling evaluation did not return the tracking evaluator",
    )
    return prepared, evaluation, evaluator


def test_rolling_forecast_aligns_each_horizon_one_target() -> None:
    prepared, evaluation, _ = _run_tracking_evaluation()
    test = evaluation.test

    assert len(test.predictions) == len(prepared.test_pairs) == 4
    assert test.pairs["current_close"].tolist() == [100.0, 101.0, 102.0, 103.0]
    assert test.pairs["actual_close"].tolist() == [101.0, 102.0, 103.0, 104.0]
    assert test.predictions.tolist() == [100.25, 101.25, 102.25, 103.25]
    assert (
        test.pairs["input_ts"].tolist()
        == _small_locked_frame()["ts"].iloc[9:13].tolist()
    )
    assert (
        test.pairs["target_ts"].tolist()
        == _small_locked_frame()["ts"].iloc[10:14].tolist()
    )


def test_validation_is_rolled_before_the_first_test_forecast() -> None:
    prepared, evaluation, model = _run_tracking_evaluation()

    assert len(evaluation.validation) == len(prepared.validation_pairs) == 3
    assert evaluation.validation.predictions.tolist() == [50.25, 51.25, 52.25]
    first_test_history = model.forecast_histories[len(evaluation.validation)]
    assert first_test_history[-2:] == (53.0, 100.0)
    assert evaluation.test.predictions[0] != prepared.train_end_close + 0.25


def test_each_forecast_history_ends_at_its_input_timestamp() -> None:
    _, evaluation, _ = _run_tracking_evaluation()

    for split_result in (evaluation.validation, evaluation.test):
        history_end = pd.to_datetime(split_result.history_end_ts, utc=True)
        input_ts = pd.to_datetime(split_result.pairs["input_ts"], utc=True)
        target_ts = pd.to_datetime(split_result.pairs["target_ts"], utc=True)
        assert history_end.tolist() == input_ts.tolist()
        assert (history_end <= input_ts).all()
        assert (input_ts < target_ts).all()


def test_pre_test_state_is_independent_from_post_test_evaluator() -> None:
    prepared, evaluation, evaluator = _run_tracking_evaluation()
    pre_test = evaluation.pre_test_model
    _require(
        isinstance(pre_test, TrackingForecaster),
        "Pre-test state has an unexpected model type",
    )
    _require(id(pre_test) != id(evaluator), "Pre-test and evaluator objects are shared")

    expected_pre_test_count = (
        len(prepared.train_close) + len(prepared.validation_pairs) + 1
    )
    expected_post_test_count = expected_pre_test_count + len(prepared.test_pairs) + 1
    _require(
        len(pre_test.history) == expected_pre_test_count,
        "Pre-test state changed while rolling through test targets",
    )
    _require(
        len(evaluator.history) == expected_post_test_count,
        "Evaluation state does not contain the complete post-test history",
    )
    _require(
        pre_test.history[-1] == 53.0,
        "Pre-test state does not end at the validation boundary",
    )
    _require(
        evaluator.history[-1] == 104.0,
        "Evaluation state does not end at the final test observation",
    )


def test_rolling_split_rejects_history_from_the_future() -> None:
    prepared = train_arima.prepare_rolling_data(_small_locked_frame())
    model = TrackingForecaster().fit(prepared.train_close)
    first_pair = prepared.validation_pairs.iloc[[0]].copy()
    future_history_ts = pd.Timestamp(first_pair["target_ts"].iloc[0])

    with pytest.raises(ValueError, match="history contains data after input_ts"):
        train_arima._roll_one_split(
            model,
            first_pair,
            future_history_ts,
            float(first_pair["actual_close"].iloc[0]),
            "validation",
        )


def test_prepare_rejects_off_by_one_target() -> None:
    frame = _small_locked_frame()
    first_test_index = frame.index[frame["split"].eq("test")][0]
    frame.loc[first_test_index, "next_close"] = 102.0

    with pytest.raises(ValueError, match="test next_close targets are off by one"):
        train_arima.prepare_rolling_data(frame)


def test_prepare_rejects_target_crossing_a_split_boundary() -> None:
    frame = _small_locked_frame()
    last_validation_index = frame.index[frame["split"].eq("val")][-1]
    frame.loc[last_validation_index, "next_close"] = 100.0

    with pytest.raises(ValueError, match="val target crosses"):
        train_arima.prepare_rolling_data(frame)


def test_prepare_rejects_non_chronological_split_order() -> None:
    frame = _small_locked_frame()
    frame.loc[4, "split"] = "val"
    frame.loc[5, "split"] = "train"

    with pytest.raises(ValueError, match="splits must be chronological"):
        train_arima.prepare_rolling_data(frame)


@pytest.mark.parametrize("prediction_count", [3, 5])
def test_prediction_count_must_match_manifest(
    prediction_count: int,
) -> None:
    prepared = train_arima.prepare_rolling_data(_small_locked_frame())
    manifest = train_arima.build_test_manifest(
        prepared.test_pairs,
        _metadata(),
        "ACB",
        "1d",
    )

    with pytest.raises(ValueError, match="prediction count must equal"):
        train_arima.build_prediction_frame(
            manifest,
            np.ones(prediction_count),
            "a" * 64,
            "run-id",
            42,
        )


def test_manifest_uses_exact_next_observation_timestamps() -> None:
    prepared = train_arima.prepare_rolling_data(_small_locked_frame())
    manifest = train_arima.build_test_manifest(
        prepared.test_pairs,
        _metadata(),
        "ACB",
        "1d",
    )

    assert manifest["input_ts"].tolist() == [
        "2026-01-10T00:00:00Z",
        "2026-01-11T00:00:00Z",
        "2026-01-12T00:00:00Z",
        "2026-01-13T00:00:00Z",
    ]
    assert manifest["target_ts"].tolist() == [
        "2026-01-11T00:00:00Z",
        "2026-01-12T00:00:00Z",
        "2026-01-13T00:00:00Z",
        "2026-01-14T00:00:00Z",
    ]


def test_metrics_export_rmse_not_mse_and_remain_finite() -> None:
    actual = np.array([12.0, 15.0])
    predicted = np.array([10.0, 19.0])
    current = np.array([11.0, 14.0])

    metrics = train_arima.evaluate_predictions(actual, predicted, current)
    expected_mse = 10.0
    assert "mse" not in metrics
    assert metrics["mae"] == pytest.approx(3.0)
    assert metrics["rmse"] == pytest.approx(np.sqrt(expected_mse))
    assert metrics["rmse"] != pytest.approx(expected_mse)
    assert metrics["rmse"] + train_arima.RMSE_TOLERANCE >= metrics["mae"]
    assert all(np.isfinite(value) for value in metrics.values())

    summary = train_arima.build_summary_frame(
        _metadata(),
        "ACB",
        "1d",
        "a" * 64,
        metrics,
        len(actual),
        "run-id",
        42,
    )
    assert tuple(summary.columns) == train_arima.SUMMARY_FIELDNAMES
    assert "mse" not in summary.columns
    assert summary.loc[0, "rmse"] == pytest.approx(np.sqrt(expected_mse))


def test_naive_metrics_use_current_close_from_the_same_manifest() -> None:
    prepared, evaluation, _ = _run_tracking_evaluation()
    manifest = train_arima.build_test_manifest(
        prepared.test_pairs,
        _metadata(),
        "ACB",
        "1d",
    )
    manifest_hash = train_arima.calculate_test_manifest_sha256(manifest)
    metrics = train_arima.evaluate_predictions(
        manifest["actual_close"],
        evaluation.test.predictions,
        manifest["current_close"],
    )
    expected_naive_errors = (
        manifest["actual_close"].to_numpy() - manifest["current_close"].to_numpy()
    )

    assert metrics["naive_mae"] == pytest.approx(np.mean(np.abs(expected_naive_errors)))
    assert metrics["naive_rmse"] == pytest.approx(
        np.sqrt(np.mean(np.square(expected_naive_errors)))
    )
    prediction_frame = train_arima.build_prediction_frame(
        manifest,
        evaluation.test.predictions,
        manifest_hash,
        "run-id",
        42,
    )
    pd.testing.assert_series_equal(
        prediction_frame["current_close"],
        manifest["current_close"],
        check_names=False,
    )
    assert prediction_frame["test_manifest_sha256"].eq(manifest_hash).all()


def test_prediction_and_summary_frames_use_exact_protocol_schemas() -> None:
    prepared, evaluation, _ = _run_tracking_evaluation()
    manifest = train_arima.build_test_manifest(
        prepared.test_pairs,
        _metadata(),
        "SYNTH",
        "1d",
    )
    manifest_hash = train_arima.calculate_test_manifest_sha256(manifest)
    metrics = train_arima.evaluate_predictions(
        manifest["actual_close"],
        evaluation.test.predictions,
        manifest["current_close"],
    )
    prediction_frame = train_arima.build_prediction_frame(
        manifest,
        evaluation.test.predictions,
        manifest_hash,
        "run-1",
        42,
    )
    summary_frame = train_arima.build_summary_frame(
        _metadata(),
        "SYNTH",
        "1d",
        manifest_hash,
        metrics,
        len(manifest),
        "run-1",
        42,
    )

    _require(
        tuple(prediction_frame.columns) == train_arima.PREDICTION_FIELDNAMES,
        "Prediction frame schema differs from the 14-column protocol",
    )
    _require(
        tuple(summary_frame.columns) == train_arima.SUMMARY_FIELDNAMES,
        "Summary frame schema differs from the 20-column protocol",
    )


def test_metrics_reject_non_finite_values_and_impossible_rmse() -> None:
    with pytest.raises(ValueError, match="contains NaN or Inf"):
        train_arima.evaluate_predictions([2.0], [np.inf], [1.0])

    valid = train_arima.evaluate_predictions(
        [2.0, 4.0],
        [2.5, 3.0],
        [1.0, 3.0],
    )
    invalid = {**valid, "mae": 2.0, "rmse": 1.0}
    with pytest.raises(ValueError, match="RMSE cannot be smaller than MAE"):
        train_arima.validate_metric_relationships(invalid)


def test_rolling_evaluation_rejects_non_finite_forecast() -> None:
    prepared = train_arima.prepare_rolling_data(_small_locked_frame())

    with pytest.raises(ValueError, match="forecast contains NaN or Inf"):
        train_arima.run_rolling_evaluation(
            prepared,
            lambda: TrackingForecaster(forecast_offset=np.inf),
        )


def test_protocol_csv_does_not_overwrite_an_existing_run(tmp_path: Path) -> None:
    metrics = train_arima.evaluate_predictions(
        [2.0, 4.0],
        [2.5, 3.0],
        [1.0, 3.0],
    )
    summary = train_arima.build_summary_frame(
        _metadata(), "ACB", "1d", "a" * 64, metrics, 2, "run-id", 42
    )
    path = tmp_path / "summary.csv"

    train_arima.write_protocol_csv(
        summary,
        path,
        train_arima.SUMMARY_FIELDNAMES,
    )
    with pytest.raises(FileExistsError):
        train_arima.write_protocol_csv(
            summary,
            path,
            train_arima.SUMMARY_FIELDNAMES,
        )


def test_cli_accepts_shared_seed_for_deterministic_arima() -> None:
    args = train_arima.parse_args(
        ["--ticker", "ACB", "--timeframe", "1d", "--seed", "42"]
    )
    assert args.seed == 42


def test_model_wrapper_forecasts_one_step_then_appends_actual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResult:
        def __init__(self, history: list[float]) -> None:
            self.history = history

        def forecast(self, steps: int) -> np.ndarray:
            assert steps == 1
            return np.array([self.history[-1] + 0.5])

        def append(self, values: list[float], refit: bool) -> FakeResult:
            assert refit is False
            return FakeResult([*self.history, *values])

    class FakeARIMA:
        def __init__(self, values: np.ndarray, **kwargs: Any) -> None:
            assert kwargs["order"] == (1, 1, 1)
            self.values = values.tolist()

        def fit(self) -> FakeResult:
            return FakeResult(self.values)

    monkeypatch.setattr(arima_model, "ARIMA", FakeARIMA)
    model = ARIMABaseline().fit([1.0, 2.0, 3.0, 4.0])

    assert model.forecast_one() == pytest.approx(4.5)
    model.update(5.0)
    assert model.forecast_one() == pytest.approx(5.5)


def test_statsmodels_snapshot_is_independent_reloadable_and_forecastable(
    tmp_path: Path,
) -> None:
    import mlflow.statsmodels

    model = ARIMABaseline().fit(np.linspace(10.0, 20.0, 24))
    pre_test_count = model.observation_count
    pre_test_last_value = model.last_observed_value
    evaluator = model.snapshot()

    _require(id(model) != id(evaluator), "Snapshot reused the ARIMA wrapper")
    _require(
        id(model.fitted_model) != id(evaluator.fitted_model),
        "Snapshot reused the fitted Statsmodels result",
    )
    evaluator.update(21.0)
    _require(
        model.observation_count == pre_test_count,
        "Updating the evaluator mutated the pre-test observation count",
    )
    _require(
        model.last_observed_value == pre_test_last_value,
        "Updating the evaluator mutated the pre-test final value",
    )
    _require(
        evaluator.observation_count == pre_test_count + 1,
        "Evaluator did not append exactly one observation",
    )

    artifact_path = tmp_path / "statsmodels_model"
    mlflow.statsmodels.save_model(model.fitted_model, artifact_path)
    restored = mlflow.statsmodels.load_model(artifact_path)
    restored_endog = np.asarray(restored.model.endog, dtype=np.float64).reshape(-1)
    restored_forecast = np.asarray(restored.forecast(steps=1), dtype=np.float64)
    _require(
        int(restored.nobs) == pre_test_count,
        "Reloaded artifact changed the pre-test observation count",
    )
    _require(
        float(restored_endog[-1]) == pre_test_last_value,
        "Reloaded artifact changed the pre-test final value",
    )
    _require(
        restored_forecast.shape == (1,) and np.isfinite(restored_forecast).all(),
        "Reloaded artifact cannot produce one finite forecast",
    )


def test_mlflow_contract_logs_pre_test_boundary_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mlflow
    import mlflow.statsmodels

    from services.training import mlflow_utils

    captured: dict[str, Any] = {}

    class RunContext:
        def __enter__(self) -> SimpleNamespace:
            return SimpleNamespace(info=SimpleNamespace(run_id="run-1"))

        def __exit__(self, *args: object) -> None:
            return None

    model = ARIMABaseline().fit(np.linspace(10.0, 20.0, 24))
    state_metadata = train_arima.build_model_state_metadata(
        model,
        pd.Timestamp("2026-01-24", tz="UTC"),
        20.0,
    )
    metrics = train_arima.evaluate_predictions(
        [20.0, 21.0],
        [19.5, 21.5],
        [19.0, 20.0],
    )

    monkeypatch.setattr(mlflow_utils, "init_mlflow", lambda: None)
    monkeypatch.setattr(
        mlflow, "set_experiment", lambda name: captured.setdefault("experiment", name)
    )
    monkeypatch.setattr(mlflow, "start_run", lambda **kwargs: RunContext())
    monkeypatch.setattr(
        mlflow, "log_params", lambda params: captured.setdefault("params", params)
    )
    monkeypatch.setattr(
        mlflow, "log_metrics", lambda values: captured.setdefault("metrics", values)
    )
    monkeypatch.setattr(
        mlflow,
        "log_dict",
        lambda payload, path: captured.update(metadata=payload, metadata_path=path),
    )
    monkeypatch.setattr(
        mlflow.statsmodels,
        "log_model",
        lambda fitted, **kwargs: captured.update(
            logged_model=fitted, model_options=kwargs
        ),
    )

    run_id = train_arima.log_training_run(
        _metadata(),
        "SYNTH",
        "1d",
        "a" * 64,
        42,
        metrics,
        model,
        state_metadata,
        7,
        8,
    )
    required_params = {
        "model": "arima",
        "state_role": "pre_test_deployable",
        "observation_count": 24,
        "history_end_ts": "2026-01-24T00:00:00Z",
        "history_end_value": 20.0,
        "order_p": 1,
        "order_d": 1,
        "order_q": 1,
        "horizon": 1,
        "contains_test_history": False,
    }
    _require(run_id == "run-1", "MLflow returned an unexpected run ID")
    for name, expected_value in required_params.items():
        _require(
            captured["params"].get(name) == expected_value,
            f"MLflow param {name} does not match the pre-test contract",
        )
        _require(
            captured["metadata"].get(name) == expected_value,
            f"Model metadata {name} does not match the pre-test contract",
        )
    _require(captured["metrics"] == metrics, "MLflow metrics changed")
    _require(
        captured["logged_model"] is model.fitted_model,
        "MLflow did not receive the immutable pre-test fitted result",
    )
    _require(
        captured["metadata_path"] == "metadata/pre_test_model.json",
        "Pre-test metadata was logged to an unexpected path",
    )
    _require(
        captured["model_options"]
        == {"artifact_path": "model", "registered_model_name": "SYNTH_1d_arima"},
        "Statsmodels registry options do not match the contract",
    )


def test_mlflow_rejects_metadata_that_does_not_match_the_model() -> None:
    model = ARIMABaseline().fit(np.linspace(10.0, 20.0, 24))
    invalid_metadata = train_arima.ModelStateMetadata(
        model="arima",
        state_role="pre_test_deployable",
        observation_count=23,
        history_end_ts="2026-01-24T00:00:00Z",
        history_end_value=20.0,
        order_p=1,
        order_d=1,
        order_q=1,
        horizon=1,
        contains_test_history=False,
    )

    with pytest.raises(ValueError, match="observation count does not match"):
        train_arima.validate_model_state_metadata(model, invalid_metadata)


def test_training_logs_pre_test_model_and_preserves_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(train_arima, "assert_locked_dataset", lambda: None)
    monkeypatch.setattr(train_arima, "load_full", lambda *_: _small_locked_frame())
    monkeypatch.setattr(train_arima, "load_dataset_metadata", _metadata)

    def fake_log_training_run(*args: Any) -> str:
        captured["logged_model"] = args[6]
        captured["state_metadata"] = args[7]
        return "run-consistency-1"

    def fake_write_and_log_outputs(*args: Any) -> None:
        captured["output_run_id"] = args[7]
        captured["output_predictions"] = np.asarray(args[5], dtype=np.float64)

    monkeypatch.setattr(train_arima, "log_training_run", fake_log_training_run)
    monkeypatch.setattr(
        train_arima,
        "_write_and_log_outputs",
        fake_write_and_log_outputs,
    )
    run_id = train_arima.run_training(
        train_arima.parse_args(
            ["--ticker", "SYNTH", "--timeframe", "1d", "--seed", "42"]
        )
    )

    logged_model = captured["logged_model"]
    state_metadata = captured["state_metadata"]
    _require(run_id == "run-consistency-1", "Training returned the wrong run ID")
    _require(
        isinstance(logged_model, ARIMABaseline),
        "Training did not log an ARIMA pre-test model",
    )
    _require(
        logged_model.observation_count == 9,
        "Training logged a model beyond the synthetic validation boundary",
    )
    _require(
        state_metadata.observation_count == 9,
        "Training metadata has the wrong synthetic pre-test count",
    )
    _require(
        state_metadata.history_end_ts == "2026-01-09T00:00:00Z",
        "Training metadata has the wrong synthetic validation boundary",
    )
    _require(
        state_metadata.history_end_value == 53.0,
        "Training metadata has the wrong synthetic validation value",
    )
    _require(
        captured["output_run_id"] == run_id,
        "CSV artifacts do not use the originating MLflow run ID",
    )
    _require(
        len(captured["output_predictions"]) == 4,
        "Training changed the synthetic test prediction count",
    )


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_model_wrapper_rejects_non_finite_history(bad_value: float) -> None:
    with pytest.raises(ValueError, match="finite values"):
        ARIMABaseline().fit([1.0, 2.0, 3.0, bad_value])
