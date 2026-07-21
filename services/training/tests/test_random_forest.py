"""Contract tests for the Random Forest benchmark pipeline."""

from __future__ import annotations

import csv
import inspect
import logging
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


def test_broadcasting_prone_shapes_are_rejected() -> None:
    y_true = np.array([100.0, 102.0, 101.0])
    y_pred = np.array([[100.5], [101.5], [101.2]])
    current_close = np.array([99.0, 101.0, 102.0])
    with pytest.raises(ValueError, match="one-dimensional"):
        train_random_forest.evaluate_metric_vectors(y_true, y_pred, current_close)


def test_mismatched_vector_lengths_are_rejected() -> None:
    with pytest.raises(AssertionError, match="shapes must match"):
        train_random_forest.evaluate_metric_vectors(
            np.array([100.0, 101.0]),
            np.array([100.5]),
            np.array([99.0, 100.0]),
        )


@pytest.mark.parametrize(
    ("argument", "bad_value"),
    [("y_true", np.nan), ("y_pred", np.inf), ("current_close", -np.inf)],
)
def test_nan_and_inf_are_rejected(argument: str, bad_value: float) -> None:
    values = {
        "y_true": np.array([100.0, 102.0]),
        "y_pred": np.array([100.5, 101.5]),
        "current_close": np.array([99.0, 101.0]),
    }
    values[argument][1] = bad_value
    with pytest.raises(AssertionError, match="finite"):
        train_random_forest.evaluate_metric_vectors(**values)


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
    assert tuple(output.columns) == train_random_forest.PREDICTION_FIELDNAMES
    assert len(output) == len(manifest)
    for column in ("input_ts", "target_ts", "current_close", "actual_close"):
        np.testing.assert_array_equal(output[column], manifest[column])
    np.testing.assert_array_equal(output["predicted_close"], predictions)


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
