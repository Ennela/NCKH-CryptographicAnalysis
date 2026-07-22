"""Train and evaluate the fixed Random Forest next-close benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.training.models.random_forest_features import (
    FEATURE_LIST,
    build_random_forest_features,
)
from services.training.models.random_forest_model import (
    DEFAULT_RANDOM_FOREST_PARAMS,
    RandomForestModelWrapper,
)
from shared.dataset.loader import (
    DEFAULT_CONTRACT_PATH,
    assert_locked_dataset,
    load_full,
)
from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)

MODEL_NAME = "random_forest"
TARGET_COLUMN = "next_close"
HORIZON = 1
DEFAULT_SEED = 42
STATUS = "preliminary"
RMSE_TOLERANCE = 1e-12
ORDER_OF_MAGNITUDE_LIMIT = 100.0
REPO_ROOT = Path(__file__).resolve().parents[2]
PREDICTION_ROOT = REPO_ROOT / "artifacts" / "predictions" / MODEL_NAME
SUMMARY_ROOT = REPO_ROOT / "artifacts" / "metrics" / MODEL_NAME

MANIFEST_FIELDNAMES: tuple[str, ...] = (
    "dataset_version",
    "snapshot_name",
    "symbol",
    "timeframe",
    "split",
    "input_ts",
    "target_ts",
    "current_close",
    "actual_close",
)
MANIFEST_HASH_FIELDNAMES: tuple[str, ...] = (
    "dataset_version",
    "snapshot_name",
    "symbol",
    "timeframe",
    "input_ts",
    "target_ts",
    "current_close",
    "actual_close",
)
PREDICTION_FIELDNAMES: tuple[str, ...] = (
    "dataset_version",
    "snapshot_name",
    "test_manifest_sha256",
    "symbol",
    "timeframe",
    "model",
    "split",
    "input_ts",
    "target_ts",
    "current_close",
    "actual_close",
    "predicted_close",
    "run_id",
    "seed",
)
SUMMARY_FIELDNAMES: tuple[str, ...] = (
    "dataset_version",
    "snapshot_name",
    "test_manifest_sha256",
    "symbol",
    "timeframe",
    "model",
    "split",
    "n_samples",
    "mae",
    "rmse",
    "mape_pct",
    "directional_accuracy",
    "naive_mae",
    "naive_rmse",
    "naive_mape_pct",
    "naive_directional_accuracy",
    "improvement_vs_naive_rmse_pct",
    "run_id",
    "seed",
    "status",
)

MetricValues = dict[str, float]


@dataclass(frozen=True)
class DatasetMetadata:
    """Locked dataset identity written to every benchmark artifact."""

    dataset_version: str
    snapshot_name: str


@dataclass(frozen=True)
class PreparedDataset:
    """Unscaled Random Forest feature matrices and next-close targets."""

    X_train: pd.DataFrame
    y_train: pd.Series
    X_val: pd.DataFrame
    y_val: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the fixed-configuration Random Forest CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Ticker in locked dataset")
    parser.add_argument("--timeframe", required=True, help="Timeframe such as 1d")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


def set_random_seed(seed: int) -> None:
    """Seed Python and NumPy for reproducible training."""
    random.seed(seed)
    np.random.seed(seed)


def load_dataset_metadata(
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> DatasetMetadata:
    """Read the locked dataset identity and target contract."""
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    if payload.get("target") != {"mode": TARGET_COLUMN, "horizon": HORIZON}:
        raise ValueError("Random Forest requires target next_close with horizon 1.")
    dataset_version = str(payload.get("dataset_version", ""))
    snapshot_name = str(payload.get("source_snapshot_name", ""))
    if not dataset_version or not snapshot_name:
        raise ValueError("Dataset contract is missing version or snapshot metadata.")
    return DatasetMetadata(dataset_version, snapshot_name)


def _validate_target_frame(frame: pd.DataFrame, split_name: str) -> None:
    """Verify that one feature split retains the locked next-close target."""
    required = {
        TARGET_COLUMN,
        "volume",
        "close",
        "split",
        "input_ts",
        "target_ts",
        "current_close",
        "actual_close",
    }
    if frame.empty or required.difference(frame.columns):
        raise ValueError(f"Random Forest {split_name} split is empty or incomplete.")
    if set(frame["split"].astype(str)) != {split_name}:
        raise ValueError(f"Random Forest {split_name} split label is invalid.")

    try:
        target = np.asarray(frame[TARGET_COLUMN], dtype=np.float64)
        actual = np.asarray(frame["actual_close"], dtype=np.float64)
        current = np.asarray(frame["current_close"], dtype=np.float64)
        close = np.asarray(frame["close"], dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("Random Forest price targets must be numeric.") from exc
    price_vectors = {
        TARGET_COLUMN: target,
        "actual_close": actual,
        "current_close": current,
        "close": close,
    }
    if any(array.ndim != 1 for array in price_vectors.values()):
        raise ValueError("Random Forest price columns must be one-dimensional.")
    if any(array.shape != target.shape for array in price_vectors.values()):
        raise ValueError("Random Forest price columns must have identical shapes.")
    if not np.array_equal(target, actual):
        raise ValueError("Random Forest target source must be next_close.")
    if not np.array_equal(current, close):
        raise ValueError("current_close must come from close at input_ts.")
    if not frame["input_ts"].lt(frame["target_ts"]).all():
        raise ValueError("input_ts must be earlier than target_ts.")


def _prepare_feature_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Select the Random Forest feature contract and require finite values."""
    features = frame.loc[:, FEATURE_LIST].astype(np.float64)
    if not np.isfinite(features.to_numpy()).all():
        raise ValueError("Random Forest feature matrix contains NaN or Inf.")
    return features


def _prepare_target(frame: pd.DataFrame) -> pd.Series:
    """Return an unscaled one-dimensional float next-close target."""
    target = np.asarray(frame[TARGET_COLUMN], dtype=np.float64)
    if target.ndim != 1:
        raise ValueError("Random Forest target must be one-dimensional.")
    if not np.isfinite(target).all():
        raise ValueError("Random Forest target contains NaN or Inf.")
    return pd.Series(target, name=TARGET_COLUMN)


def prepare_dataset(splits: dict[str, pd.DataFrame]) -> PreparedDataset:
    """Prepare unscaled features and targets without fitting a target scaler."""
    for split_name in ("train", "val", "test"):
        _validate_target_frame(splits[split_name], split_name)
    return PreparedDataset(
        X_train=_prepare_feature_matrix(splits["train"]),
        y_train=_prepare_target(splits["train"]),
        X_val=_prepare_feature_matrix(splits["val"]),
        y_val=_prepare_target(splits["val"]),
        X_test=_prepare_feature_matrix(splits["test"]),
        y_test=_prepare_target(splits["test"]),
    )


def build_model_params(seed: int) -> dict[str, Any]:
    """Return the existing fixed hyperparameters with the requested seed."""
    params = dict(DEFAULT_RANDOM_FOREST_PARAMS)
    params["random_state"] = seed
    return params


def train_model(data: PreparedDataset, seed: int) -> RandomForestModelWrapper:
    """Fit one fixed Random Forest on the training split only."""
    model = RandomForestModelWrapper(build_model_params(seed))
    model.fit(data.X_train, data.y_train)
    return model


def _log_metric_vector(name: str, values: np.ndarray) -> None:
    """Log audit statistics for one metric input before calculation."""
    finite_mask = np.isfinite(values)
    finite_values = values[finite_mask]
    minimum = float(finite_values.min()) if finite_values.size else None
    maximum = float(finite_values.max()) if finite_values.size else None
    mean = float(finite_values.mean()) if finite_values.size else None
    logger.debug(
        "%s shape=%s ndim=%d dtype=%s min=%s max=%s mean=%s finite_count=%d",
        name,
        values.shape,
        values.ndim,
        values.dtype,
        minimum,
        maximum,
        mean,
        int(finite_mask.sum()),
    )


def _metric_vector(name: str, values: Any) -> np.ndarray:
    """Convert a metric input to float64 and reject broadcasting-prone shapes."""
    raw_array = np.asarray(values)
    if raw_array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional, got shape={raw_array.shape}")
    if raw_array.size == 0:
        raise ValueError(f"{name} must not be empty")
    try:
        array = np.asarray(raw_array, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric values") from exc
    _log_metric_vector(name, array)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains NaN or infinite values")
    return array


def validate_metric_vectors(
    y_true: Any,
    y_pred: Any,
    current_close: Any,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Validate metric vector structure, then return finite float64 arrays."""
    raw_vectors = {
        "y_true": np.asarray(y_true),
        "y_pred": np.asarray(y_pred),
        "current_close": np.asarray(current_close),
    }
    for name, array in raw_vectors.items():
        if array.ndim != 1:
            raise ValueError(f"{name} must be one-dimensional, got shape={array.shape}")
        if array.size == 0:
            raise ValueError(f"{name} must not be empty")

    expected_shape = raw_vectors["y_true"].shape
    for name in ("y_pred", "current_close"):
        actual_shape = raw_vectors[name].shape
        if actual_shape != expected_shape:
            raise ValueError(
                f"y_true and {name} must have identical shapes: "
                f"{expected_shape} != {actual_shape}"
            )

    validated_vectors: dict[str, np.ndarray] = {}
    for name, raw_array in raw_vectors.items():
        try:
            array = np.asarray(raw_array, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must contain numeric values") from exc
        _log_metric_vector(name, array)
        if not np.isfinite(array).all():
            raise ValueError(f"{name} contains NaN or infinite values")
        validated_vectors[name] = array

    return (
        validated_vectors["y_true"],
        validated_vectors["y_pred"],
        validated_vectors["current_close"],
    )


def _validate_prediction_scale(y_true: np.ndarray, y_pred: np.ndarray) -> None:
    """Reject predictions that differ from actual prices by over two magnitudes."""
    actual_scale = float(np.median(np.abs(y_true)))
    predicted_scale = float(np.median(np.abs(y_pred)))
    if actual_scale <= 0.0 or predicted_scale <= 0.0:
        raise ValueError("Actual and predicted price scales must be positive.")
    scale_ratio = predicted_scale / actual_scale
    lower_limit = 1.0 / ORDER_OF_MAGNITUDE_LIMIT
    if not lower_limit <= scale_ratio <= ORDER_OF_MAGNITUDE_LIMIT:
        raise ValueError(
            "predicted_close is not comparable in magnitude to actual_close."
        )


def _error_metrics(
    y_true: np.ndarray, y_pred: np.ndarray
) -> tuple[float, float, float]:
    """Calculate MAE, RMSE, and percentage MAPE on identical vectors."""
    if np.any(y_true == 0.0):
        raise ValueError("MAPE is undefined when actual_close contains zero.")
    errors = y_true - y_pred
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    mape_pct = float(np.mean(np.abs(errors / y_true)) * 100.0)
    return mae, rmse, mape_pct


def _directional_accuracy(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    current_close: np.ndarray,
) -> float:
    """Return the fraction of predicted directions matching actual directions."""
    actual_direction = np.sign(y_true - current_close)
    predicted_direction = np.sign(y_pred - current_close)
    return float(np.mean(actual_direction == predicted_direction))


def validate_metric_relationships(metrics: dict[str, float]) -> None:
    """Enforce protocol inequalities and finite metric values."""
    if not all(np.isfinite(value) for value in metrics.values()):
        raise ValueError("Metric summary contains NaN or Inf.")
    if metrics["rmse"] + RMSE_TOLERANCE < metrics["mae"]:
        raise ValueError("RMSE cannot be smaller than MAE.")
    if metrics["naive_rmse"] + RMSE_TOLERANCE < metrics["naive_mae"]:
        raise ValueError("Naive RMSE cannot be smaller than Naive MAE.")


def _calculate_metric_summary(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    current_close: np.ndarray,
) -> MetricValues:
    """Calculate model and manifest-locked Naive metrics."""
    mae, rmse, mape_pct = _error_metrics(y_true, y_pred)
    naive_mae, naive_rmse, naive_mape_pct = _error_metrics(y_true, current_close)
    if naive_rmse == 0.0:
        raise ValueError("Improvement is undefined when naive RMSE is zero.")
    metrics = {
        "mae": mae,
        "rmse": rmse,
        "mape_pct": mape_pct,
        "directional_accuracy": _directional_accuracy(y_true, y_pred, current_close),
        "naive_mae": naive_mae,
        "naive_rmse": naive_rmse,
        "naive_mape_pct": naive_mape_pct,
        "naive_directional_accuracy": _directional_accuracy(
            y_true, current_close, current_close
        ),
        "improvement_vs_naive_rmse_pct": ((naive_rmse - rmse) / naive_rmse * 100.0),
    }
    validate_metric_relationships(metrics)
    return metrics


def evaluate_metric_vectors(
    y_true: Any,
    y_pred: Any,
    current_close: Any,
) -> MetricValues:
    """Validate and evaluate raw next-close predictions against the manifest."""
    y_true_array, y_pred_array, current_array = validate_metric_vectors(
        y_true,
        y_pred,
        current_close,
    )
    _validate_prediction_scale(y_true_array, y_pred_array)
    return _calculate_metric_summary(y_true_array, y_pred_array, current_array)


def _utc_timestamp(value: Any) -> str:
    """Serialize one timestamp as canonical UTC ISO-8601 seconds."""
    timestamp = pd.to_datetime(value, utc=True, errors="raise")
    if pd.isna(timestamp):
        raise ValueError("Timestamp must not be missing.")
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_float(value: Any) -> str:
    """Serialize one finite float using the protocol round-trip format."""
    number = float(value)
    if not np.isfinite(number):
        raise ValueError("Manifest numeric values must be finite.")
    formatted = format(number, ".17g")
    return "0" if formatted == "-0" else formatted


def build_test_manifest(
    test_frame: pd.DataFrame,
    metadata: DatasetMetadata,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    """Build the ordered test manifest from preserved feature metadata."""
    _validate_target_frame(test_frame, "test")
    manifest = pd.DataFrame(
        {
            "dataset_version": metadata.dataset_version,
            "snapshot_name": metadata.snapshot_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "split": "test",
            "input_ts": test_frame["input_ts"].map(_utc_timestamp),
            "target_ts": test_frame["target_ts"].map(_utc_timestamp),
            "current_close": test_frame["current_close"].astype(np.float64),
            "actual_close": test_frame["actual_close"].astype(np.float64),
        }
    ).sort_values("target_ts", kind="mergesort", ignore_index=True)
    if (
        manifest["input_ts"].duplicated().any()
        or manifest["target_ts"].duplicated().any()
    ):
        raise ValueError("Test manifest timestamps must be unique.")
    if not (manifest["input_ts"] < manifest["target_ts"]).all():
        raise ValueError("Test manifest input_ts must precede target_ts.")
    return manifest.loc[:, MANIFEST_FIELDNAMES]


def calculate_test_manifest_sha256(manifest: pd.DataFrame) -> str:
    """Hash the canonical eight-column manifest representation."""
    if tuple(manifest.columns) != MANIFEST_FIELDNAMES:
        raise ValueError("Test manifest schema or column order is invalid.")
    canonical = manifest.sort_values("target_ts", kind="mergesort", ignore_index=True)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(MANIFEST_HASH_FIELDNAMES)
    for row in canonical.loc[:, MANIFEST_HASH_FIELDNAMES].itertuples(index=False):
        values = list(row)
        values[4] = _utc_timestamp(values[4])
        values[5] = _utc_timestamp(values[5])
        values[6] = _canonical_float(values[6])
        values[7] = _canonical_float(values[7])
        writer.writerow(values)
    return hashlib.sha256(stream.getvalue().encode("utf-8")).hexdigest()


def build_prediction_frame(
    manifest: pd.DataFrame,
    predictions: Any,
    manifest_hash: str,
    run_id: str,
    seed: int,
) -> pd.DataFrame:
    """Join predictions to the manifest without changing target order."""
    predicted_close = _metric_vector("y_pred", predictions)
    if len(predicted_close) != len(manifest):
        raise ValueError("Prediction count must equal the test manifest count.")
    if not np.isfinite(predicted_close).all():
        raise ValueError("Prediction output contains NaN or Inf.")
    frame = manifest.copy()
    frame.insert(2, "test_manifest_sha256", manifest_hash)
    frame.insert(5, "model", MODEL_NAME)
    frame["predicted_close"] = predicted_close
    frame["run_id"] = run_id
    frame["seed"] = seed
    return frame.loc[:, PREDICTION_FIELDNAMES]


def build_summary_frame(
    metadata: DatasetMetadata,
    symbol: str,
    timeframe: str,
    manifest_hash: str,
    metrics: MetricValues,
    n_samples: int,
    run_id: str,
    seed: int,
) -> pd.DataFrame:
    """Build the one-row protocol metrics summary."""
    validate_metric_relationships(metrics)
    if n_samples <= 0:
        raise ValueError("Metrics summary requires at least one sample.")
    row: dict[str, Any] = {
        "dataset_version": metadata.dataset_version,
        "snapshot_name": metadata.snapshot_name,
        "test_manifest_sha256": manifest_hash,
        "symbol": symbol,
        "timeframe": timeframe,
        "model": MODEL_NAME,
        "split": "test",
        "n_samples": n_samples,
        **metrics,
        "run_id": run_id,
        "seed": seed,
        "status": STATUS,
    }
    return pd.DataFrame([row], columns=SUMMARY_FIELDNAMES)


def write_protocol_csv(
    frame: pd.DataFrame,
    path: Path,
    fieldnames: tuple[str, ...],
) -> None:
    """Write one exact-schema UTF-8 CSV without overwriting prior runs."""
    if tuple(frame.columns) != fieldnames:
        raise ValueError("CSV schema or column order does not match the protocol.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(frame.to_dict(orient="records"))


def log_training_run(
    metadata: DatasetMetadata,
    symbol: str,
    timeframe: str,
    manifest_hash: str,
    seed: int,
    metrics: MetricValues,
    model: RandomForestModelWrapper,
) -> str:
    """Log fixed hyperparameters, protocol metadata, metrics, and model."""
    from services.training.mlflow_utils import log_experiment_run

    params = {
        **{
            key: value for key, value in model.get_params().items() if value is not None
        },
        "dataset_version": metadata.dataset_version,
        "snapshot_name": metadata.snapshot_name,
        "test_manifest_sha256": manifest_hash,
        "symbol": symbol,
        "timeframe": timeframe,
        "model": MODEL_NAME,
        "horizon": HORIZON,
        "seed": seed,
        "feature_list": ",".join(FEATURE_LIST),
        "target": TARGET_COLUMN,
    }
    return log_experiment_run(
        experiment_name=f"{symbol}_{timeframe}_{MODEL_NAME}",
        run_name=f"{MODEL_NAME}_{symbol}_{timeframe}",
        params=params,
        metrics=metrics,
        model=model.model,
        model_name_in_registry=f"{symbol}_{timeframe}_{MODEL_NAME}",
    )


def _artifact_paths(symbol: str, timeframe: str, run_id: str) -> tuple[Path, Path]:
    """Return unique prediction and summary paths for one MLflow run."""
    filename = f"{symbol}_{timeframe}_{run_id}.csv"
    return PREDICTION_ROOT / filename, SUMMARY_ROOT / filename


def _log_csv_artifacts(run_id: str, prediction_path: Path, summary_path: Path) -> None:
    """Attach both protocol CSV files to their originating MLflow run."""
    import mlflow

    with mlflow.start_run(run_id=run_id):
        mlflow.log_artifact(str(prediction_path), artifact_path="predictions")
        mlflow.log_artifact(str(summary_path), artifact_path="metrics")


def run_training(args: argparse.Namespace) -> str:
    """Execute locked-data training, strict evaluation, and protocol export."""
    set_random_seed(args.seed)
    assert_locked_dataset()
    metadata = load_dataset_metadata()
    symbol = args.ticker.strip().replace("/", "").upper()
    timeframe = args.timeframe.strip().lower()
    full_frame = load_full(symbol, timeframe)
    splits = build_random_forest_features(full_frame)
    data = prepare_dataset(splits)
    model = train_model(data, args.seed)

    manifest = build_test_manifest(splits["test"], metadata, symbol, timeframe)
    manifest_hash = calculate_test_manifest_sha256(manifest)
    predictions = model.predict(data.X_test)
    metrics = evaluate_metric_vectors(
        data.y_test,
        predictions,
        splits["test"]["current_close"],
    )
    run_id = log_training_run(
        metadata, symbol, timeframe, manifest_hash, args.seed, metrics, model
    )
    prediction_frame = build_prediction_frame(
        manifest, predictions, manifest_hash, run_id, args.seed
    )
    summary_frame = build_summary_frame(
        metadata,
        symbol,
        timeframe,
        manifest_hash,
        metrics,
        len(manifest),
        run_id,
        args.seed,
    )
    prediction_path, summary_path = _artifact_paths(symbol, timeframe, run_id)
    write_protocol_csv(prediction_frame, prediction_path, PREDICTION_FIELDNAMES)
    write_protocol_csv(summary_frame, summary_path, SUMMARY_FIELDNAMES)
    _log_csv_artifacts(run_id, prediction_path, summary_path)
    logger.info("Random Forest training completed. MLflow run ID: %s", run_id)
    return str(run_id)


def main(argv: list[str] | None = None) -> None:
    """Run the Random Forest command-line entrypoint."""
    args = parse_args(argv)
    setup_logging()
    run_training(args)


if __name__ == "__main__":
    main()
