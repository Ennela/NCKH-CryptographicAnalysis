"""Run the deterministic ARIMA rolling one-step benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import random
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

from services.training.models.arima_model import ARIMABaseline, DEFAULT_ARIMA_ORDER
from shared.dataset.loader import (
    DEFAULT_CONTRACT_PATH,
    assert_locked_dataset,
    load_full,
)
from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)

MODEL_NAME = "arima"
TARGET_COLUMN = "next_close"
DEFAULT_SEED = 42
HORIZON = 1
STATUS = "preliminary"
PRE_TEST_STATE_ROLE = "pre_test_deployable"
RMSE_TOLERANCE = 1e-12
REPO_ROOT = Path(__file__).resolve().parents[2]
PREDICTION_ROOT = REPO_ROOT / "artifacts" / "predictions" / MODEL_NAME
SUMMARY_ROOT = REPO_ROOT / "artifacts" / "metrics" / MODEL_NAME

PAIR_FIELDNAMES: tuple[str, ...] = (
    "input_ts",
    "target_ts",
    "current_close",
    "actual_close",
)
MANIFEST_FIELDNAMES: tuple[str, ...] = (
    "dataset_version",
    "snapshot_name",
    "symbol",
    "timeframe",
    "split",
    *PAIR_FIELDNAMES,
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
METRIC_FIELDNAMES: tuple[str, ...] = SUMMARY_FIELDNAMES[8:17]

MetricValues = dict[str, float]


class OneStepForecaster(Protocol):
    """Operations required by the auditable rolling evaluation loop."""

    def fit(self, prices: Sequence[float] | np.ndarray) -> Any:
        """Fit chronological training observations."""

    def forecast_one(self) -> float:
        """Forecast the observation immediately after current history."""

    def update(self, actual_close: float) -> None:
        """Append one observation that has become available."""

    def snapshot(self) -> OneStepForecaster:
        """Return an independent serialized snapshot of the current state."""


@dataclass(frozen=True)
class DatasetMetadata:
    """Locked dataset identity copied into benchmark artifacts."""

    dataset_version: str
    snapshot_name: str


@dataclass(frozen=True)
class PreparedRollingData:
    """Chronological train history and aligned validation/test target pairs."""

    train_close: np.ndarray
    train_end_ts: pd.Timestamp
    train_end_close: float
    validation_pairs: pd.DataFrame
    test_pairs: pd.DataFrame


@dataclass(frozen=True)
class RollingSplitResult:
    """One split's predictions plus the history boundary used per forecast."""

    pairs: pd.DataFrame
    predictions: np.ndarray
    history_end_ts: np.ndarray

    def __len__(self) -> int:
        return len(self.predictions)


@dataclass(frozen=True)
class RollingEvaluation:
    """Validation-first and test rolling results from one fitted model."""

    pre_test_model: OneStepForecaster
    evaluation_model: OneStepForecaster
    validation: RollingSplitResult
    test: RollingSplitResult


@dataclass(frozen=True)
class ModelStateMetadata:
    """Auditable boundary metadata for the deployable pre-test artifact."""

    model: str
    state_role: str
    observation_count: int
    history_end_ts: str
    history_end_value: float
    order_p: int
    order_d: int
    order_q: int
    horizon: int
    contains_test_history: bool


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the fixed ARIMA benchmark command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Ticker in locked dataset")
    parser.add_argument("--timeframe", required=True, help="Timeframe such as 1d")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


def set_random_seed(seed: int) -> None:
    """Accept the shared seed while documenting ARIMA determinism."""
    random.seed(seed)
    np.random.seed(seed)
    logger.info(
        "Benchmark seed set to %d for metadata consistency; ARIMA%s is "
        "deterministic and does not consume it during fitting.",
        seed,
        DEFAULT_ARIMA_ORDER,
    )


def load_dataset_metadata(
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> DatasetMetadata:
    """Read and validate locked next-close dataset metadata."""
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    if payload.get("target") != {"mode": TARGET_COLUMN, "horizon": 1}:
        raise ValueError("ARIMA requires target next_close with horizon 1.")
    dataset_version = str(payload.get("dataset_version", ""))
    snapshot_name = str(payload.get("source_snapshot_name", ""))
    if not dataset_version or not snapshot_name:
        raise ValueError("Dataset contract is missing version or snapshot metadata.")
    return DatasetMetadata(dataset_version, snapshot_name)


def _normalise_full_frame(full_frame: pd.DataFrame) -> pd.DataFrame:
    """Validate locked-loader output and return chronological typed values."""
    required = {"ts", "close", TARGET_COLUMN, "split"}
    missing = required.difference(full_frame.columns)
    if full_frame.empty or missing:
        raise ValueError(f"Locked ARIMA frame is empty or missing columns: {missing}.")

    frame = full_frame.loc[:, ["ts", "close", TARGET_COLUMN, "split"]].copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="raise")
    frame["close"] = pd.to_numeric(frame["close"], errors="raise").astype(float)
    frame[TARGET_COLUMN] = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce").astype(
        float
    )
    frame["split"] = frame["split"].astype(str)

    if frame["ts"].isna().any() or frame["ts"].duplicated().any():
        raise ValueError("Locked ARIMA timestamps must be present and unique.")
    if not frame["ts"].is_monotonic_increasing:
        raise ValueError("Locked ARIMA rows must be chronological.")
    if not np.isfinite(frame["close"].to_numpy(dtype=np.float64)).all():
        raise ValueError("Locked ARIMA close values must be finite.")

    split_order = {"train": 0, "val": 1, "test": 2}
    if set(frame["split"]) != set(split_order):
        raise ValueError("Locked ARIMA data must contain train, val, and test splits.")
    split_codes = frame["split"].map(split_order).to_numpy(dtype=np.int64)
    if np.any(np.diff(split_codes) < 0):
        raise ValueError("Locked ARIMA splits must be chronological and contiguous.")
    return frame.reset_index(drop=True)


def _build_split_pairs(frame: pd.DataFrame, split: str) -> pd.DataFrame:
    """Build horizon-one pairs without crossing a locked split boundary."""
    split_frame = frame.loc[frame["split"].eq(split)].reset_index(drop=True)
    if len(split_frame) < 2:
        raise ValueError(f"ARIMA {split} split requires at least two observations.")

    expected_targets = split_frame["close"].shift(-1)
    provided_targets = split_frame[TARGET_COLUMN]
    if not np.allclose(
        provided_targets.iloc[:-1].to_numpy(dtype=np.float64),
        expected_targets.iloc[:-1].to_numpy(dtype=np.float64),
        rtol=0.0,
        atol=0.0,
    ):
        raise ValueError(f"ARIMA {split} next_close targets are off by one.")
    if not pd.isna(provided_targets.iloc[-1]):
        raise ValueError(f"ARIMA {split} target crosses the split boundary.")

    pairs = pd.DataFrame(
        {
            "input_ts": split_frame["ts"].iloc[:-1].to_numpy(),
            "target_ts": split_frame["ts"].iloc[1:].to_numpy(),
            "current_close": split_frame["close"].iloc[:-1].to_numpy(),
            "actual_close": split_frame["close"].iloc[1:].to_numpy(),
        }
    )
    if not (pairs["input_ts"] < pairs["target_ts"]).all():
        raise ValueError(f"ARIMA {split} input_ts must precede target_ts.")
    if not pairs["target_ts"].is_monotonic_increasing:
        raise ValueError(f"ARIMA {split} targets must be chronological.")
    numeric = pairs[["current_close", "actual_close"]].to_numpy(dtype=np.float64)
    if not np.isfinite(numeric).all():
        raise ValueError(f"ARIMA {split} target pairs contain NaN or Inf.")
    return pairs.loc[:, PAIR_FIELDNAMES]


def prepare_rolling_data(full_frame: pd.DataFrame) -> PreparedRollingData:
    """Prepare train history and exact validation/test horizon-one pairs."""
    frame = _normalise_full_frame(full_frame)
    train_frame = frame.loc[frame["split"].eq("train")].reset_index(drop=True)
    if len(train_frame) < 4:
        raise ValueError("ARIMA train split requires at least four observations.")
    _build_split_pairs(frame, "train")
    train_close = train_frame["close"].to_numpy(dtype=np.float64)
    return PreparedRollingData(
        train_close=train_close,
        train_end_ts=pd.Timestamp(train_frame["ts"].iloc[-1]),
        train_end_close=float(train_close[-1]),
        validation_pairs=_build_split_pairs(frame, "val"),
        test_pairs=_build_split_pairs(frame, "test"),
    )


def _roll_one_split(
    model: OneStepForecaster,
    pairs: pd.DataFrame,
    history_end_ts: pd.Timestamp,
    history_end_close: float,
    split: str,
) -> tuple[RollingSplitResult, pd.Timestamp, float]:
    """Forecast one split sequentially and append actuals only after prediction."""
    predictions: list[float] = []
    history_boundaries: list[pd.Timestamp] = []

    for row in pairs.itertuples(index=False):
        input_ts = pd.Timestamp(row.input_ts)
        target_ts = pd.Timestamp(row.target_ts)
        current_close = float(row.current_close)
        actual_close = float(row.actual_close)

        if history_end_ts < input_ts:
            model.update(current_close)
            history_end_ts = input_ts
            history_end_close = current_close
        elif history_end_ts > input_ts:
            raise ValueError(
                f"ARIMA {split} history contains data after input_ts={input_ts}."
            )

        if history_end_close != current_close:
            raise ValueError(f"ARIMA {split} current_close does not match history.")
        if history_end_ts != input_ts:
            raise ValueError(f"ARIMA {split} history must end exactly at input_ts.")

        predicted_close = float(model.forecast_one())
        if not np.isfinite(predicted_close):
            raise ValueError(f"ARIMA {split} forecast contains NaN or Inf.")
        predictions.append(predicted_close)
        history_boundaries.append(history_end_ts)

        model.update(actual_close)
        history_end_ts = target_ts
        history_end_close = actual_close

    prediction_vector = np.asarray(predictions, dtype=np.float64)
    if len(prediction_vector) != len(pairs):
        raise ValueError(f"ARIMA {split} prediction count must equal target count.")
    result = RollingSplitResult(
        pairs=pairs.copy(),
        predictions=prediction_vector,
        history_end_ts=np.asarray(history_boundaries, dtype=object),
    )
    return result, history_end_ts, history_end_close


def run_rolling_evaluation(
    prepared: PreparedRollingData,
    model_factory: Callable[[], OneStepForecaster] = ARIMABaseline,
) -> RollingEvaluation:
    """Fit train, roll through validation, then evaluate test one step at a time."""
    model = model_factory()
    model.fit(prepared.train_close)
    validation, history_end_ts, history_end_close = _roll_one_split(
        model,
        prepared.validation_pairs,
        prepared.train_end_ts,
        prepared.train_end_close,
        "validation",
    )
    pre_test_model = model
    evaluation_model = pre_test_model.snapshot()
    if evaluation_model is pre_test_model:
        raise RuntimeError(
            "ARIMA evaluation model must be independent from pre-test state."
        )
    test, _, _ = _roll_one_split(
        evaluation_model,
        prepared.test_pairs,
        history_end_ts,
        history_end_close,
        "test",
    )
    return RollingEvaluation(
        pre_test_model=pre_test_model,
        evaluation_model=evaluation_model,
        validation=validation,
        test=test,
    )


def build_model_state_metadata(
    model: ARIMABaseline,
    history_end_ts: Any,
    history_end_value: float,
) -> ModelStateMetadata:
    """Build and validate metadata for the immutable pre-test artifact."""
    expected_value = float(history_end_value)
    if not np.isfinite(expected_value):
        raise ValueError("ARIMA pre-test history end value must be finite.")
    if not np.isclose(model.last_observed_value, expected_value, rtol=0.0, atol=0.0):
        raise ValueError("ARIMA pre-test artifact does not end at the expected value.")
    order_p, order_d, order_q = model.order
    return ModelStateMetadata(
        model=MODEL_NAME,
        state_role=PRE_TEST_STATE_ROLE,
        observation_count=model.observation_count,
        history_end_ts=_utc_timestamp(history_end_ts),
        history_end_value=expected_value,
        order_p=order_p,
        order_d=order_d,
        order_q=order_q,
        horizon=HORIZON,
        contains_test_history=False,
    )


def validate_model_state_metadata(
    model: ARIMABaseline,
    state_metadata: ModelStateMetadata,
) -> None:
    """Reject metadata that does not describe the fitted pre-test artifact."""
    expected_identity = (
        state_metadata.model == MODEL_NAME
        and state_metadata.state_role == PRE_TEST_STATE_ROLE
        and state_metadata.horizon == HORIZON
        and state_metadata.contains_test_history is False
    )
    if not expected_identity:
        raise ValueError("ARIMA model metadata does not identify a pre-test artifact.")
    if model.order != (
        state_metadata.order_p,
        state_metadata.order_d,
        state_metadata.order_q,
    ):
        raise ValueError("ARIMA model metadata order does not match the artifact.")
    if model.observation_count != state_metadata.observation_count:
        raise ValueError("ARIMA model metadata observation count does not match.")
    if not np.isclose(
        model.last_observed_value,
        state_metadata.history_end_value,
        rtol=0.0,
        atol=0.0,
    ):
        raise ValueError("ARIMA model metadata final value does not match.")
    if _utc_timestamp(state_metadata.history_end_ts) != state_metadata.history_end_ts:
        raise ValueError("ARIMA model metadata history timestamp is not canonical UTC.")


def prepare_pre_test_artifact(
    prepared: PreparedRollingData,
    evaluation: RollingEvaluation,
) -> tuple[ARIMABaseline, ModelStateMetadata]:
    """Validate both state boundaries and return the deployable pre-test model."""
    if not isinstance(evaluation.pre_test_model, ARIMABaseline):
        raise TypeError(
            "Production ARIMA evaluation returned an unexpected pre-test model."
        )
    if not isinstance(evaluation.evaluation_model, ARIMABaseline):
        raise TypeError("Production ARIMA evaluation returned an unexpected evaluator.")

    expected_pre_test_count = (
        len(prepared.train_close) + len(prepared.validation_pairs) + 1
    )
    expected_post_test_count = expected_pre_test_count + len(prepared.test_pairs) + 1
    if evaluation.pre_test_model.observation_count != expected_pre_test_count:
        raise ValueError("ARIMA pre-test artifact observation count is inconsistent.")
    if evaluation.evaluation_model.observation_count != expected_post_test_count:
        raise ValueError("ARIMA evaluator must contain the full post-test history.")

    state_metadata = build_model_state_metadata(
        evaluation.pre_test_model,
        prepared.validation_pairs["target_ts"].iloc[-1],
        float(prepared.validation_pairs["actual_close"].iloc[-1]),
    )
    validate_model_state_metadata(evaluation.pre_test_model, state_metadata)
    return evaluation.pre_test_model, state_metadata


def _metric_vector(name: str, values: Any) -> np.ndarray:
    """Return one non-empty finite float vector for metric calculation."""
    vector = np.asarray(values, dtype=np.float64)
    if vector.ndim != 1 or vector.size == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional vector.")
    if not np.isfinite(vector).all():
        raise ValueError(f"{name} contains NaN or Inf.")
    return vector


def _error_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
) -> tuple[float, float, float]:
    """Calculate MAE, RMSE, and percentage MAPE on identical targets."""
    if np.any(actual == 0.0):
        raise ValueError("MAPE is undefined when actual_close contains zero.")
    errors = actual - predicted
    return (
        float(np.mean(np.abs(errors))),
        float(np.sqrt(np.mean(np.square(errors)))),
        float(np.mean(np.abs(errors / actual)) * 100.0),
    )


def _directional_accuracy(
    actual: np.ndarray,
    predicted: np.ndarray,
    current: np.ndarray,
) -> float:
    """Calculate direction accuracy relative to each manifest current close."""
    return float(np.mean(np.sign(predicted - current) == np.sign(actual - current)))


def validate_metric_relationships(metrics: MetricValues) -> None:
    """Reject non-finite metrics and impossible RMSE/MAE relationships."""
    if set(metrics) != set(METRIC_FIELDNAMES):
        raise ValueError("ARIMA metric keys do not match benchmark schema.")
    if not all(np.isfinite(value) for value in metrics.values()):
        raise ValueError("ARIMA metric summary contains NaN or Inf.")
    if metrics["rmse"] + RMSE_TOLERANCE < metrics["mae"]:
        raise ValueError("RMSE cannot be smaller than MAE.")
    if metrics["naive_rmse"] + RMSE_TOLERANCE < metrics["naive_mae"]:
        raise ValueError("Naive RMSE cannot be smaller than Naive MAE.")
    for name in ("directional_accuracy", "naive_directional_accuracy"):
        if not 0.0 <= metrics[name] <= 1.0:
            raise ValueError(f"{name} must be between zero and one.")


def evaluate_predictions(
    y_true: Any,
    y_pred: Any,
    current_close: Any,
) -> MetricValues:
    """Evaluate ARIMA and locked Naive predictions on the same manifest."""
    actual = _metric_vector("y_true", y_true)
    predicted = _metric_vector("y_pred", y_pred)
    current = _metric_vector("current_close", current_close)
    if actual.shape != predicted.shape or actual.shape != current.shape:
        raise ValueError("ARIMA metric vectors must have identical shapes.")

    mae, rmse, mape_pct = _error_metrics(actual, predicted)
    naive_mae, naive_rmse, naive_mape_pct = _error_metrics(actual, current)
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
        "naive_directional_accuracy": _directional_accuracy(actual, current, current),
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
    """Serialize one finite float with the protocol round-trip format."""
    number = float(value)
    if not np.isfinite(number):
        raise ValueError("Manifest numeric values must be finite.")
    formatted = format(number, ".17g")
    return "0" if formatted == "-0" else formatted


def build_test_manifest(
    test_pairs: pd.DataFrame,
    metadata: DatasetMetadata,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    """Build the shared protocol manifest from aligned test pairs."""
    manifest = pd.DataFrame(
        {
            "dataset_version": metadata.dataset_version,
            "snapshot_name": metadata.snapshot_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "split": "test",
            "input_ts": [_utc_timestamp(value) for value in test_pairs["input_ts"]],
            "target_ts": [_utc_timestamp(value) for value in test_pairs["target_ts"]],
            "current_close": test_pairs["current_close"].to_numpy(dtype=np.float64),
            "actual_close": test_pairs["actual_close"].to_numpy(dtype=np.float64),
        }
    ).sort_values("target_ts", kind="mergesort", ignore_index=True)
    if manifest.empty:
        raise ValueError("ARIMA test manifest must not be empty.")
    if (
        manifest["input_ts"].duplicated().any()
        or manifest["target_ts"].duplicated().any()
    ):
        raise ValueError("ARIMA test manifest timestamps must be unique.")
    if not (manifest["input_ts"] < manifest["target_ts"]).all():
        raise ValueError("ARIMA manifest input_ts must precede target_ts.")
    numeric = manifest[["current_close", "actual_close"]].to_numpy(dtype=np.float64)
    if not np.isfinite(numeric).all():
        raise ValueError("ARIMA test manifest contains NaN or Inf.")
    return manifest.loc[:, MANIFEST_FIELDNAMES]


def calculate_test_manifest_sha256(manifest: pd.DataFrame) -> str:
    """Hash the canonical shared eight-column manifest representation."""
    if tuple(manifest.columns) != MANIFEST_FIELDNAMES:
        raise ValueError("ARIMA test manifest schema or column order is invalid.")
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
    """Join finite ARIMA predictions to every manifest target in order."""
    predicted = _metric_vector("predicted_close", predictions)
    if len(predicted) != len(manifest):
        raise ValueError("ARIMA prediction count must equal manifest target count.")
    frame = manifest.copy()
    frame.insert(2, "test_manifest_sha256", manifest_hash)
    frame.insert(5, "model", MODEL_NAME)
    frame["predicted_close"] = predicted
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
    """Build one exact-schema benchmark metrics row without MSE."""
    validate_metric_relationships(metrics)
    if n_samples <= 0:
        raise ValueError("ARIMA metrics summary requires at least one sample.")
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
    """Write exact-schema UTF-8 CSV without overwriting an earlier run."""
    if tuple(frame.columns) != fieldnames:
        raise ValueError("ARIMA CSV schema or column order is invalid.")
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
    metrics: MetricValues,
    model: ARIMABaseline,
    state_metadata: ModelStateMetadata,
    validation_steps: int,
    test_steps: int,
) -> str:
    """Log the deterministic order, validation walk, model, and test metrics."""
    import mlflow
    import mlflow.statsmodels

    from services.training.mlflow_utils import init_mlflow

    validate_model_state_metadata(model, state_metadata)
    init_mlflow()
    mlflow.set_experiment(f"{symbol}_{timeframe}_{MODEL_NAME}")
    with mlflow.start_run(run_name=f"{MODEL_NAME}_{symbol}_{timeframe}") as run:
        mlflow.log_params(
            {
                "order": str(model.order),
                "order_p": state_metadata.order_p,
                "order_d": state_metadata.order_d,
                "order_q": state_metadata.order_q,
                "dataset_version": metadata.dataset_version,
                "snapshot_name": metadata.snapshot_name,
                "test_manifest_sha256": manifest_hash,
                "symbol": symbol,
                "timeframe": timeframe,
                "model": state_metadata.model,
                "target": TARGET_COLUMN,
                "horizon": state_metadata.horizon,
                "seed": seed,
                "state_role": state_metadata.state_role,
                "observation_count": state_metadata.observation_count,
                "history_end_ts": state_metadata.history_end_ts,
                "history_end_value": state_metadata.history_end_value,
                "contains_test_history": state_metadata.contains_test_history,
                "deterministic": True,
                "refit_during_rolling": False,
                "validation_steps": validation_steps,
                "test_steps": test_steps,
            }
        )
        mlflow.log_metrics(metrics)
        mlflow.log_dict(
            {
                **asdict(state_metadata),
                "dataset_version": metadata.dataset_version,
                "snapshot_name": metadata.snapshot_name,
                "test_manifest_sha256": manifest_hash,
                "symbol": symbol,
                "timeframe": timeframe,
            },
            "metadata/pre_test_model.json",
        )
        mlflow.statsmodels.log_model(
            model.fitted_model,
            artifact_path="model",
            registered_model_name=f"{symbol}_{timeframe}_{MODEL_NAME}",
        )
        return str(run.info.run_id)


def _artifact_paths(symbol: str, timeframe: str, run_id: str) -> tuple[Path, Path]:
    """Return unique prediction and summary paths for one MLflow run."""
    filename = f"{symbol}_{timeframe}_{run_id}.csv"
    return PREDICTION_ROOT / filename, SUMMARY_ROOT / filename


def _log_run_artifacts(run_id: str, prediction_path: Path, summary_path: Path) -> None:
    """Attach both benchmark CSV files to their existing MLflow run."""
    import mlflow

    with mlflow.start_run(run_id=run_id):
        mlflow.log_artifact(str(prediction_path), artifact_path="predictions")
        mlflow.log_artifact(str(summary_path), artifact_path="metrics")


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
) -> None:
    """Write protocol outputs and attach them to the MLflow run."""
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
    _log_run_artifacts(run_id, prediction_path, summary_path)


def run_training(args: argparse.Namespace) -> str:
    """Execute locked-data ARIMA rolling evaluation and artifact export."""
    set_random_seed(args.seed)
    assert_locked_dataset()
    metadata = load_dataset_metadata()
    symbol = args.ticker.strip().replace("/", "").upper()
    timeframe = args.timeframe.strip().lower()
    full_frame = load_full(symbol, timeframe)
    prepared = prepare_rolling_data(full_frame)
    evaluation = run_rolling_evaluation(prepared)
    manifest = build_test_manifest(
        evaluation.test.pairs,
        metadata,
        symbol,
        timeframe,
    )
    manifest_hash = calculate_test_manifest_sha256(manifest)
    metrics = evaluate_predictions(
        manifest["actual_close"],
        evaluation.test.predictions,
        manifest["current_close"],
    )
    pre_test_model, state_metadata = prepare_pre_test_artifact(prepared, evaluation)
    run_id = log_training_run(
        metadata,
        symbol,
        timeframe,
        manifest_hash,
        args.seed,
        metrics,
        pre_test_model,
        state_metadata,
        len(evaluation.validation),
        len(evaluation.test),
    )
    _write_and_log_outputs(
        metadata,
        symbol,
        timeframe,
        manifest,
        manifest_hash,
        evaluation.test.predictions,
        metrics,
        run_id,
        args.seed,
    )
    logger.info(
        "ARIMA rolling benchmark completed: run_id=%s manifest=%s samples=%d",
        run_id,
        manifest_hash,
        len(manifest),
    )
    return run_id


def main(argv: list[str] | None = None) -> None:
    """Run the ARIMA command-line entrypoint."""
    args = parse_args(argv)
    setup_logging()
    run_training(args)


if __name__ == "__main__":
    main()
