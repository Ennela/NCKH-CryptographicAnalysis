"""Contract tests for the Random Forest benchmark pipeline."""

from __future__ import annotations

import csv
import inspect
import logging
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from services.training import train_random_forest
from services.training.models.random_forest_features import (
    FEATURE_LIST,
    build_random_forest_features,
)
from services.training.models.random_forest_model import RandomForestModelWrapper


def _model_params(seed: int = 7) -> dict[str, Any]:
    return {
        "n_estimators": 12,
        "max_depth": 4,
        "min_samples_split": 2,
        "min_samples_leaf": 1,
        "random_state": seed,
        "n_jobs": 1,
    }


@pytest.fixture
def ohlcv_frame() -> pd.DataFrame:
    row_count = 90
    row_number = np.arange(row_count, dtype=np.float64)
    close = 100.0 + 0.5 * row_number + np.sin(row_number / 4.0)
    split = np.where(
        row_number < 60,
        "train",
        np.where(row_number < 75, "val", "test"),
    )
    frame = pd.DataFrame(
        {
            "ts": pd.date_range("2025-01-01", periods=row_count, freq="D", tz="UTC"),
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000.0 + row_number * 10_000.0,
            "split": split,
        }
    )
    frame["next_close"] = frame.groupby("split", sort=False)["close"].shift(-1)
    return frame


@pytest.fixture
def feature_splits(ohlcv_frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return build_random_forest_features(ohlcv_frame)


@pytest.fixture
def metadata() -> train_random_forest.DatasetMetadata:
    return train_random_forest.DatasetMetadata(
        dataset_version="group_dataset_v1",
        snapshot_name="ohlcv_full_current",
    )


def _manifest(
    feature_splits: dict[str, pd.DataFrame],
    metadata: train_random_forest.DatasetMetadata,
) -> pd.DataFrame:
    return train_random_forest.build_test_manifest(
        feature_splits["test"], metadata, "ACB", "1d"
    )


def _valid_metrics() -> dict[str, float]:
    return {
        "mae": 1.0,
        "rmse": 1.2,
        "mape_pct": 0.8,
        "directional_accuracy": 0.6,
        "naive_mae": 1.5,
        "naive_rmse": 1.8,
        "naive_mape_pct": 1.1,
        "naive_directional_accuracy": 0.0,
        "improvement_vs_naive_rmse_pct": 33.3333333333,
    }


def test_feature_pipeline_is_owned_by_random_forest() -> None:
    feature_source = inspect.getsource(
        __import__(
            "services.training.models.random_forest_features",
            fromlist=["random_forest_features"],
        )
    )
    training_source = inspect.getsource(train_random_forest)
    assert "xgboost_features" not in feature_source
    assert "xgboost_features" not in training_source


def test_features_are_causal_on_continuous_series(ohlcv_frame: pd.DataFrame) -> None:
    cutoff = ohlcv_frame.loc[50, "ts"]
    original = build_random_forest_features(ohlcv_frame)
    changed = ohlcv_frame.copy()
    future_mask = changed["ts"].gt(cutoff)
    changed.loc[future_mask, ["open", "high", "low", "close"]] += 100_000.0
    changed.loc[future_mask, "volume"] *= 100.0
    changed.loc[changed["ts"].ge(cutoff), "next_close"] += 100_000.0
    rebuilt = build_random_forest_features(changed)

    original_row = original["train"].loc[original["train"]["input_ts"].eq(cutoff)]
    changed_row = rebuilt["train"].loc[rebuilt["train"]["input_ts"].eq(cutoff)]
    np.testing.assert_allclose(
        original_row.loc[:, FEATURE_LIST].to_numpy(),
        changed_row.loc[:, FEATURE_LIST].to_numpy(),
        rtol=0.0,
        atol=0.0,
    )


def test_target_is_float_one_dimensional(
    feature_splits: dict[str, pd.DataFrame],
) -> None:
    data = train_random_forest.prepare_dataset(feature_splits)
    for target in (data.y_train, data.y_val, data.y_test):
        values = target.to_numpy()
        assert values.dtype == np.float64
        assert values.ndim == 1
        assert target.name == "next_close"


def test_target_alignment_and_utc_manifest(
    feature_splits: dict[str, pd.DataFrame],
    metadata: train_random_forest.DatasetMetadata,
) -> None:
    manifest = _manifest(feature_splits, metadata)
    test_frame = feature_splits["test"]
    np.testing.assert_array_equal(
        manifest["actual_close"].to_numpy(),
        test_frame["next_close"].to_numpy(),
    )
    np.testing.assert_array_equal(
        manifest["current_close"].to_numpy(),
        test_frame["close"].to_numpy(),
    )
    assert (manifest["input_ts"] < manifest["target_ts"]).all()
    assert manifest["input_ts"].str.endswith("Z").all()
    assert manifest["target_ts"].str.endswith("Z").all()


def test_volume_or_timestamp_cannot_be_used_as_target(
    feature_splits: dict[str, pd.DataFrame],
) -> None:
    volume_target = feature_splits["test"].copy()
    volume_target["next_close"] = volume_target["volume"]
    with pytest.raises(ValueError, match="target source"):
        train_random_forest._validate_target_frame(volume_target, "test")

    timestamp_target = feature_splits["test"].copy()
    timestamp_target["next_close"] = timestamp_target["target_ts"]
    with pytest.raises(ValueError, match="target source|must be numeric"):
        train_random_forest._validate_target_frame(timestamp_target, "test")


def test_equal_shape_vectors_produce_metrics() -> None:
    y_true = np.array([100.0, 102.0, 101.0])
    y_pred = np.array([100.5, 101.5, 101.2])
    current_close = np.array([99.0, 101.0, 102.0])
    metrics = train_random_forest.evaluate_metric_vectors(y_true, y_pred, current_close)
    assert metrics["rmse"] >= metrics["mae"]
    assert metrics["naive_rmse"] >= metrics["naive_mae"]


def test_metric_recomputation_matches_expected_values() -> None:
    y_true = np.array([100.0, 102.0, 101.0], dtype=np.float64)
    y_pred = np.array([100.5, 101.5, 101.2], dtype=np.float64)
    current_close = np.array([99.0, 101.0, 102.0], dtype=np.float64)
    metrics = train_random_forest.evaluate_metric_vectors(
        y_true,
        y_pred,
        current_close,
    )

    errors = y_true - y_pred
    naive_errors = y_true - current_close
    expected = {
        "mae": np.mean(np.abs(errors)),
        "rmse": np.sqrt(np.mean(np.square(errors))),
        "mape_pct": np.mean(np.abs(errors / y_true)) * 100.0,
        "directional_accuracy": np.mean(
            np.sign(y_pred - current_close) == np.sign(y_true - current_close)
        ),
        "naive_mae": np.mean(np.abs(naive_errors)),
        "naive_rmse": np.sqrt(np.mean(np.square(naive_errors))),
        "naive_mape_pct": np.mean(np.abs(naive_errors / y_true)) * 100.0,
        "naive_directional_accuracy": np.mean(
            np.sign(current_close - current_close) == np.sign(y_true - current_close)
        ),
    }
    expected["improvement_vs_naive_rmse_pct"] = (
        (expected["naive_rmse"] - expected["rmse"]) / expected["naive_rmse"] * 100.0
    )
    np.testing.assert_allclose(
        [metrics[name] for name in expected],
        [expected[name] for name in expected],
        rtol=1e-12,
        atol=1e-12,
    )


@pytest.mark.parametrize("argument", ["y_true", "y_pred", "current_close"])
def test_multidimensional_metric_vectors_are_rejected(argument: str) -> None:
    values = {
        "y_true": np.array([100.0, 102.0, 101.0]),
        "y_pred": np.array([100.5, 101.5, 101.2]),
        "current_close": np.array([99.0, 101.0, 102.0]),
    }
    values[argument] = values[argument].reshape(-1, 1)
    with pytest.raises(ValueError, match=rf"{argument} must be one-dimensional"):
        train_random_forest.evaluate_metric_vectors(**values)


@pytest.mark.parametrize("argument", ["y_pred", "current_close"])
def test_mismatched_vector_lengths_are_rejected(argument: str) -> None:
    values = {
        "y_true": np.array([100.0, 101.0]),
        "y_pred": np.array([100.5, 101.5]),
        "current_close": np.array([99.0, 100.0]),
    }
    values[argument] = np.array([100.5])
    with pytest.raises(ValueError, match=rf"y_true and {argument}.*identical shapes"):
        train_random_forest.evaluate_metric_vectors(**values)


@pytest.mark.parametrize("argument", ["y_true", "y_pred", "current_close"])
def test_empty_metric_vectors_are_rejected(argument: str) -> None:
    values = {
        "y_true": np.array([100.0, 101.0]),
        "y_pred": np.array([100.5, 101.5]),
        "current_close": np.array([99.0, 100.0]),
    }
    values[argument] = np.array([])
    with pytest.raises(ValueError, match=rf"{argument} must not be empty"):
        train_random_forest.evaluate_metric_vectors(
            **values,
        )


@pytest.mark.parametrize(
    ("argument", "bad_value"),
    [
        (argument, bad_value)
        for argument in ("y_true", "y_pred", "current_close")
        for bad_value in (np.nan, np.inf, -np.inf)
    ],
)
def test_nan_and_inf_are_rejected(argument: str, bad_value: float) -> None:
    values = {
        "y_true": np.array([100.0, 102.0]),
        "y_pred": np.array([100.5, 101.5]),
        "current_close": np.array([99.0, 101.0]),
    }
    values[argument][1] = bad_value
    with pytest.raises(ValueError, match=rf"{argument} contains NaN or infinite"):
        train_random_forest.evaluate_metric_vectors(**values)


def test_integer_metric_vectors_are_converted_to_float64() -> None:
    vectors = train_random_forest.validate_metric_vectors(
        np.array([100, 102, 101], dtype=np.int64),
        np.array([101, 101, 102], dtype=np.int32),
        np.array([99, 101, 100], dtype=np.int16),
    )
    for vector in vectors:
        if vector.dtype != np.float64:
            pytest.fail(f"Expected float64 metric vector, got {vector.dtype}")


def test_metric_validation_survives_python_optimization_mode() -> None:
    validation_script = """
import numpy as np
from services.training.train_random_forest import evaluate_metric_vectors

valid = (
    np.array([100.0, 101.0]),
    np.array([100.5, 101.5]),
    np.array([99.0, 100.0]),
)
invalid_cases = {
    "multidimensional": (valid[0].reshape(-1, 1), valid[1], valid[2]),
    "mismatched": (valid[0], np.array([100.5]), valid[2]),
    "empty": (np.array([]), np.array([]), np.array([])),
    "nan": (np.array([100.0, np.nan]), valid[1], valid[2]),
    "positive_infinity": (valid[0], np.array([100.5, np.inf]), valid[2]),
    "negative_infinity": (valid[0], valid[1], np.array([99.0, -np.inf])),
}
for name, vectors in invalid_cases.items():
    try:
        evaluate_metric_vectors(*vectors)
    except ValueError:
        continue
    raise RuntimeError(f"optimization mode accepted invalid case: {name}")
"""
    completed = subprocess.run(
        [sys.executable, "-O", "-c", validation_script],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(
            "Optimized validation subprocess failed:\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


def test_prediction_order_of_magnitude_is_checked() -> None:
    with pytest.raises(ValueError, match="magnitude"):
        train_random_forest.evaluate_metric_vectors(
            np.array([100.0, 101.0]),
            np.array([100_000.0, 101_000.0]),
            np.array([99.0, 100.0]),
        )


def test_rmse_smaller_than_mae_is_rejected() -> None:
    metrics = _valid_metrics()
    metrics["mae"] = 2.0
    metrics["rmse"] = 1.0
    with pytest.raises(ValueError, match="RMSE cannot be smaller"):
        train_random_forest.validate_metric_relationships(metrics)


def test_unscaled_target_has_no_inverse_transform_path() -> None:
    source = inspect.getsource(train_random_forest)
    assert ".inverse_transform(" not in source
    assert "StandardScaler" not in source


def test_debug_logs_include_required_vector_statistics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=train_random_forest.__name__)
    train_random_forest.evaluate_metric_vectors(
        np.array([100.0, 102.0]),
        np.array([100.5, 101.5]),
        np.array([99.0, 101.0]),
    )
    for name in ("y_true", "y_pred", "current_close"):
        message = next(
            record.message for record in caplog.records if name in record.message
        )
        for field in (
            "shape=",
            "ndim=",
            "dtype=",
            "min=",
            "max=",
            "mean=",
            "finite_count=",
        ):
            assert field in message


def test_manifest_hash_is_stable(
    feature_splits: dict[str, pd.DataFrame],
    metadata: train_random_forest.DatasetMetadata,
) -> None:
    manifest = _manifest(feature_splits, metadata)
    first_hash = train_random_forest.calculate_test_manifest_sha256(manifest)
    shuffled = manifest.sample(frac=1.0, random_state=42).reset_index(drop=True)
    second_hash = train_random_forest.calculate_test_manifest_sha256(shuffled)
    assert first_hash == second_hash
    assert len(first_hash) == 64


def test_prediction_matches_test_manifest(
    feature_splits: dict[str, pd.DataFrame],
    metadata: train_random_forest.DatasetMetadata,
) -> None:
    manifest = _manifest(feature_splits, metadata)
    manifest_hash = train_random_forest.calculate_test_manifest_sha256(manifest)
    predictions = manifest["actual_close"].to_numpy() + 0.25
    output = train_random_forest.build_prediction_frame(
        manifest, predictions, manifest_hash, "run-123", 42
    )
    if tuple(output.columns) != train_random_forest.PREDICTION_FIELDNAMES:
        pytest.fail(f"Unexpected prediction schema: {tuple(output.columns)}")
    if len(output) != len(manifest):
        pytest.fail("Prediction row count does not match the canonical manifest")
    for column in ("input_ts", "target_ts", "current_close", "actual_close"):
        np.testing.assert_array_equal(output[column], manifest[column])
    np.testing.assert_array_equal(output["predicted_close"], predictions)
    expected_constants = {
        "dataset_version": metadata.dataset_version,
        "snapshot_name": metadata.snapshot_name,
        "test_manifest_sha256": manifest_hash,
        "symbol": "ACB",
        "timeframe": "1d",
        "model": "random_forest",
        "split": "test",
        "run_id": "run-123",
        "seed": 42,
    }
    for column, expected_value in expected_constants.items():
        if not output[column].eq(expected_value).all():
            pytest.fail(f"Prediction column {column} does not equal {expected_value!r}")
    if not output["target_ts"].is_monotonic_increasing:
        pytest.fail("Prediction target timestamps are not increasing")
    if output["target_ts"].duplicated().any():
        pytest.fail("Prediction output contains duplicate targets")
    if not output["input_ts"].lt(output["target_ts"]).all():
        pytest.fail("Prediction input timestamps must precede target timestamps")
    if not np.isfinite(
        output[["current_close", "actual_close", "predicted_close"]].to_numpy(
            dtype=np.float64
        )
    ).all():
        pytest.fail("Prediction output contains non-finite prices")


def test_prediction_count_must_equal_manifest(
    feature_splits: dict[str, pd.DataFrame],
    metadata: train_random_forest.DatasetMetadata,
) -> None:
    manifest = _manifest(feature_splits, metadata)
    with pytest.raises(ValueError, match="Prediction count"):
        train_random_forest.build_prediction_frame(
            manifest,
            np.ones(len(manifest) - 1),
            "a" * 64,
            "run-123",
            42,
        )


def test_naive_metrics_use_manifest_current_close(
    feature_splits: dict[str, pd.DataFrame],
    metadata: train_random_forest.DatasetMetadata,
) -> None:
    manifest = _manifest(feature_splits, metadata)
    actual = manifest["actual_close"].to_numpy(dtype=np.float64)
    current = manifest["current_close"].to_numpy(dtype=np.float64)
    metrics = train_random_forest.evaluate_metric_vectors(actual, actual, current)
    expected_rmse = float(np.sqrt(np.mean(np.square(actual - current))))
    expected_mae = float(np.mean(np.abs(actual - current)))
    assert metrics["naive_rmse"] == pytest.approx(expected_rmse)
    assert metrics["naive_mae"] == pytest.approx(expected_mae)
    assert metrics["naive_directional_accuracy"] == 0.0


def test_exact_prediction_and_summary_csv_schema(
    tmp_path: Path,
    feature_splits: dict[str, pd.DataFrame],
    metadata: train_random_forest.DatasetMetadata,
) -> None:
    manifest = _manifest(feature_splits, metadata)
    manifest_hash = train_random_forest.calculate_test_manifest_sha256(manifest)
    predictions = manifest["actual_close"].to_numpy(dtype=np.float64)
    prediction_frame = train_random_forest.build_prediction_frame(
        manifest, predictions, manifest_hash, "run-123", 42
    )
    summary_frame = train_random_forest.build_summary_frame(
        metadata,
        "ACB",
        "1d",
        manifest_hash,
        _valid_metrics(),
        len(manifest),
        "run-123",
        42,
    )
    prediction_path = tmp_path / "prediction.csv"
    summary_path = tmp_path / "summary.csv"
    train_random_forest.write_protocol_csv(
        prediction_frame,
        prediction_path,
        train_random_forest.PREDICTION_FIELDNAMES,
    )
    train_random_forest.write_protocol_csv(
        summary_frame,
        summary_path,
        train_random_forest.SUMMARY_FIELDNAMES,
    )
    with prediction_path.open(newline="", encoding="utf-8") as csv_file:
        prediction_header = tuple(next(csv.reader(csv_file)))
    with summary_path.open(newline="", encoding="utf-8") as csv_file:
        summary_header = tuple(next(csv.reader(csv_file)))
    assert prediction_header == train_random_forest.PREDICTION_FIELDNAMES
    assert summary_header == train_random_forest.SUMMARY_FIELDNAMES


def test_protocol_csv_does_not_overwrite_existing_run(tmp_path: Path) -> None:
    path = tmp_path / "existing.csv"
    frame = pd.DataFrame([{field: "value" for field in ("a", "b")}])
    train_random_forest.write_protocol_csv(frame, path, ("a", "b"))
    with pytest.raises(FileExistsError):
        train_random_forest.write_protocol_csv(frame, path, ("a", "b"))


def test_mlflow_params_metrics_and_model_contract(
    monkeypatch: pytest.MonkeyPatch,
    metadata: train_random_forest.DatasetMetadata,
) -> None:
    captured: dict[str, Any] = {}

    def fake_log_experiment_run(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "run-123"

    monkeypatch.setattr(
        "services.training.mlflow_utils.log_experiment_run",
        fake_log_experiment_run,
    )
    model = RandomForestModelWrapper(_model_params(seed=42))
    metrics = _valid_metrics()
    run_id = train_random_forest.log_training_run(
        metadata,
        "ACB",
        "1d",
        "a" * 64,
        42,
        metrics,
        model,
    )

    if run_id != "run-123":
        pytest.fail(f"Unexpected MLflow run ID: {run_id}")
    required_params = {
        "dataset_version": "group_dataset_v1",
        "snapshot_name": "ohlcv_full_current",
        "test_manifest_sha256": "a" * 64,
        "symbol": "ACB",
        "timeframe": "1d",
        "target": "next_close",
        "horizon": 1,
        "seed": 42,
        "model": "random_forest",
    }
    for name, expected_value in required_params.items():
        actual_value = captured["params"].get(name)
        if actual_value != expected_value:
            pytest.fail(
                f"MLflow param {name}={actual_value!r}, expected {expected_value!r}"
            )
    if captured["metrics"] != metrics:
        pytest.fail("MLflow metrics do not match the evaluated metric summary")
    if captured["model"] is not model.model:
        pytest.fail("MLflow did not receive the Random Forest estimator artifact")
    if captured["model_name_in_registry"] != "ACB_1d_random_forest":
        pytest.fail("Unexpected MLflow registered model name")


def test_mlflow_csv_artifacts_use_the_originating_run_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import mlflow

    started_run_ids: list[str] = []
    logged_artifacts: list[tuple[str, str]] = []

    @contextmanager
    def fake_start_run(*, run_id: str) -> Iterator[None]:
        started_run_ids.append(run_id)
        yield

    def fake_log_artifact(local_path: str, artifact_path: str) -> None:
        logged_artifacts.append((local_path, artifact_path))

    monkeypatch.setattr(mlflow, "start_run", fake_start_run)
    monkeypatch.setattr(mlflow, "log_artifact", fake_log_artifact)
    prediction_path = tmp_path / "prediction.csv"
    summary_path = tmp_path / "summary.csv"
    prediction_path.write_text("prediction", encoding="utf-8")
    summary_path.write_text("summary", encoding="utf-8")

    train_random_forest._log_csv_artifacts(
        "run-123",
        prediction_path,
        summary_path,
    )

    if started_run_ids != ["run-123"]:
        pytest.fail(f"Artifacts used unexpected run IDs: {started_run_ids}")
    expected_artifacts = [
        (str(prediction_path), "predictions"),
        (str(summary_path), "metrics"),
    ]
    if logged_artifacts != expected_artifacts:
        pytest.fail(f"Unexpected MLflow artifact calls: {logged_artifacts}")


def test_training_keeps_mlflow_csv_and_artifact_run_ids_consistent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ohlcv_frame: pd.DataFrame,
    feature_splits: dict[str, pd.DataFrame],
    metadata: train_random_forest.DatasetMetadata,
) -> None:
    expected_run_id = "run-consistency-123"
    expected_predictions = (
        feature_splits["test"]["actual_close"].to_numpy(dtype=np.float64) + 0.25
    )
    mlflow_call: dict[str, Any] = {}
    artifact_call: dict[str, Any] = {}

    class StubModel:
        def predict(self, features: pd.DataFrame) -> np.ndarray:
            if len(features) != len(expected_predictions):
                pytest.fail("Stub prediction count does not match test features")
            return expected_predictions.copy()

    def fake_assert_locked_dataset() -> None:
        return None

    def fake_load_dataset_metadata() -> train_random_forest.DatasetMetadata:
        return metadata

    def fake_load_full(ticker: str, timeframe: str) -> pd.DataFrame:
        if (ticker, timeframe) != ("ACB", "1d"):
            pytest.fail("Training did not request the expected locked series")
        return ohlcv_frame.copy()

    def fake_train_model(
        data: train_random_forest.PreparedDataset,
        seed: int,
    ) -> StubModel:
        if seed != 42 or len(data.X_test) != len(expected_predictions):
            pytest.fail("Training received an unexpected seed or test split")
        return StubModel()

    def fake_log_training_run(
        run_metadata: train_random_forest.DatasetMetadata,
        symbol: str,
        timeframe: str,
        manifest_hash: str,
        seed: int,
        metrics: train_random_forest.MetricValues,
        model: Any,
    ) -> str:
        mlflow_call.update(
            metadata=run_metadata,
            symbol=symbol,
            timeframe=timeframe,
            manifest_hash=manifest_hash,
            seed=seed,
            metrics=dict(metrics),
            model=model,
        )
        return expected_run_id

    def fake_log_csv_artifacts(
        run_id: str,
        prediction_path: Path,
        summary_path: Path,
    ) -> None:
        artifact_call.update(
            run_id=run_id,
            prediction_path=prediction_path,
            summary_path=summary_path,
        )

    monkeypatch.setattr(
        train_random_forest,
        "assert_locked_dataset",
        fake_assert_locked_dataset,
    )
    monkeypatch.setattr(
        train_random_forest,
        "load_dataset_metadata",
        fake_load_dataset_metadata,
    )
    monkeypatch.setattr(train_random_forest, "load_full", fake_load_full)
    monkeypatch.setattr(train_random_forest, "train_model", fake_train_model)
    monkeypatch.setattr(
        train_random_forest,
        "log_training_run",
        fake_log_training_run,
    )
    monkeypatch.setattr(
        train_random_forest,
        "_log_csv_artifacts",
        fake_log_csv_artifacts,
    )
    monkeypatch.setattr(
        train_random_forest,
        "PREDICTION_ROOT",
        tmp_path / "predictions",
    )
    monkeypatch.setattr(
        train_random_forest,
        "SUMMARY_ROOT",
        tmp_path / "metrics",
    )

    args = train_random_forest.parse_args(
        ["--ticker", "ACB", "--timeframe", "1d", "--seed", "42"]
    )
    returned_run_id = train_random_forest.run_training(args)
    if returned_run_id != expected_run_id:
        pytest.fail(f"Training returned unexpected run ID: {returned_run_id}")

    prediction_path = artifact_call["prediction_path"]
    summary_path = artifact_call["summary_path"]
    prediction_frame = pd.read_csv(prediction_path)
    summary_frame = pd.read_csv(summary_path)
    if artifact_call["run_id"] != expected_run_id:
        pytest.fail("MLflow CSV artifacts were attached to a different run")
    if not prediction_frame["run_id"].eq(expected_run_id).all():
        pytest.fail("Prediction CSV contains an inconsistent run ID")
    if not summary_frame["run_id"].eq(expected_run_id).all():
        pytest.fail("Summary CSV contains an inconsistent run ID")
    for metric_name, expected_value in mlflow_call["metrics"].items():
        np.testing.assert_allclose(
            summary_frame.loc[0, metric_name],
            expected_value,
            rtol=1e-12,
            atol=1e-12,
        )


def test_random_forest_model_save_load_roundtrip(tmp_path: Path) -> None:
    X_train = pd.DataFrame({"a": np.arange(20.0), "b": np.arange(20.0) ** 2})
    y_train = pd.Series(100.0 + np.arange(20.0), name="next_close")
    X_test = X_train.iloc[-5:].copy()
    model = RandomForestModelWrapper(_model_params())
    model.fit(X_train, y_train)
    expected = model.predict(X_test)
    model_path = tmp_path / "random_forest.joblib"
    model.save(model_path)
    restored = RandomForestModelWrapper(_model_params())
    restored.load(model_path)
    np.testing.assert_allclose(restored.predict(X_test), expected)


def test_issue_does_not_add_optuna_tuning() -> None:
    source = inspect.getsource(train_random_forest)
    assert "optuna" not in source.lower()
    args = train_random_forest.parse_args(
        ["--ticker", "ACB", "--timeframe", "1d", "--seed", "42"]
    )
    assert vars(args) == {"ticker": "ACB", "timeframe": "1d", "seed": 42}
