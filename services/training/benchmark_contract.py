"""Shared, machine-readable contract for the ACB 1d four-model benchmark."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from shared.dataset.loader import (
    DEFAULT_CONTRACT_PATH,
    assert_locked_dataset,
    load_full,
)

MODEL_NAMES: tuple[str, ...] = (
    "xgboost",
    "random_forest",
    "gru",
    "arima",
)
BENCHMARK_SYMBOL = "ACB"
BENCHMARK_TIMEFRAME = "1d"
BENCHMARK_SPLIT = "test"
BENCHMARK_SEED = 42
EXPECTED_PREDICTION_ROWS = 78
EXPECTED_TEST_MANIFEST_SHA256 = (
    "62d82e13b48f337623235e20c2412d435395fef46fea5a24776ea895d1c8b828"
)
METRIC_TOLERANCE = 1e-12

PREDICTION_COLUMNS: tuple[str, ...] = (
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
SUMMARY_COLUMNS: tuple[str, ...] = (
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
OVERVIEW_COLUMNS: tuple[str, ...] = (
    "rank",
    "dataset_version",
    "snapshot_name",
    "test_manifest_sha256",
    "symbol",
    "timeframe",
    "model",
    "n_samples",
    "mae",
    "rmse",
    "mape_pct",
    "directional_accuracy",
    "naive_mae",
    "naive_rmse",
    "naive_mape_pct",
    "improvement_vs_naive_rmse_pct",
    "run_id",
    "seed",
    "status",
)
MANIFEST_COLUMNS: tuple[str, ...] = (
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
MANIFEST_HASH_COLUMNS: tuple[str, ...] = (
    "dataset_version",
    "snapshot_name",
    "symbol",
    "timeframe",
    "input_ts",
    "target_ts",
    "current_close",
    "actual_close",
)
METRIC_NAMES: tuple[str, ...] = (
    "mae",
    "rmse",
    "mape_pct",
    "directional_accuracy",
    "naive_mae",
    "naive_rmse",
    "naive_mape_pct",
    "naive_directional_accuracy",
    "improvement_vs_naive_rmse_pct",
)
REQUIRED_RUN_PARAMS: tuple[str, ...] = (
    "dataset_version",
    "snapshot_name",
    "test_manifest_sha256",
    "symbol",
    "timeframe",
    "model",
    "target",
    "horizon",
    "seed",
)
MODEL_REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "xgboost": (
        "n_estimators",
        "max_depth",
        "learning_rate",
        "subsample",
        "colsample_bytree",
        "random_state",
        "feature_list",
    ),
    "random_forest": (
        "n_estimators",
        "max_depth",
        "min_samples_split",
        "min_samples_leaf",
        "random_state",
        "feature_list",
    ),
    "gru": (
        "sequence_length",
        "hidden_size",
        "num_layers",
        "dropout",
        "batch_size",
        "learning_rate",
        "patience",
        "max_epochs",
        "input_size",
        "feature_list",
    ),
    "arima": (
        "order_p",
        "order_d",
        "order_q",
        "state_role",
        "observation_count",
        "contains_test_history",
    ),
}
MINIMUM_SOURCE_COMMITS: dict[str, str] = {
    "xgboost": "de996d7778f90b119b2497bd66b5f1f71f6186b0",
    "random_forest": "0989aee0d668bf7876decef033e62df7415ec295",
    "gru": "8a0d2dd3ec7a749aec2fedd8516e835390a9243d",
    "arima": "ab1cf9af355211192c923c55aa042ff0413fdf6a",
}
SOURCE_SUMMARY_STATUSES: frozenset[str] = frozenset({"preliminary", "valid", "invalid"})
ELIGIBLE_SOURCE_SUMMARY_STATUSES: frozenset[str] = frozenset({"preliminary", "valid"})


@dataclass(frozen=True)
class LockedBenchmarkContract:
    """Values loaded from the canonical dataset config plus Issue #20 pilot scope."""

    dataset_version: str
    snapshot_name: str
    target: str
    horizon: int
    symbol: str = BENCHMARK_SYMBOL
    timeframe: str = BENCHMARK_TIMEFRAME
    split: str = BENCHMARK_SPLIT
    seed: int = BENCHMARK_SEED
    prediction_rows: int = EXPECTED_PREDICTION_ROWS

    def as_dict(self) -> dict[str, str | int]:
        """Return a JSON-safe ordered representation of the locked contract."""
        return {
            "dataset_version": self.dataset_version,
            "snapshot_name": self.snapshot_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "target": self.target,
            "horizon": self.horizon,
            "split": self.split,
            "seed": self.seed,
            "prediction_rows": self.prediction_rows,
        }


def load_benchmark_contract(
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> LockedBenchmarkContract:
    """Read dataset identity and target semantics from the canonical JSON contract."""
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    target = payload.get("target")
    if not isinstance(target, dict):
        raise ValueError("Dataset contract is missing the target configuration.")
    return LockedBenchmarkContract(
        dataset_version=str(payload["dataset_version"]),
        snapshot_name=str(payload["source_snapshot_name"]),
        target=str(target["mode"]),
        horizon=int(target["horizon"]),
    )


def _timestamp_text(value: Any) -> str:
    """Serialize one timestamp to the protocol's UTC second-resolution form."""
    timestamp = pd.to_datetime(value, utc=True, errors="raise")
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _float_text(value: Any) -> str:
    """Serialize one finite float with the protocol's round-trip representation."""
    number = float(value)
    if not np.isfinite(number):
        raise ValueError("Canonical manifest values must be finite.")
    rendered = format(number, ".17g")
    return "0" if rendered == "-0" else rendered


def calculate_manifest_sha256(manifest: pd.DataFrame) -> str:
    """Hash the canonical manifest independently of CSV platform defaults."""
    if not set(MANIFEST_HASH_COLUMNS).issubset(manifest.columns):
        raise ValueError("Manifest is missing canonical hash columns.")
    canonical = manifest.loc[:, MANIFEST_HASH_COLUMNS].copy()
    canonical = canonical.sort_values("target_ts", kind="mergesort")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(MANIFEST_HASH_COLUMNS)
    for row in canonical.itertuples(index=False, name=None):
        values = list(row)
        values[4] = _timestamp_text(values[4])
        values[5] = _timestamp_text(values[5])
        values[6] = _float_text(values[6])
        values[7] = _float_text(values[7])
        writer.writerow(values)
    return hashlib.sha256(buffer.getvalue().encode("utf-8")).hexdigest()


def build_locked_test_manifest(
    contract: LockedBenchmarkContract,
) -> tuple[pd.DataFrame, str]:
    """Build the canonical ACB test manifest directly from the locked loader."""
    assert_locked_dataset()
    frame = load_full(contract.symbol, contract.timeframe)
    test = frame.loc[
        frame["split"].eq(contract.split) & frame["next_close"].notna()
    ].copy()
    target_indices = test.index + contract.horizon
    target_timestamps = frame.loc[target_indices, "ts"].to_numpy()
    manifest = pd.DataFrame(
        {
            "dataset_version": contract.dataset_version,
            "snapshot_name": contract.snapshot_name,
            "symbol": contract.symbol,
            "timeframe": contract.timeframe,
            "split": contract.split,
            "input_ts": test["ts"].map(_timestamp_text).to_numpy(),
            "target_ts": [_timestamp_text(value) for value in target_timestamps],
            "current_close": test["close"].to_numpy(dtype=np.float64),
            "actual_close": test["next_close"].to_numpy(dtype=np.float64),
        },
        columns=MANIFEST_COLUMNS,
    )
    if len(manifest) != contract.prediction_rows:
        raise ValueError(
            f"Locked manifest has {len(manifest)} rows; "
            f"expected {contract.prediction_rows}."
        )
    manifest_hash = calculate_manifest_sha256(manifest)
    if manifest_hash != EXPECTED_TEST_MANIFEST_SHA256:
        raise ValueError(
            "Locked test manifest hash mismatch: "
            f"expected {EXPECTED_TEST_MANIFEST_SHA256}, got {manifest_hash}."
        )
    return manifest, manifest_hash
