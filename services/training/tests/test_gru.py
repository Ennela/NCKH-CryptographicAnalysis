"""Contract tests for the reproducible GRU benchmark pipeline."""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
import random
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import joblib
import numpy as np
import pandas as pd
import pytest
import torch

from services.training import train_gru
from services.training.models.gru_model import GRUForecaster


@pytest.fixture
def config() -> train_gru.GRUTrainingConfig:
    return replace(
        train_gru.GRUTrainingConfig(),
        sequence_length=8,
        moving_average_window=3,
        hidden_size=8,
        num_layers=1,
        dropout=0.0,
        max_epochs=3,
        batch_size=8,
        patience=2,
    )


@pytest.fixture
def full_frame() -> pd.DataFrame:
    row_count = 140
    row_number = np.arange(row_count, dtype=np.float64)
    close = 10.0 + row_number * 0.1 + np.sin(row_number / 5.0) * 0.2
    close[80:110] += 50.0
    close[110:] += 100.0
    split = np.where(
        row_number < 80,
        "train",
        np.where(row_number < 110, "val", "test"),
    )
    frame = pd.DataFrame(
        {
            "ts": pd.date_range("2025-01-01", periods=row_count, freq="D", tz="UTC"),
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000.0 + row_number,
            "split": split,
        }
    )
    frame["next_close"] = frame.groupby("split", sort=False)["close"].shift(-1)
    return frame


@pytest.fixture
def sequences(
    full_frame: pd.DataFrame,
    config: train_gru.GRUTrainingConfig,
) -> train_gru.PreparedSequences:
    return train_gru.build_sequence_dataset(full_frame, config)


@pytest.fixture
def metadata() -> train_gru.DatasetMetadata:
    return train_gru.DatasetMetadata("group_dataset_v1", "ohlcv_full_current")


def _small_model(config: train_gru.GRUTrainingConfig) -> GRUForecaster:
    return GRUForecaster(
        input_size=config.input_size,
        hidden_size=config.hidden_size,
        num_layers=config.num_layers,
        dropout=config.dropout,
    )


class LastFeatureModel(torch.nn.Module):
    """Return a row-specific marker for ordered batching tests."""

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return inputs[:, -1, 0]


def _valid_metrics() -> dict[str, float]:
    return {
        "mae": 1.0,
        "rmse": 1.2,
        "mape_pct": 2.0,
        "directional_accuracy": 0.6,
        "naive_mae": 1.5,
        "naive_rmse": 1.8,
        "naive_mape_pct": 3.0,
        "naive_directional_accuracy": 0.0,
        "improvement_vs_naive_rmse_pct": 33.333333333,
    }


def _read_logged_artifact(path: Path, loaded: dict[str, Any]) -> None:
    """Load a temporary artifact before its source directory is removed."""
    if path.name == "gru_state_dict.pt":
        loaded["state_dict"] = torch.load(path, map_location="cpu", weights_only=True)
    elif path.name == "feature_scaler.joblib":
        loaded["feature_scaler"] = joblib.load(path)
    elif path.name == "target_scaler.joblib":
        loaded["target_scaler"] = joblib.load(path)
    elif path.name == "reproducibility.json":
        loaded["metadata"] = json.loads(path.read_text(encoding="utf-8"))


def test_gru_forward_returns_one_value_per_sequence(
    config: train_gru.GRUTrainingConfig,
) -> None:
    model = _small_model(config)
    inputs = torch.zeros(4, config.sequence_length, config.input_size)
    predictions = model(inputs)
    assert predictions.shape == (4,)
    assert torch.isfinite(predictions).all()


def test_seed_reproduces_python_numpy_torch_and_model(
    config: train_gru.GRUTrainingConfig,
) -> None:
    train_gru.set_random_seed(42)
    first_values = (random.random(), np.random.random(), torch.rand(1))
    first_state = _small_model(config).state_dict()
    train_gru.set_random_seed(42)
    second_values = (random.random(), np.random.random(), torch.rand(1))
    second_state = _small_model(config).state_dict()
    assert first_values[0] == second_values[0]
    assert first_values[1] == second_values[1]
    torch.testing.assert_close(first_values[2], second_values[2])
    for name in first_state:
        torch.testing.assert_close(first_state[name], second_state[name])


def test_seed_is_called_before_model_and_dataloaders() -> None:
    source = inspect.getsource(train_gru.run_training)
    seed_position = source.index("set_random_seed")
    loader_position = source.index("create_data_loader")
    model_position = source.index("GRUForecaster")
    assert seed_position < loader_position
    assert seed_position < model_position


def test_short_cpu_training_is_reproducible(
    config: train_gru.GRUTrainingConfig,
    sequences: train_gru.PreparedSequences,
) -> None:
    short_config = replace(config, max_epochs=2, patience=2, batch_size=16)

    def train_once() -> tuple[
        train_gru.TrainingResult,
        dict[str, torch.Tensor],
        np.ndarray,
    ]:
        train_gru.set_random_seed(42)
        train_loader = train_gru.create_data_loader(sequences.train, 16, 42)
        validation_loader = train_gru.create_data_loader(sequences.val, 16, 42)
        model = _small_model(short_config)
        result = train_gru.train_with_early_stopping(
            model,
            train_loader,
            validation_loader,
            short_config,
            torch.device("cpu"),
        )
        state = {
            name: value.detach().clone() for name, value in model.state_dict().items()
        }
        predictions = train_gru.predict_scaled(
            model, sequences.test, 16, torch.device("cpu")
        )
        return result, state, predictions

    first_result, first_state, first_predictions = train_once()
    second_result, second_state, second_predictions = train_once()
    assert first_result == second_result
    for name in first_state:
        torch.testing.assert_close(
            first_state[name], second_state[name], rtol=0, atol=0
        )
    np.testing.assert_allclose(first_predictions, second_predictions, rtol=0, atol=0)


def test_scalers_fit_train_only(
    full_frame: pd.DataFrame,
    config: train_gru.GRUTrainingConfig,
    sequences: train_gru.PreparedSequences,
) -> None:
    featured = train_gru._build_continuous_features(full_frame, config)
    train_rows = featured["split"].eq("train")
    train_target_rows = train_rows & featured["next_close"].notna()
    train_features = featured.loc[train_rows, train_gru.FEATURE_LIST].to_numpy()
    train_targets = featured.loc[train_target_rows, "next_close"].to_numpy()
    np.testing.assert_allclose(
        sequences.feature_scaler.data_min_, train_features.min(0)
    )
    np.testing.assert_allclose(
        sequences.feature_scaler.data_max_, train_features.max(0)
    )
    assert sequences.target_scaler.data_min_[0] == pytest.approx(train_targets.min())
    assert sequences.target_scaler.data_max_[0] == pytest.approx(train_targets.max())
    assert sequences.target_scaler.data_max_[0] < full_frame["next_close"].max()


def test_sequence_has_no_lookahead(
    full_frame: pd.DataFrame,
    config: train_gru.GRUTrainingConfig,
) -> None:
    original = train_gru.build_sequence_dataset(full_frame, config)
    cutoff = original.test.input_ts[5]
    changed = full_frame.copy()
    changed.loc[changed["ts"].gt(cutoff), "close"] += 10_000.0
    changed["next_close"] = changed.groupby("split", sort=False)["close"].shift(-1)
    rebuilt = train_gru.build_sequence_dataset(changed, config)
    original_index = np.flatnonzero(original.test.input_ts == cutoff)[0]
    rebuilt_index = np.flatnonzero(rebuilt.test.input_ts == cutoff)[0]
    np.testing.assert_allclose(
        original.test.X[original_index],
        rebuilt.test.X[rebuilt_index],
        rtol=0.0,
        atol=0.0,
    )


def test_train_target_never_crosses_into_validation(
    full_frame: pd.DataFrame,
    sequences: train_gru.PreparedSequences,
) -> None:
    first_validation_ts = full_frame.loc[full_frame["split"].eq("val"), "ts"].min()
    assert max(sequences.train.target_ts) < first_validation_ts


def test_validation_target_never_crosses_into_test(
    full_frame: pd.DataFrame,
    sequences: train_gru.PreparedSequences,
) -> None:
    first_test_ts = full_frame.loc[full_frame["split"].eq("test"), "ts"].min()
    assert max(sequences.val.target_ts) < first_test_ts


def test_first_test_sequence_uses_prior_history_but_test_target(
    full_frame: pd.DataFrame,
    sequences: train_gru.PreparedSequences,
) -> None:
    first_test_ts = full_frame.loc[full_frame["split"].eq("test"), "ts"].min()
    test_times = set(full_frame.loc[full_frame["split"].eq("test"), "ts"])
    assert sequences.test.input_ts[0] == first_test_ts
    assert sequences.test.window_start_ts[0] < first_test_ts
    assert sequences.test.target_ts[0] in test_times
    assert sequences.test.target_ts[0] > sequences.test.input_ts[0]


def test_early_stopping_uses_validation_only(
    monkeypatch: pytest.MonkeyPatch,
    config: train_gru.GRUTrainingConfig,
    sequences: train_gru.PreparedSequences,
) -> None:
    train_gru.set_random_seed(42)
    train_loader = train_gru.create_data_loader(sequences.train, 16, 42)
    validation_loader = train_gru.create_data_loader(sequences.val, 16, 42)
    observed_loaders: list[Any] = []

    def fake_validation_loss(
        model: GRUForecaster,
        loader: Any,
        criterion: Any,
        device: torch.device,
    ) -> float:
        observed_loaders.append(loader)
        return 1.0

    monkeypatch.setattr(train_gru, "_mean_loader_loss", fake_validation_loss)
    short_config = replace(config, max_epochs=2, patience=1)
    model = _small_model(short_config)
    result = train_gru.train_with_early_stopping(
        model,
        train_loader,
        validation_loader,
        short_config,
        torch.device("cpu"),
    )
    assert result.epochs_ran == 2
    assert observed_loaders and set(map(id, observed_loaders)) == {
        id(validation_loader)
    }
    assert (
        "test" not in inspect.signature(train_gru.train_with_early_stopping).parameters
    )


def test_early_stopping_restores_best_validation_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    config: train_gru.GRUTrainingConfig,
    sequences: train_gru.PreparedSequences,
) -> None:
    epoch = 0
    validation_losses = iter([3.0, 1.0, 2.0])

    def fake_train_epoch(
        model: GRUForecaster,
        loader: Any,
        criterion: Any,
        optimizer: Any,
        device: torch.device,
    ) -> None:
        nonlocal epoch
        epoch += 1
        with torch.no_grad():
            for parameter in model.parameters():
                parameter.fill_(float(epoch))

    def fake_validation_loss(
        model: GRUForecaster,
        loader: Any,
        criterion: Any,
        device: torch.device,
    ) -> float:
        return next(validation_losses)

    monkeypatch.setattr(train_gru, "_train_one_epoch", fake_train_epoch)
    monkeypatch.setattr(train_gru, "_mean_loader_loss", fake_validation_loss)
    train_loader = train_gru.create_data_loader(sequences.train, 16, 42)
    validation_loader = train_gru.create_data_loader(sequences.val, 16, 42)
    model = _small_model(config)
    result = train_gru.train_with_early_stopping(
        model,
        train_loader,
        validation_loader,
        replace(config, max_epochs=3, patience=3),
        torch.device("cpu"),
    )
    assert result.best_epoch == 2
    for parameter in model.parameters():
        torch.testing.assert_close(parameter, torch.full_like(parameter, 2.0))


def test_scalers_are_not_refit_during_early_stopping() -> None:
    source = inspect.getsource(train_gru.train_with_early_stopping)
    assert "scaler" not in source.lower()
    assert ".fit(" not in source


def test_prediction_inverse_transform_occurs_once(
    monkeypatch: pytest.MonkeyPatch,
    sequences: train_gru.PreparedSequences,
) -> None:
    calls = 0
    original_inverse = sequences.target_scaler.inverse_transform

    def tracked_inverse(values: np.ndarray) -> np.ndarray:
        nonlocal calls
        calls += 1
        return original_inverse(values)

    monkeypatch.setattr(sequences.target_scaler, "inverse_transform", tracked_inverse)
    predictions = train_gru.inverse_predictions_once(
        sequences.target_scaler, sequences.test.y_scaled
    )
    assert calls == 1
    assert predictions.shape == (len(sequences.test),)
    source = inspect.getsource(train_gru)
    assert source.count(".inverse_transform(") == 1


def test_predictions_are_finite_and_shape_valid(
    config: train_gru.GRUTrainingConfig,
    sequences: train_gru.PreparedSequences,
) -> None:
    train_gru.set_random_seed(42)
    model = _small_model(config)
    predictions = train_gru.predict_scaled(
        model, sequences.test, config.batch_size, torch.device("cpu")
    )
    assert predictions.shape == (len(sequences.test),)
    assert np.isfinite(predictions).all()


def test_prediction_batches_preserve_row_identity(
    sequences: train_gru.PreparedSequences,
    metadata: train_gru.DatasetMetadata,
) -> None:
    batch_size = 3
    assert len(sequences.test) % batch_size != 0
    predictions = train_gru.predict_scaled(
        LastFeatureModel(), sequences.test, batch_size, torch.device("cpu")
    )
    expected_predictions = sequences.test.X[:, -1, 0].astype(np.float64)
    manifest = train_gru.build_test_manifest(sequences.test, metadata, "ACB", "1d")
    output = train_gru.build_prediction_frame(
        manifest, predictions, "a" * 64, "run-1", 42
    )
    np.testing.assert_array_equal(output.index, np.arange(len(sequences.test)))
    np.testing.assert_array_equal(output["predicted_close"], expected_predictions)
    np.testing.assert_array_equal(
        output["input_ts"],
        [train_gru._utc_timestamp(value) for value in sequences.test.input_ts],
    )
    np.testing.assert_array_equal(
        output["target_ts"],
        [train_gru._utc_timestamp(value) for value in sequences.test.target_ts],
    )
    np.testing.assert_array_equal(output["current_close"], sequences.test.current_close)
    np.testing.assert_array_equal(output["actual_close"], sequences.test.actual_close)
    assert output["target_ts"].is_unique


def test_metrics_are_finite_and_rmse_not_below_mae() -> None:
    actual = np.array([100.0, 102.0, 101.0])
    predicted = np.array([100.5, 101.5, 101.2])
    current = np.array([99.0, 101.0, 102.0])
    metrics = train_gru.evaluate_predictions(actual, predicted, current)
    assert all(np.isfinite(value) for value in metrics.values())
    assert metrics["rmse"] >= metrics["mae"]
    assert metrics["naive_rmse"] >= metrics["naive_mae"]


def test_invalid_rmse_mae_relationship_is_rejected() -> None:
    metrics = _valid_metrics()
    metrics["mae"] = 2.0
    metrics["rmse"] = 1.0
    with pytest.raises(ValueError, match="RMSE cannot be smaller"):
        train_gru.validate_metric_relationships(metrics)


def test_manifest_hash_matches_canonical_protocol() -> None:
    manifest = pd.DataFrame(
        [
            {
                "dataset_version": "group_dataset_v1",
                "snapshot_name": "ohlcv_full_current",
                "symbol": "ACB",
                "timeframe": "1d",
                "split": "test",
                "input_ts": "2026-01-01T00:00:00Z",
                "target_ts": "2026-01-02T00:00:00Z",
                "current_close": 10.0,
                "actual_close": 10.5,
            },
            {
                "dataset_version": "group_dataset_v1",
                "snapshot_name": "ohlcv_full_current",
                "symbol": "ACB",
                "timeframe": "1d",
                "split": "test",
                "input_ts": "2026-01-02T00:00:00Z",
                "target_ts": "2026-01-03T00:00:00Z",
                "current_close": 10.5,
                "actual_close": 11.0,
            },
        ],
        columns=train_gru.MANIFEST_FIELDNAMES,
    )
    canonical = (
        "dataset_version,snapshot_name,symbol,timeframe,input_ts,target_ts,"
        "current_close,actual_close\n"
        "group_dataset_v1,ohlcv_full_current,ACB,1d,2026-01-01T00:00:00Z,"
        "2026-01-02T00:00:00Z,10,10.5\n"
        "group_dataset_v1,ohlcv_full_current,ACB,1d,2026-01-02T00:00:00Z,"
        "2026-01-03T00:00:00Z,10.5,11\n"
    )
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert train_gru.calculate_test_manifest_sha256(manifest) == expected
    shuffled = manifest.iloc[::-1].reset_index(drop=True)
    assert train_gru.calculate_test_manifest_sha256(shuffled) == expected


def test_prediction_count_matches_manifest(
    sequences: train_gru.PreparedSequences,
    metadata: train_gru.DatasetMetadata,
) -> None:
    manifest = train_gru.build_test_manifest(sequences.test, metadata, "ACB", "1d")
    predictions = sequences.test.actual_close + 0.1
    output = train_gru.build_prediction_frame(
        manifest, predictions, "a" * 64, "run-1", 42
    )
    assert len(output) == len(manifest) == len(sequences.test)
    for column in ("input_ts", "target_ts", "current_close", "actual_close"):
        np.testing.assert_array_equal(output[column], manifest[column])
    assert output["model"].eq("gru").all()
    assert output["split"].eq("test").all()
    assert output["run_id"].eq("run-1").all()
    assert output["seed"].eq(42).all()
    with pytest.raises(ValueError, match="prediction count"):
        train_gru.build_prediction_frame(
            manifest, predictions[:-1], "a" * 64, "run-1", 42
        )


def test_non_finite_prediction_is_rejected(
    sequences: train_gru.PreparedSequences,
    metadata: train_gru.DatasetMetadata,
) -> None:
    manifest = train_gru.build_test_manifest(sequences.test, metadata, "ACB", "1d")
    predictions = sequences.test.actual_close.copy()
    predictions[0] = np.inf
    with pytest.raises(ValueError, match="NaN or Inf"):
        train_gru.build_prediction_frame(manifest, predictions, "a" * 64, "run-1", 42)


def test_exact_csv_schemas(
    tmp_path: Path,
    sequences: train_gru.PreparedSequences,
    metadata: train_gru.DatasetMetadata,
) -> None:
    manifest = train_gru.build_test_manifest(sequences.test, metadata, "ACB", "1d")
    manifest_hash = train_gru.calculate_test_manifest_sha256(manifest)
    prediction_frame = train_gru.build_prediction_frame(
        manifest, sequences.test.actual_close, manifest_hash, "run-1", 42
    )
    summary_frame = train_gru.build_summary_frame(
        metadata,
        "ACB",
        "1d",
        manifest_hash,
        _valid_metrics(),
        len(manifest),
        "run-1",
        42,
    )
    prediction_path = tmp_path / "prediction.csv"
    summary_path = tmp_path / "summary.csv"
    train_gru.write_protocol_csv(
        prediction_frame, prediction_path, train_gru.PREDICTION_FIELDNAMES
    )
    train_gru.write_protocol_csv(
        summary_frame, summary_path, train_gru.SUMMARY_FIELDNAMES
    )
    with prediction_path.open(newline="", encoding="utf-8") as csv_file:
        assert tuple(next(csv.reader(csv_file))) == train_gru.PREDICTION_FIELDNAMES
    with summary_path.open(newline="", encoding="utf-8") as csv_file:
        assert tuple(next(csv.reader(csv_file))) == train_gru.SUMMARY_FIELDNAMES


def test_model_state_scalers_and_outputs_share_mlflow_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config: train_gru.GRUTrainingConfig,
    sequences: train_gru.PreparedSequences,
) -> None:
    logged: list[tuple[str, str]] = []
    loaded: dict[str, Any] = {}

    @contextmanager
    def fake_start_run(run_id: str) -> Iterator[None]:
        assert run_id == "run-1"
        yield

    def fake_log_artifact(path: str, artifact_path: str) -> None:
        assert Path(path).is_file()
        logged.append((Path(path).name, artifact_path))
        _read_logged_artifact(Path(path), loaded)

    fake_mlflow = SimpleNamespace(
        start_run=fake_start_run,
        log_artifact=fake_log_artifact,
    )
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    prediction_path = tmp_path / "prediction.csv"
    summary_path = tmp_path / "summary.csv"
    prediction_path.write_text("prediction\n", encoding="utf-8")
    summary_path.write_text("summary\n", encoding="utf-8")
    model = _small_model(config)
    train_gru._log_run_artifacts(
        "run-1",
        model,
        sequences.feature_scaler,
        sequences.target_scaler,
        config,
        prediction_path,
        summary_path,
    )
    assert ("gru_state_dict.pt", "model_state") in logged
    assert ("feature_scaler.joblib", "preprocessing") in logged
    assert ("target_scaler.joblib", "preprocessing") in logged
    assert ("reproducibility.json", "metadata") in logged
    assert ("prediction.csv", "predictions") in logged
    assert ("summary.csv", "metrics") in logged
    restored_model = _small_model(config)
    restored_model.load_state_dict(loaded["state_dict"], strict=True)
    for name, value in model.state_dict().items():
        torch.testing.assert_close(value, restored_model.state_dict()[name])
    assert loaded["feature_scaler"].n_features_in_ == len(train_gru.FEATURE_LIST)
    assert loaded["target_scaler"].n_features_in_ == 1
    assert loaded["metadata"]["config"]["sequence_length"] == config.sequence_length


def test_mlflow_contract_logs_required_params_metrics_and_model(
    monkeypatch: pytest.MonkeyPatch,
    config: train_gru.GRUTrainingConfig,
    metadata: train_gru.DatasetMetadata,
) -> None:
    from services.training import mlflow_utils

    captured: dict[str, Any] = {}

    def fake_log_experiment_run(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "run-1"

    monkeypatch.setattr(mlflow_utils, "log_experiment_run", fake_log_experiment_run)
    model = _small_model(config)
    metrics = _valid_metrics()
    run_id = train_gru.log_training_run(
        metadata,
        "ACB",
        "1d",
        "a" * 64,
        42,
        metrics,
        model,
        config,
        train_gru.TrainingResult(2, 0.25, 3),
        torch.device("cpu"),
    )
    required_params = {
        "dataset_version",
        "snapshot_name",
        "test_manifest_sha256",
        "symbol",
        "timeframe",
        "model",
        "target",
        "horizon",
        "seed",
        "sequence_length",
        "batch_size",
        "learning_rate",
        "patience",
    }
    assert run_id == "run-1"
    assert required_params.issubset(captured["params"])
    assert captured["params"]["model"] == "gru"
    assert captured["params"]["target"] == "next_close"
    assert captured["params"]["horizon"] == 1
    assert captured["params"]["seed"] == 42
    assert captured["metrics"] == metrics
    assert captured["model"] is model
    assert captured["model_name_in_registry"] == "ACB_1d_gru"


def test_pipeline_contains_only_pytorch_gru() -> None:
    source = (
        inspect.getsource(train_gru)
        + inspect.getsource(
            __import__("services.training.models.gru_model", fromlist=["gru_model"])
        )
    ).lower()
    for forbidden in ("lstm", "tensorflow", "keras", "optuna"):
        assert forbidden not in source
    args = train_gru.parse_args(
        ["--ticker", "ACB", "--timeframe", "1d", "--seed", "42"]
    )
    assert vars(args) == {"ticker": "ACB", "timeframe": "1d", "seed": 42}
