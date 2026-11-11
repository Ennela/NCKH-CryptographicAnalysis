"""Train and evaluate the XGBoost next-close benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import random
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import mlflow
import numpy as np
import optuna
import pandas as pd
from sklearn.preprocessing import StandardScaler

from services.training.mlflow_utils import log_experiment_run
from services.training.models.xgboost_features import (
    AUDIT_COLUMNS,
    FEATURE_LIST,
    build_xgboost_features,
)
from services.training.models.xgboost_model import XGBoostModelWrapper
from shared.dataset.loader import (
    DEFAULT_CONTRACT_PATH,
    assert_locked_dataset,
    load_full,
)
from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)

MODEL_NAME = "xgboost"
TARGET_COLUMN = "next_close"
HORIZON = 1
DEFAULT_N_TRIALS = 1
DEFAULT_SEED = 42
EARLY_STOPPING_ROUNDS = 50
XGBOOST_N_JOBS = 1
STATUS = "preliminary"
RMSE_TOLERANCE = 1e-12
SCALER_ARTIFACT_NAME = "standard_scaler.joblib"
EXPLAIN_ARTIFACT_NAME = "explainability/feature_importance.json"
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

N_ESTIMATORS_RANGE: tuple[int, int] = (50, 200)
MAX_DEPTH_RANGE: tuple[int, int] = (3, 9)
LEARNING_RATE_RANGE: tuple[float, float] = (0.01, 0.2)
SAMPLING_RANGE: tuple[float, float] = (0.6, 1.0)
REGULARIZATION_RANGE: tuple[float, float] = (1e-4, 10.0)

ModelParams = dict[str, Any]
MetricValues = dict[str, float]


@dataclass(frozen=True)
class DatasetMetadata:
    """Locked dataset identity written to benchmark artifacts and MLflow."""

    dataset_version: str
    snapshot_name: str


@dataclass(frozen=True)
class ScaledDataset:
    """Train-fitted scaler and aligned feature/target splits."""

    scaler: StandardScaler
    X_train: pd.DataFrame
    y_train: pd.Series
    X_val: pd.DataFrame
    y_val: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series


def _positive_int(value: str) -> int:
    """Parse a strictly positive integer for argparse."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the standalone XGBoost training CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Ticker in locked dataset")
    parser.add_argument("--timeframe", required=True, help="Timeframe such as 1d")
    parser.add_argument("--n-trials", type=_positive_int, default=DEFAULT_N_TRIALS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


def set_random_seed(seed: int) -> None:
    """Seed Python and NumPy before tuning or model training."""
    random.seed(seed)
    np.random.seed(seed)


def load_dataset_metadata(
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> DatasetMetadata:
    """Read and validate the locked dataset identity and target contract."""
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    if payload.get("target") != {"mode": TARGET_COLUMN, "horizon": HORIZON}:
        raise ValueError("XGBoost requires target next_close with horizon 1.")
    dataset_version = str(payload.get("dataset_version", ""))
    snapshot_name = str(payload.get("source_snapshot_name", ""))
    if not dataset_version or not snapshot_name:
        raise ValueError("Dataset contract is missing version or snapshot metadata.")
    return DatasetMetadata(dataset_version, snapshot_name)


def _normalize_symbol(ticker: str) -> str:
    """Normalize stock and crypto symbols for artifacts and MLflow."""
    symbol = ticker.strip().replace("/", "").upper()
    if not symbol:
        raise ValueError("ticker must not be empty.")
    return symbol


def _normalize_timeframe(timeframe: str) -> str:
    """Normalize and validate the requested timeframe label."""
    normalized = timeframe.strip().lower()
    if not normalized:
        raise ValueError("timeframe must not be empty.")
    return normalized


def _validate_feature_split(frame: pd.DataFrame, split_name: str) -> None:
    """Validate one feature split and its preserved horizon-one audit fields."""
    required = {*FEATURE_LIST, *AUDIT_COLUMNS, TARGET_COLUMN, "close", "split"}
    missing = required.difference(frame.columns)
    if frame.empty or missing:
        raise ValueError(f"XGBoost {split_name} split is empty or incomplete.")
    if set(frame["split"].astype(str)) != {split_name}:
        raise ValueError(f"XGBoost {split_name} split label is invalid.")

    input_ts = pd.to_datetime(frame["input_ts"], utc=True, errors="raise")
    target_ts = pd.to_datetime(frame["target_ts"], utc=True, errors="raise")
    if input_ts.isna().any() or target_ts.isna().any():
        raise ValueError("XGBoost audit timestamps must not be missing.")
    if not input_ts.lt(target_ts).all():
        raise ValueError("XGBoost input_ts must be earlier than target_ts.")

    target = frame[TARGET_COLUMN].to_numpy(dtype=np.float64)
    actual = frame["actual_close"].to_numpy(dtype=np.float64)
    current = frame["current_close"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    features = frame.loc[:, FEATURE_LIST].to_numpy(dtype=np.float64)
    if not all(np.isfinite(values).all() for values in (target, current, features)):
        raise ValueError("XGBoost features and prices must contain only finite values.")
    if not np.array_equal(target, actual):
        raise ValueError("XGBoost actual_close must preserve next_close.")
    if not np.array_equal(current, close):
        raise ValueError("XGBoost current_close must preserve close at input_ts.")


def _scaled_frame(values: np.ndarray, source: pd.DataFrame) -> pd.DataFrame:
    """Restore feature names and indices after scaler transformation."""
    return pd.DataFrame(values, columns=FEATURE_LIST, index=source.index)


def _target_series(frame: pd.DataFrame) -> pd.Series:
    """Return one-dimensional finite next-close values for model fitting."""
    target = frame[TARGET_COLUMN].to_numpy(dtype=np.float64)
    if target.ndim != 1 or not np.isfinite(target).all():
        raise ValueError("XGBoost target must be a finite one-dimensional vector.")
    return pd.Series(target, name=TARGET_COLUMN)


def prepare_scaled_dataset(splits: dict[str, pd.DataFrame]) -> ScaledDataset:
    """Fit StandardScaler on train only, then transform validation and test."""
    for split_name in ("train", "val", "test"):
        _validate_feature_split(splits[split_name], split_name)

    train_features = splits["train"].loc[:, FEATURE_LIST].astype(np.float64)
    val_features = splits["val"].loc[:, FEATURE_LIST].astype(np.float64)
    test_features = splits["test"].loc[:, FEATURE_LIST].astype(np.float64)
    scaler = StandardScaler()
    scaler.fit(train_features)
    return ScaledDataset(
        scaler=scaler,
        X_train=_scaled_frame(scaler.transform(train_features), train_features),
        y_train=_target_series(splits["train"]),
        X_val=_scaled_frame(scaler.transform(val_features), val_features),
        y_val=_target_series(splits["val"]),
        X_test=_scaled_frame(scaler.transform(test_features), test_features),
        y_test=_target_series(splits["test"]),
    )


def _trial_params(trial: optuna.Trial, seed: int) -> ModelParams:
    """Sample one configuration from the existing XGBoost search space."""
    return {
        "n_estimators": trial.suggest_int("n_estimators", *N_ESTIMATORS_RANGE),
        "max_depth": trial.suggest_int("max_depth", *MAX_DEPTH_RANGE),
        "learning_rate": trial.suggest_float(
            "learning_rate", *LEARNING_RATE_RANGE, log=True
        ),
        "subsample": trial.suggest_float("subsample", *SAMPLING_RANGE),
        "colsample_bytree": trial.suggest_float("colsample_bytree", *SAMPLING_RANGE),
        "reg_alpha": trial.suggest_float("reg_alpha", *REGULARIZATION_RANGE, log=True),
        "reg_lambda": trial.suggest_float(
            "reg_lambda", *REGULARIZATION_RANGE, log=True
        ),
        "objective": "reg:squarederror",
        "random_state": seed,
        "n_jobs": XGBOOST_N_JOBS,
    }


def objective_optuna(
    trial: optuna.Trial,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    seed: int,
) -> float:
    """Minimize validation MAE without accepting or touching test data."""
    model = XGBoostModelWrapper(params=_trial_params(trial, seed))
    model.fit(
        X_train,
        y_train,
        X_val=X_val,
        y_val=y_val,
        early_stopping_rounds=EARLY_STOPPING_ROUNDS,
    )
    predictions = model.predict(X_val)
    return float(np.mean(np.abs(y_val.to_numpy() - predictions)))


def optimize_params(data: ScaledDataset, n_trials: int, seed: int) -> ModelParams:
    """Tune hyperparameters using only the train and validation splits."""
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    study.optimize(
        lambda trial: objective_optuna(
            trial,
            data.X_train,
            data.y_train,
            data.X_val,
            data.y_val,
            seed,
        ),
        n_trials=n_trials,
    )
    logger.info("Best Optuna validation MAE: %.6f", study.best_value)
    return {
        **study.best_params,
        "objective": "reg:squarederror",
        "random_state": seed,
        "n_jobs": XGBOOST_N_JOBS,
    }


def train_final_model(
    data: ScaledDataset,
    best_params: ModelParams,
) -> XGBoostModelWrapper:
    """Fit the final model on train with early stopping on validation."""
    model = XGBoostModelWrapper(params=best_params)
    model.fit(
        data.X_train,
        data.y_train,
        X_val=data.X_val,
        y_val=data.y_val,
        early_stopping_rounds=EARLY_STOPPING_ROUNDS,
    )
    return model


def _metric_vector(name: str, values: Any) -> np.ndarray:
    """Convert one metric input to a finite, non-empty one-dimensional vector."""
    vector = np.asarray(values, dtype=np.float64)
    if vector.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional to prevent broadcasting.")
    if vector.size == 0 or not np.isfinite(vector).all():
        raise ValueError(f"{name} must be non-empty and contain only finite values.")
    return vector


def build_naive_predictions(current_close: Any) -> np.ndarray:
    """Return the locked horizon-one Naive forecast: current close."""
    return _metric_vector("current_close", current_close).copy()


def _error_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
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


def validate_metric_relationships(metrics: MetricValues) -> None:
    """Enforce finite metrics, valid direction rates, and RMSE inequalities."""
    if not all(np.isfinite(value) for value in metrics.values()):
        raise ValueError("Metric summary contains NaN or Inf.")
    if metrics["rmse"] + RMSE_TOLERANCE < metrics["mae"]:
        raise ValueError("RMSE cannot be smaller than MAE.")
    if metrics["naive_rmse"] + RMSE_TOLERANCE < metrics["naive_mae"]:
        raise ValueError("Naive RMSE cannot be smaller than Naive MAE.")
    for name in ("directional_accuracy", "naive_directional_accuracy"):
        if not 0.0 <= metrics[name] <= 1.0:
            raise ValueError(f"{name} must be in the interval [0, 1].")


def evaluate_metric_vectors(
    y_true: Any,
    y_pred: Any,
    current_close: Any,
) -> MetricValues:
    """Evaluate model and Naive predictions on the same aligned test vectors."""
    actual = _metric_vector("y_true", y_true)
    predicted = _metric_vector("y_pred", y_pred)
    current = _metric_vector("current_close", current_close)
    if actual.shape != predicted.shape or actual.shape != current.shape:
        raise ValueError("Metric vectors must have identical shapes.")

    naive = build_naive_predictions(current)
    mae, rmse, mape_pct = _error_metrics(actual, predicted)
    naive_mae, naive_rmse, naive_mape_pct = _error_metrics(actual, naive)
    if naive_rmse == 0.0:
        raise ValueError("Improvement is undefined when naive RMSE is zero.")
    metrics = {
        "mae": mae,
        "rmse": rmse,
        "mape_pct": mape_pct,
        "directional_accuracy": _directional_accuracy(actual, predicted, current),
        "naive_mae": naive_mae,
        "naive_rmse": naive_rmse,
        "naive_mape_pct": naive_mape_pct,
        "naive_directional_accuracy": _directional_accuracy(actual, naive, current),
        "improvement_vs_naive_rmse_pct": ((naive_rmse - rmse) / naive_rmse * 100.0),
    }
    validate_metric_relationships(metrics)
    return metrics


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
    """Build the ordered shared manifest from preserved XGBoost metadata."""
    _validate_feature_split(test_frame, "test")
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
    input_ts = pd.to_datetime(manifest["input_ts"], utc=True)
    target_ts = pd.to_datetime(manifest["target_ts"], utc=True)
    if not input_ts.lt(target_ts).all() or not target_ts.is_monotonic_increasing:
        raise ValueError("Test manifest timestamps are not aligned chronologically.")
    numeric = manifest[["current_close", "actual_close"]].to_numpy(np.float64)
    if not np.isfinite(numeric).all():
        raise ValueError("Test manifest contains NaN or Inf.")
    return manifest.loc[:, MANIFEST_FIELDNAMES]


def calculate_test_manifest_sha256(manifest: pd.DataFrame) -> str:
    """Hash the canonical shared eight-column manifest representation."""
    if tuple(manifest.columns) != MANIFEST_FIELDNAMES:
        raise ValueError("Test manifest schema or column order is invalid.")
    canonical = manifest.copy()
    canonical["input_ts"] = canonical["input_ts"].map(_utc_timestamp)
    canonical["target_ts"] = canonical["target_ts"].map(_utc_timestamp)
    canonical = canonical.sort_values("target_ts", kind="mergesort", ignore_index=True)
    if (
        canonical["input_ts"].duplicated().any()
        or canonical["target_ts"].duplicated().any()
    ):
        raise ValueError("Test manifest timestamps must be unique before hashing.")
    if not (
        pd.to_datetime(canonical["input_ts"], utc=True)
        < pd.to_datetime(canonical["target_ts"], utc=True)
    ).all():
        raise ValueError("Manifest input_ts must precede target_ts before hashing.")

    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(MANIFEST_HASH_FIELDNAMES)
    for row in canonical.loc[:, MANIFEST_HASH_FIELDNAMES].itertuples(index=False):
        values = list(row)
        values[6] = _canonical_float(values[6])
        values[7] = _canonical_float(values[7])
        writer.writerow(values)
    return hashlib.sha256(stream.getvalue().encode("utf-8")).hexdigest()


def _validate_manifest_hash(manifest_hash: str) -> None:
    """Require the lowercase 64-character SHA-256 representation."""
    if len(manifest_hash) != 64 or set(manifest_hash).difference("0123456789abcdef"):
        raise ValueError("test_manifest_sha256 must be 64 lowercase hex characters.")


def build_prediction_frame(
    manifest: pd.DataFrame,
    predictions: Any,
    manifest_hash: str,
    run_id: str,
    seed: int,
) -> pd.DataFrame:
    """Join finite predictions to every manifest target without reordering."""
    _validate_manifest_hash(manifest_hash)
    predicted_close = _metric_vector("predicted_close", predictions)
    if len(predicted_close) != len(manifest):
        raise ValueError("Prediction count must equal the test manifest count.")
    if not run_id:
        raise ValueError("run_id must not be empty.")
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
    """Build the exact one-row protocol metrics summary."""
    _validate_manifest_hash(manifest_hash)
    validate_metric_relationships(metrics)
    if n_samples <= 0 or not run_id:
        raise ValueError("Metrics summary requires samples and a run ID.")
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
    """Write one exact-schema UTF-8 CSV without overwriting an earlier run."""
    if tuple(frame.columns) != fieldnames:
        raise ValueError("CSV schema or column order does not match the protocol.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(frame.to_dict(orient="records"))


def log_training_run(
    metadata: DatasetMetadata,
    symbol: str,
    timeframe: str,
    manifest_hash: str,
    seed: int,
    n_trials: int,
    best_params: ModelParams,
    metrics: MetricValues,
    model: XGBoostModelWrapper,
) -> str:
    """Log protocol metadata, hyperparameters, metrics, and the model."""
    live_model_params = {
        name: value
        for name, value in model.model.get_params().items()
        if value is not None
        and not (isinstance(value, float) and not np.isfinite(value))
    }
    logged_params = {
        **best_params,
        **live_model_params,
        "dataset_version": metadata.dataset_version,
        "snapshot_name": metadata.snapshot_name,
        "test_manifest_sha256": manifest_hash,
        "symbol": symbol,
        "timeframe": timeframe,
        "model": MODEL_NAME,
        "horizon": HORIZON,
        "seed": seed,
        "n_trials": n_trials,
        "feature_list": ",".join(FEATURE_LIST),
        "target": TARGET_COLUMN,
    }
    if model.best_iteration is not None:
        logged_params["best_iteration"] = model.best_iteration
    return str(
        log_experiment_run(
            experiment_name=f"{symbol}_{timeframe}_{MODEL_NAME}",
            run_name=f"{MODEL_NAME}_{symbol}_{timeframe}",
            params=logged_params,
            metrics=metrics,
            model=model.model,
            model_name_in_registry=f"{symbol}_{timeframe}_{MODEL_NAME}",
        )
    )


def _artifact_paths(symbol: str, timeframe: str, run_id: str) -> tuple[Path, Path]:
    """Return unique prediction and summary paths for one MLflow run."""
    filename = f"{symbol}_{timeframe}_{run_id}.csv"
    return PREDICTION_ROOT / filename, SUMMARY_ROOT / filename


def _log_run_artifacts(
    run_id: str,
    scaler: StandardScaler,
    prediction_path: Path,
    summary_path: Path,
) -> None:
    """Attach scaler and protocol CSV files to their originating MLflow run."""
    with tempfile.TemporaryDirectory(prefix="xgboost_scaler_") as temp_dir:
        scaler_path = Path(temp_dir) / SCALER_ARTIFACT_NAME
        joblib.dump(scaler, scaler_path)
        with mlflow.start_run(run_id=run_id):
            mlflow.log_artifact(str(scaler_path), artifact_path="preprocessing")
            mlflow.log_artifact(str(prediction_path), artifact_path="predictions")
            mlflow.log_artifact(str(summary_path), artifact_path="metrics")


def build_explainability_payload(
    model: XGBoostModelWrapper,
    features: pd.DataFrame,
) -> dict[str, Any]:
    """Build the SHAP global-importance payload served by /api/v1/explain.

    Input: the fitted wrapper and the scaled feature frame SHAP is computed
    on (test split). Output: JSON-safe dict with per-feature XGBoost gain
    importance and mean |SHAP| across the provided samples.
    """
    shap_values = np.asarray(model.calculate_shap_values(features))
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    importances = model.get_feature_importances(list(features.columns))
    return {
        "method": "shap_tree_explainer",
        "model": MODEL_NAME,
        "feature_list": list(features.columns),
        "n_samples": int(len(features)),
        "features": [
            {
                "feature": name,
                "importance": float(importances[name]),
                "mean_abs_shap": float(mean_abs_shap[index]),
            }
            for index, name in enumerate(features.columns)
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _log_explainability_artifact(
    run_id: str,
    model: XGBoostModelWrapper,
    features: pd.DataFrame,
) -> None:
    """Attach the SHAP payload to the run for the inference /explain endpoint."""
    payload = build_explainability_payload(model, features)
    with mlflow.start_run(run_id=run_id):
        mlflow.log_dict(payload, EXPLAIN_ARTIFACT_NAME)


def _validate_test_alignment(
    data: ScaledDataset,
    manifest: pd.DataFrame,
) -> None:
    """Require model test targets to match every manifest target in order."""
    model_targets = _metric_vector("y_test", data.y_test)
    manifest_targets = _metric_vector("manifest actual_close", manifest["actual_close"])
    if not np.array_equal(model_targets, manifest_targets):
        raise ValueError("XGBoost test targets do not align with the test manifest.")


def _write_and_log_outputs(
    metadata: DatasetMetadata,
    symbol: str,
    timeframe: str,
    manifest: pd.DataFrame,
    manifest_hash: str,
    predictions: np.ndarray,
    metrics: MetricValues,
    run_id: str,
    seed: int,
    scaler: StandardScaler,
) -> None:
    """Build, write, and log both protocol CSV artifacts for one run."""
    prediction_frame = build_prediction_frame(
        manifest, predictions, manifest_hash, run_id, seed
    )
    summary_frame = build_summary_frame(
        metadata,
        symbol,
        timeframe,
        manifest_hash,
        metrics,
        len(manifest),
        run_id,
        seed,
    )
    prediction_path, summary_path = _artifact_paths(symbol, timeframe, run_id)
    write_protocol_csv(prediction_frame, prediction_path, PREDICTION_FIELDNAMES)
    write_protocol_csv(summary_frame, summary_path, SUMMARY_FIELDNAMES)
    _log_run_artifacts(run_id, scaler, prediction_path, summary_path)


def run_training(args: argparse.Namespace) -> str:
    """Execute locked-data tuning, training, evaluation, export, and logging."""
    set_random_seed(args.seed)
    assert_locked_dataset()
    metadata = load_dataset_metadata()
    symbol = _normalize_symbol(args.ticker)
    timeframe = _normalize_timeframe(args.timeframe)
    full_frame = load_full(symbol, timeframe)
    splits = build_xgboost_features(full_frame)
    data = prepare_scaled_dataset(splits)
    best_params = optimize_params(data, args.n_trials, args.seed)
    model = train_final_model(data, best_params)

    manifest = build_test_manifest(splits["test"], metadata, symbol, timeframe)
    manifest_hash = calculate_test_manifest_sha256(manifest)
    _validate_test_alignment(data, manifest)
    predictions = model.predict(data.X_test)
    metrics = evaluate_metric_vectors(
        manifest["actual_close"], predictions, manifest["current_close"]
    )
    run_id = log_training_run(
        metadata,
        symbol,
        timeframe,
        manifest_hash,
        args.seed,
        args.n_trials,
        best_params,
        metrics,
        model,
    )

    _write_and_log_outputs(
        metadata,
        symbol,
        timeframe,
        manifest,
        manifest_hash,
        predictions,
        metrics,
        run_id,
        args.seed,
        data.scaler,
    )
    _log_explainability_artifact(run_id, model, data.X_test)
    logger.info(
        "XGBoost benchmark completed: run_id=%s manifest=%s samples=%d",
        run_id,
        manifest_hash,
        len(manifest),
    )
    return run_id


def main(argv: list[str] | None = None) -> None:
    """Run the XGBoost command-line entrypoint."""
    args = parse_args(argv)
    setup_logging()
    run_training(args)


if __name__ == "__main__":
    main()
