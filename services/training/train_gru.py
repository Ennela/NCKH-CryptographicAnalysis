"""Train and evaluate the fixed, reproducible GRU next-close benchmark."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import logging
import random
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import MinMaxScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from services.training.models.gru_model import GRUForecaster
from shared.dataset.loader import (
    DEFAULT_CONTRACT_PATH,
    assert_locked_dataset,
    load_full,
)
from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)

MODEL_NAME = "gru"
TARGET_COLUMN = "next_close"
DEFAULT_SEED = 42
STATUS = "preliminary"
RMSE_TOLERANCE = 1e-12
REPO_ROOT = Path(__file__).resolve().parents[2]
PREDICTION_ROOT = REPO_ROOT / "artifacts" / "predictions" / MODEL_NAME
SUMMARY_ROOT = REPO_ROOT / "artifacts" / "metrics" / MODEL_NAME
FEATURE_LIST: tuple[str, ...] = ("close", "moving_average_7")
REPRODUCIBILITY_LIMIT = (
    "Deterministic algorithms are requested, but exact CUDA reproducibility can "
    "still depend on PyTorch, CUDA, cuDNN, driver, and GPU versions."
)

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
class GRUTrainingConfig:
    """Fixed architecture and training configuration for Issue #18."""

    sequence_length: int = 30
    moving_average_window: int = 7
    input_size: int = 2
    hidden_size: int = 64
    num_layers: int = 2
    dropout: float = 0.2
    max_epochs: int = 60
    batch_size: int = 32
    learning_rate: float = 0.0005
    weight_decay: float = 0.0001
    patience: int = 10
    min_delta: float = 0.0


@dataclass(frozen=True)
class DatasetMetadata:
    """Locked dataset identity copied into protocol artifacts."""

    dataset_version: str
    snapshot_name: str


@dataclass(frozen=True)
class SequenceSplit:
    """One chronological sequence split with audit metadata per target."""

    X: np.ndarray
    y_scaled: np.ndarray
    input_ts: np.ndarray
    target_ts: np.ndarray
    current_close: np.ndarray
    actual_close: np.ndarray
    window_start_ts: np.ndarray

    def __len__(self) -> int:
        return len(self.y_scaled)


@dataclass(frozen=True)
class PreparedSequences:
    """Train-fitted scalers and aligned train/validation/test sequences."""

    feature_scaler: MinMaxScaler
    target_scaler: MinMaxScaler
    train: SequenceSplit
    val: SequenceSplit
    test: SequenceSplit


@dataclass(frozen=True)
class TrainingResult:
    """Early-stopping evidence retained for MLflow metadata."""

    best_epoch: int
    best_validation_loss: float
    epochs_ran: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the fixed GRU benchmark CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Ticker in locked dataset")
    parser.add_argument("--timeframe", required=True, help="Timeframe such as 1d")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


def set_random_seed(seed: int) -> None:
    """Seed Python, NumPy, and PyTorch and request deterministic kernels."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    logger.info("Random seed fixed to %d. %s", seed, REPRODUCIBILITY_LIMIT)


def resolve_device() -> torch.device:
    """Use CUDA when available, otherwise CPU."""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_dataset_metadata(
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> DatasetMetadata:
    """Read and validate the locked next-close dataset identity."""
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    if payload.get("target") != {"mode": TARGET_COLUMN, "horizon": 1}:
        raise ValueError("GRU requires target next_close with horizon 1.")
    dataset_version = str(payload.get("dataset_version", ""))
    snapshot_name = str(payload.get("source_snapshot_name", ""))
    if not dataset_version or not snapshot_name:
        raise ValueError("Dataset contract is missing version or snapshot metadata.")
    return DatasetMetadata(dataset_version, snapshot_name)


def _validate_full_frame(frame: pd.DataFrame) -> None:
    """Validate the continuous locked-loader output used for sequences."""
    required = {"ts", "close", TARGET_COLUMN, "split"}
    missing = required.difference(frame.columns)
    if frame.empty or missing:
        raise ValueError(f"Locked GRU frame is empty or missing columns: {missing}.")
    if set(frame["split"].dropna().astype(str)).difference({"train", "val", "test"}):
        raise ValueError("Locked GRU frame contains invalid split labels.")
    if frame["split"].isna().any() or frame["ts"].duplicated().any():
        raise ValueError("Locked GRU frame contains missing splits or duplicate times.")


def _build_continuous_features(
    full_frame: pd.DataFrame,
    config: GRUTrainingConfig,
) -> pd.DataFrame:
    """Calculate causal features before any split-specific sequence selection."""
    _validate_full_frame(full_frame)
    featured = (
        full_frame.sort_values("ts", kind="mergesort").reset_index(drop=True).copy()
    )
    featured["ts"] = pd.to_datetime(featured["ts"], utc=True, errors="raise")
    featured["moving_average_7"] = (
        featured["close"].rolling(window=config.moving_average_window).mean()
    )
    featured["input_ts"] = featured["ts"]
    featured["target_ts"] = featured.groupby("split", sort=False)["ts"].shift(-1)
    featured["current_close"] = featured["close"]
    featured["actual_close"] = featured[TARGET_COLUMN]
    featured = featured.dropna(subset=FEATURE_LIST).reset_index(drop=True)
    feature_values = featured.loc[:, FEATURE_LIST].to_numpy(dtype=np.float64)
    if not np.isfinite(feature_values).all():
        raise ValueError("GRU features contain NaN or Inf.")
    return featured


def _fit_train_scalers(featured: pd.DataFrame) -> tuple[MinMaxScaler, MinMaxScaler]:
    """Fit feature and target scalers once, using training rows only."""
    train_rows = featured["split"].eq("train")
    train_target_rows = train_rows & featured[TARGET_COLUMN].notna()
    feature_scaler = MinMaxScaler()
    target_scaler = MinMaxScaler()
    feature_scaler.fit(featured.loc[train_rows, FEATURE_LIST])
    target_scaler.fit(featured.loc[train_target_rows, [TARGET_COLUMN]])
    return feature_scaler, target_scaler


def _scaled_arrays(
    featured: pd.DataFrame,
    feature_scaler: MinMaxScaler,
    target_scaler: MinMaxScaler,
) -> tuple[np.ndarray, np.ndarray]:
    """Transform the continuous feature series and all finite targets."""
    scaled_features = feature_scaler.transform(featured.loc[:, FEATURE_LIST])
    scaled_targets = np.full(len(featured), np.nan, dtype=np.float64)
    finite_target = featured[TARGET_COLUMN].notna().to_numpy()
    scaled_targets[finite_target] = target_scaler.transform(
        featured.loc[finite_target, [TARGET_COLUMN]]
    ).reshape(-1)
    return scaled_features, scaled_targets


def _empty_records() -> dict[str, list[tuple[Any, ...]]]:
    """Return one mutable sequence-record list per locked split."""
    return {"train": [], "val": [], "test": []}


def _collect_sequence_records(
    featured: pd.DataFrame,
    scaled_features: np.ndarray,
    scaled_targets: np.ndarray,
    sequence_length: int,
) -> dict[str, list[tuple[Any, ...]]]:
    """Collect windows ending at input_ts with the next row as target."""
    records = _empty_records()
    for input_index in range(sequence_length - 1, len(featured)):
        if not np.isfinite(scaled_targets[input_index]):
            continue
        split_name = str(featured.at[input_index, "split"])
        target_index = input_index + 1
        if target_index >= len(featured):
            raise ValueError("A finite GRU target is missing its target row.")
        if str(featured.at[target_index, "split"]) != split_name:
            raise ValueError("GRU target crosses a locked split boundary.")
        if featured.at[input_index, "target_ts"] != featured.at[target_index, "ts"]:
            raise ValueError("GRU target_ts is not the next observed timestamp.")
        window_start = input_index - sequence_length + 1
        records[split_name].append(
            (
                scaled_features[window_start : input_index + 1],
                scaled_targets[input_index],
                featured.at[input_index, "input_ts"],
                featured.at[input_index, "target_ts"],
                featured.at[input_index, "current_close"],
                featured.at[input_index, "actual_close"],
                featured.at[window_start, "ts"],
            )
        )
    return records


def _records_to_split(
    records: list[tuple[Any, ...]],
    sequence_length: int,
) -> SequenceSplit:
    """Convert collected records into typed arrays without changing order."""
    if not records:
        raise ValueError("Every GRU split must contain at least one sequence.")
    X = np.stack([record[0] for record in records]).astype(np.float32)
    if X.shape[1:] != (sequence_length, len(FEATURE_LIST)):
        raise ValueError("GRU sequence tensor has an invalid shape.")
    return SequenceSplit(
        X=X,
        y_scaled=np.asarray([record[1] for record in records], dtype=np.float32),
        input_ts=np.asarray([record[2] for record in records], dtype=object),
        target_ts=np.asarray([record[3] for record in records], dtype=object),
        current_close=np.asarray([record[4] for record in records], dtype=np.float64),
        actual_close=np.asarray([record[5] for record in records], dtype=np.float64),
        window_start_ts=np.asarray([record[6] for record in records], dtype=object),
    )


def build_sequence_dataset(
    full_frame: pd.DataFrame,
    config: GRUTrainingConfig,
) -> PreparedSequences:
    """Fit train-only scalers and create split-safe sequences continuously."""
    featured = _build_continuous_features(full_frame, config)
    feature_scaler, target_scaler = _fit_train_scalers(featured)
    scaled_features, scaled_targets = _scaled_arrays(
        featured, feature_scaler, target_scaler
    )
    records = _collect_sequence_records(
        featured, scaled_features, scaled_targets, config.sequence_length
    )
    return PreparedSequences(
        feature_scaler=feature_scaler,
        target_scaler=target_scaler,
        train=_records_to_split(records["train"], config.sequence_length),
        val=_records_to_split(records["val"], config.sequence_length),
        test=_records_to_split(records["test"], config.sequence_length),
    )


def create_data_loader(
    split: SequenceSplit,
    batch_size: int,
    seed: int,
) -> DataLoader:
    """Create an ordered DataLoader after the global seed has been fixed."""
    generator = torch.Generator()
    generator.manual_seed(seed)
    dataset = TensorDataset(
        torch.from_numpy(split.X),
        torch.from_numpy(split.y_scaled),
    )
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        drop_last=False,
        generator=generator,
    )


def _mean_loader_loss(
    model: GRUForecaster,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    """Calculate mean loss for the validation loader without gradients."""
    model.eval()
    total_loss = 0.0
    sample_count = 0
    with torch.no_grad():
        for batch_X, batch_y in loader:
            batch_X = batch_X.to(device)
            batch_y = batch_y.to(device)
            loss = criterion(model(batch_X), batch_y)
            total_loss += float(loss.item()) * len(batch_X)
            sample_count += len(batch_X)
    if sample_count == 0:
        raise ValueError("Validation loader must not be empty.")
    return total_loss / sample_count


def _train_one_epoch(
    model: GRUForecaster,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> None:
    """Update model weights using training sequences only."""
    model.train()
    for batch_X, batch_y in loader:
        batch_X = batch_X.to(device)
        batch_y = batch_y.to(device)
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(model(batch_X), batch_y)
        loss.backward()
        optimizer.step()


def train_with_early_stopping(
    model: GRUForecaster,
    train_loader: DataLoader,
    validation_loader: DataLoader,
    config: GRUTrainingConfig,
    device: torch.device,
) -> TrainingResult:
    """Select the best epoch using validation loss only."""
    criterion = nn.MSELoss()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    best_loss = float("inf")
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    epochs_without_improvement = 0
    epochs_ran = 0
    for epoch in range(1, config.max_epochs + 1):
        _train_one_epoch(model, train_loader, criterion, optimizer, device)
        validation_loss = _mean_loader_loss(model, validation_loader, criterion, device)
        epochs_ran = epoch
        if validation_loss < best_loss - config.min_delta:
            best_loss = validation_loss
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= config.patience:
                break
    if best_state is None:
        raise RuntimeError("GRU early stopping did not capture a model state.")
    model.load_state_dict(best_state)
    return TrainingResult(best_epoch, float(best_loss), epochs_ran)


def predict_scaled(
    model: GRUForecaster,
    split: SequenceSplit,
    batch_size: int,
    device: torch.device,
) -> np.ndarray:
    """Predict scaled targets in chronological order."""
    model.eval()
    predictions: list[np.ndarray] = []
    tensor = torch.from_numpy(split.X)
    with torch.no_grad():
        for start in range(0, len(tensor), batch_size):
            batch = tensor[start : start + batch_size].to(device)
            predictions.append(model(batch).cpu().numpy())
    result = np.concatenate(predictions).astype(np.float64).reshape(-1)
    if result.shape != (len(split),) or not np.isfinite(result).all():
        raise ValueError("GRU scaled predictions are invalid.")
    return result


def inverse_predictions_once(
    target_scaler: MinMaxScaler,
    predictions_scaled: Any,
) -> np.ndarray:
    """Inverse-transform model predictions exactly once into close-price units."""
    scaled = np.asarray(predictions_scaled, dtype=np.float64)
    if scaled.ndim != 1 or not np.isfinite(scaled).all():
        raise ValueError("Scaled GRU predictions must be one finite vector.")
    predictions = target_scaler.inverse_transform(scaled.reshape(-1, 1)).reshape(-1)
    if not np.isfinite(predictions).all():
        raise ValueError("Inverse-transformed GRU predictions contain NaN or Inf.")
    return predictions


def _metric_vector(name: str, values: Any) -> np.ndarray:
    """Convert a metric input and reject broadcasting-prone shapes."""
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional; got {array.shape}.")
    result = array.reshape(-1)
    if not np.isfinite(result).all():
        raise ValueError(f"{name} contains NaN or Inf.")
    return result


def _error_metrics(
    y_true: np.ndarray, y_pred: np.ndarray
) -> tuple[float, float, float]:
    """Calculate MAE, RMSE, and percentage MAPE."""
    if np.any(y_true == 0.0):
        raise ValueError("MAPE is undefined when actual_close contains zero.")
    errors = y_true - y_pred
    return (
        float(np.mean(np.abs(errors))),
        float(np.sqrt(np.mean(np.square(errors)))),
        float(np.mean(np.abs(errors / y_true)) * 100.0),
    )


def _directional_accuracy(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    current_close: np.ndarray,
) -> float:
    """Calculate direction accuracy relative to the manifest current close."""
    return float(
        np.mean(np.sign(y_pred - current_close) == np.sign(y_true - current_close))
    )


def validate_metric_relationships(metrics: MetricValues) -> None:
    """Reject non-finite metrics and impossible RMSE/MAE relationships."""
    if not all(np.isfinite(value) for value in metrics.values()):
        raise ValueError("GRU metric summary contains NaN or Inf.")
    if metrics["rmse"] + RMSE_TOLERANCE < metrics["mae"]:
        raise ValueError("RMSE cannot be smaller than MAE.")
    if metrics["naive_rmse"] + RMSE_TOLERANCE < metrics["naive_mae"]:
        raise ValueError("Naive RMSE cannot be smaller than Naive MAE.")


def evaluate_predictions(
    y_true: Any,
    y_pred: Any,
    current_close: Any,
) -> MetricValues:
    """Evaluate GRU and locked Naive predictions on identical vectors."""
    actual = _metric_vector("y_true", y_true)
    predicted = _metric_vector("y_pred", y_pred)
    current = _metric_vector("current_close", current_close)
    if actual.shape != predicted.shape or actual.shape != current.shape:
        raise ValueError("GRU metric vectors must have identical shapes.")
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
    test_split: SequenceSplit,
    metadata: DatasetMetadata,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    """Build the protocol manifest from sequence audit metadata."""
    manifest = pd.DataFrame(
        {
            "dataset_version": metadata.dataset_version,
            "snapshot_name": metadata.snapshot_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "split": "test",
            "input_ts": [_utc_timestamp(value) for value in test_split.input_ts],
            "target_ts": [_utc_timestamp(value) for value in test_split.target_ts],
            "current_close": test_split.current_close,
            "actual_close": test_split.actual_close,
        }
    ).sort_values("target_ts", kind="mergesort", ignore_index=True)
    if (
        manifest["input_ts"].duplicated().any()
        or manifest["target_ts"].duplicated().any()
    ):
        raise ValueError("GRU test manifest timestamps must be unique.")
    if not (manifest["input_ts"] < manifest["target_ts"]).all():
        raise ValueError("GRU manifest input_ts must precede target_ts.")
    numeric = manifest[["current_close", "actual_close"]].to_numpy(dtype=np.float64)
    if not np.isfinite(numeric).all():
        raise ValueError("GRU test manifest contains NaN or Inf.")
    return manifest.loc[:, MANIFEST_FIELDNAMES]


def calculate_test_manifest_sha256(manifest: pd.DataFrame) -> str:
    """Hash the canonical eight-column manifest representation."""
    if tuple(manifest.columns) != MANIFEST_FIELDNAMES:
        raise ValueError("GRU test manifest schema or column order is invalid.")
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
    """Join finite GRU predictions to the test manifest in target order."""
    predicted = _metric_vector("predicted_close", predictions)
    if len(predicted) != len(manifest):
        raise ValueError("GRU prediction count must equal manifest target count.")
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
    """Build the one-row protocol metrics summary."""
    validate_metric_relationships(metrics)
    if n_samples <= 0:
        raise ValueError("GRU metrics summary requires at least one sample.")
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
    """Write an exact-schema UTF-8 CSV without overwriting prior runs."""
    if tuple(frame.columns) != fieldnames:
        raise ValueError("GRU CSV schema or column order is invalid.")
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
    model: GRUForecaster,
    config: GRUTrainingConfig,
    result: TrainingResult,
    device: torch.device,
) -> str:
    """Log model, architecture, dataset identity, and final metrics."""
    from services.training.mlflow_utils import log_experiment_run

    params: dict[str, Any] = {
        **asdict(config),
        **model.get_config(),
        "best_epoch": result.best_epoch,
        "best_validation_loss": result.best_validation_loss,
        "epochs_ran": result.epochs_ran,
        "dataset_version": metadata.dataset_version,
        "snapshot_name": metadata.snapshot_name,
        "test_manifest_sha256": manifest_hash,
        "symbol": symbol,
        "timeframe": timeframe,
        "seed": seed,
        "feature_list": ",".join(FEATURE_LIST),
        "target": TARGET_COLUMN,
        "device": str(device),
        "deterministic_algorithms": True,
    }
    return log_experiment_run(
        experiment_name=f"{symbol}_{timeframe}_{MODEL_NAME}",
        run_name=f"{MODEL_NAME}_{symbol}_{timeframe}",
        params=params,
        metrics=metrics,
        model=model,
        model_name_in_registry=f"{symbol}_{timeframe}_{MODEL_NAME}",
    )


def _artifact_paths(symbol: str, timeframe: str, run_id: str) -> tuple[Path, Path]:
    """Return unique prediction and summary paths for one MLflow run."""
    filename = f"{symbol}_{timeframe}_{run_id}.csv"
    return PREDICTION_ROOT / filename, SUMMARY_ROOT / filename


def _log_run_artifacts(
    run_id: str,
    model: GRUForecaster,
    feature_scaler: MinMaxScaler,
    target_scaler: MinMaxScaler,
    config: GRUTrainingConfig,
    prediction_path: Path,
    summary_path: Path,
) -> None:
    """Log state dict, both train-fitted scalers, metadata, and CSV outputs."""
    import mlflow

    with tempfile.TemporaryDirectory(prefix="gru_artifacts_") as temp_dir:
        temp_root = Path(temp_dir)
        state_path = temp_root / "gru_state_dict.pt"
        feature_scaler_path = temp_root / "feature_scaler.joblib"
        target_scaler_path = temp_root / "target_scaler.joblib"
        metadata_path = temp_root / "reproducibility.json"
        torch.save(model.state_dict(), state_path)
        joblib.dump(feature_scaler, feature_scaler_path)
        joblib.dump(target_scaler, target_scaler_path)
        metadata_path.write_text(
            json.dumps(
                {
                    "config": asdict(config),
                    "reproducibility_limit": REPRODUCIBILITY_LIMIT,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with mlflow.start_run(run_id=run_id):
            mlflow.log_artifact(str(state_path), artifact_path="model_state")
            mlflow.log_artifact(str(feature_scaler_path), artifact_path="preprocessing")
            mlflow.log_artifact(str(target_scaler_path), artifact_path="preprocessing")
            mlflow.log_artifact(str(metadata_path), artifact_path="metadata")
            mlflow.log_artifact(str(prediction_path), artifact_path="predictions")
            mlflow.log_artifact(str(summary_path), artifact_path="metrics")


def _write_and_log_outputs(
    args: argparse.Namespace,
    metadata: DatasetMetadata,
    symbol: str,
    timeframe: str,
    sequences: PreparedSequences,
    model: GRUForecaster,
    config: GRUTrainingConfig,
    manifest: pd.DataFrame,
    manifest_hash: str,
    predictions: np.ndarray,
    metrics: MetricValues,
    run_id: str,
) -> None:
    """Write protocol CSVs and attach every required file to the MLflow run."""
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
    _log_run_artifacts(
        run_id,
        model,
        sequences.feature_scaler,
        sequences.target_scaler,
        config,
        prediction_path,
        summary_path,
    )


def _evaluate_and_export(
    args: argparse.Namespace,
    metadata: DatasetMetadata,
    symbol: str,
    timeframe: str,
    sequences: PreparedSequences,
    model: GRUForecaster,
    config: GRUTrainingConfig,
    training_result: TrainingResult,
    device: torch.device,
) -> str:
    """Evaluate the untouched test split and persist protocol artifacts."""
    predictions_scaled = predict_scaled(
        model, sequences.test, config.batch_size, device
    )
    predictions = inverse_predictions_once(sequences.target_scaler, predictions_scaled)
    metrics = evaluate_predictions(
        sequences.test.actual_close,
        predictions,
        sequences.test.current_close,
    )
    manifest = build_test_manifest(sequences.test, metadata, symbol, timeframe)
    manifest_hash = calculate_test_manifest_sha256(manifest)
    run_id = log_training_run(
        metadata,
        symbol,
        timeframe,
        manifest_hash,
        args.seed,
        metrics,
        model,
        config,
        training_result,
        device,
    )
    _write_and_log_outputs(
        args,
        metadata,
        symbol,
        timeframe,
        sequences,
        model,
        config,
        manifest,
        manifest_hash,
        predictions,
        metrics,
        run_id,
    )
    return run_id


def run_training(args: argparse.Namespace) -> str:
    """Execute locked-data sequence creation, training, evaluation, and export."""
    set_random_seed(args.seed)
    config = GRUTrainingConfig()
    assert_locked_dataset()
    metadata = load_dataset_metadata()
    symbol = args.ticker.strip().replace("/", "").upper()
    timeframe = args.timeframe.strip().lower()
    full_frame = load_full(symbol, timeframe)
    sequences = build_sequence_dataset(full_frame, config)
    device = resolve_device()

    train_loader = create_data_loader(sequences.train, config.batch_size, args.seed)
    validation_loader = create_data_loader(sequences.val, config.batch_size, args.seed)
    model = GRUForecaster(
        input_size=config.input_size,
        hidden_size=config.hidden_size,
        num_layers=config.num_layers,
        dropout=config.dropout,
    ).to(device)
    training_result = train_with_early_stopping(
        model, train_loader, validation_loader, config, device
    )
    run_id = _evaluate_and_export(
        args,
        metadata,
        symbol,
        timeframe,
        sequences,
        model,
        config,
        training_result,
        device,
    )
    logger.info("GRU training completed. MLflow run ID: %s", run_id)
    return str(run_id)


def main(argv: list[str] | None = None) -> None:
    """Run the GRU command-line entrypoint."""
    args = parse_args(argv)
    setup_logging()
    run_training(args)


if __name__ == "__main__":
    main()
