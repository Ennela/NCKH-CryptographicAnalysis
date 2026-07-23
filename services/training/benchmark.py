"""Validate and rank four explicit MLflow runs for the locked ACB 1d benchmark."""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import mlflow
import numpy as np
import pandas as pd

from services.training.benchmark_contract import (
    ELIGIBLE_SOURCE_SUMMARY_STATUSES,
    METRIC_NAMES,
    METRIC_TOLERANCE,
    MINIMUM_SOURCE_COMMITS,
    MODEL_NAMES,
    MODEL_REQUIRED_PARAMS,
    OVERVIEW_COLUMNS,
    PREDICTION_COLUMNS,
    REQUIRED_RUN_PARAMS,
    SOURCE_SUMMARY_STATUSES,
    SUMMARY_COLUMNS,
    LockedBenchmarkContract,
    build_locked_test_manifest,
    load_benchmark_contract,
)
from services.training.mlflow_utils import init_mlflow
from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
BENCHMARK_EXPERIMENT = "ACB_1d_four_model_benchmark"
OUTPUT_FILENAMES: tuple[str, ...] = (
    "benchmark_overview.csv",
    "benchmark_report.md",
    "benchmark_audit.json",
)
REQUIRED_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "xgboost": (
        "model/MLmodel",
        "preprocessing/standard_scaler.joblib",
    ),
    "random_forest": ("model/MLmodel",),
    "gru": (
        "model/MLmodel",
        "model_state/gru_state_dict.pt",
        "preprocessing/feature_scaler.joblib",
        "preprocessing/target_scaler.joblib",
        "metadata/reproducibility.json",
    ),
    "arima": (
        "model/MLmodel",
        "metadata/pre_test_model.json",
    ),
}


class BenchmarkValidationError(RuntimeError):
    """Raised when one or more benchmark quality gates fail."""

    def __init__(self, message: str, audit: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.audit = {} if audit is None else audit


@dataclass(frozen=True)
class CheckResult:
    """One machine-readable expected-versus-actual validation result."""

    name: str
    status: str
    expected: Any
    actual: Any
    failure_reason: str | None = None


@dataclass
class ModelEvaluation:
    """Validated state for one explicitly selected MLflow model run."""

    model: str
    run_id: str
    status: str = "invalid"
    source_commit: str | None = None
    source_summary_status: str | None = None
    params: dict[str, str] = field(default_factory=dict)
    mlflow_metrics: dict[str, float] = field(default_factory=dict)
    recomputed_metrics: dict[str, float] = field(default_factory=dict)
    artifact_paths: list[str] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    predictions: pd.DataFrame | None = None

    def record(
        self,
        name: str,
        passed: bool,
        expected: Any,
        actual: Any,
        failure_reason: str,
    ) -> None:
        """Record one check and retain an explicit reason when it fails."""
        result = CheckResult(
            name=name,
            status="pass" if passed else "fail",
            expected=expected,
            actual=actual,
            failure_reason=None if passed else failure_reason,
        )
        self.checks.append(result)
        if not passed and failure_reason not in self.failure_reasons:
            self.failure_reasons.append(failure_reason)

    def as_audit_dict(self) -> dict[str, Any]:
        """Return the JSON-safe portion of this evaluation."""
        return {
            "model": self.model,
            "run_id": self.run_id,
            "source_commit": self.source_commit,
            "source_summary_status": self.source_summary_status,
            "status": self.status,
            "failure_reason": self.failure_reasons,
            "params": self.params,
            "mlflow_metrics": self.mlflow_metrics,
            "recomputed_metrics": self.recomputed_metrics,
            "artifacts": self.artifact_paths,
            "checks": [asdict(check) for check in self.checks],
        }


@dataclass(frozen=True)
class BenchmarkResult:
    """Successful benchmark outputs and MLflow evidence identity."""

    output_dir: Path
    evaluator_run_id: str
    ranking: tuple[dict[str, Any], ...]
    generated_at: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse four explicit run IDs and the generated-artifact output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    for model in MODEL_NAMES:
        option = f"--{model.replace('_', '-')}-run-id"
        parser.add_argument(option, required=True, dest=f"{model}_run_id")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def explicit_run_ids(args: argparse.Namespace) -> dict[str, str]:
    """Build and validate the fixed model-to-run mapping from CLI arguments."""
    mapping = {
        model: str(getattr(args, f"{model}_run_id")).strip() for model in MODEL_NAMES
    }
    if any(not run_id for run_id in mapping.values()):
        raise BenchmarkValidationError("All four explicit run IDs are required.")
    if len(set(mapping.values())) != len(MODEL_NAMES):
        raise BenchmarkValidationError("Each model must use a distinct MLflow run ID.")
    return mapping


def _run_git(
    arguments: list[str], repo_root: Path = REPO_ROOT
) -> subprocess.CompletedProcess[str]:
    """Run one non-shell Git command and preserve its exit code for audit."""
    return subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def current_source_commit(repo_root: Path = REPO_ROOT) -> str:
    """Return the committed evaluator source revision."""
    result = _run_git(["rev-parse", "HEAD"], repo_root)
    commit = result.stdout.strip()
    if result.returncode != 0 or not COMMIT_PATTERN.fullmatch(commit):
        raise BenchmarkValidationError("Cannot resolve evaluator source commit.")
    return commit


def require_clean_worktree(repo_root: Path = REPO_ROOT) -> None:
    """Reject official evaluation from a dirty worktree."""
    result = _run_git(["status", "--short"], repo_root)
    if result.returncode != 0 or result.stdout.strip():
        raise BenchmarkValidationError(
            "Official benchmark requires a clean committed worktree."
        )


def git_is_ancestor(
    ancestor: str,
    descendant: str,
    repo_root: Path = REPO_ROOT,
) -> bool:
    """Return whether one validated commit is an ancestor of a Git ref."""
    if not COMMIT_PATTERN.fullmatch(ancestor):
        return False
    result = _run_git(["merge-base", "--is-ancestor", ancestor, descendant], repo_root)
    return result.returncode == 0


def _list_artifacts_recursive(
    client: Any,
    run_id: str,
    path: str = "",
) -> list[str]:
    """Return every MLflow artifact path in deterministic order."""
    paths: list[str] = []
    for artifact in client.list_artifacts(run_id, path):
        if artifact.is_dir:
            paths.extend(_list_artifacts_recursive(client, run_id, artifact.path))
        else:
            paths.append(str(artifact.path))
    return sorted(paths)


def _single_csv_artifact(paths: list[str], directory: str) -> str:
    """Resolve exactly one CSV under a required MLflow artifact directory."""
    matches = [
        path
        for path in paths
        if path.startswith(f"{directory}/") and path.lower().endswith(".csv")
    ]
    if len(matches) != 1:
        raise BenchmarkValidationError(
            f"Expected one {directory} CSV artifact, found {matches}."
        )
    return matches[0]


def _download_artifact(
    client: Any,
    run_id: str,
    artifact_path: str,
    destination: Path,
) -> Path:
    """Download one run artifact to an evaluator-owned temporary directory."""
    downloaded = client.download_artifacts(
        run_id,
        artifact_path,
        dst_path=str(destination),
    )
    path = Path(downloaded)
    if not path.is_file():
        raise BenchmarkValidationError(
            f"Downloaded artifact is not a file: {artifact_path}"
        )
    return path


def _exact_string_column(frame: pd.DataFrame, column: str, expected: str) -> bool:
    """Return whether a required identity column contains one exact value."""
    return bool(frame[column].astype(str).eq(expected).all())


def _finite_numeric(frame: pd.DataFrame, columns: tuple[str, ...]) -> bool:
    """Return whether exact numeric columns parse and contain only finite values."""
    try:
        values = frame.loc[:, columns].apply(pd.to_numeric, errors="raise")
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(values.to_numpy(dtype=np.float64)).all())


def recompute_metrics(predictions: pd.DataFrame) -> dict[str, float]:
    """Recompute model and Naive metrics from exact prediction-level vectors."""
    actual = predictions["actual_close"].to_numpy(dtype=np.float64)
    predicted = predictions["predicted_close"].to_numpy(dtype=np.float64)
    current = predictions["current_close"].to_numpy(dtype=np.float64)
    if (
        actual.ndim != 1
        or predicted.shape != actual.shape
        or current.shape != actual.shape
    ):
        raise BenchmarkValidationError("Metric vectors must be aligned 1D arrays.")
    if not np.isfinite(np.concatenate((actual, predicted, current))).all():
        raise BenchmarkValidationError("Metric vectors contain NaN or infinity.")
    if np.any(actual == 0.0):
        raise BenchmarkValidationError("MAPE is undefined for zero actual values.")
    errors = actual - predicted
    naive_errors = actual - current
    naive_rmse = float(np.sqrt(np.mean(naive_errors**2)))
    if naive_rmse == 0.0:
        raise BenchmarkValidationError("Naive RMSE must be nonzero.")
    metrics = {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "mape_pct": float(np.mean(np.abs(errors / actual)) * 100.0),
        "directional_accuracy": float(
            np.mean(np.sign(actual - current) == np.sign(predicted - current))
        ),
        "naive_mae": float(np.mean(np.abs(naive_errors))),
        "naive_rmse": naive_rmse,
        "naive_mape_pct": float(np.mean(np.abs(naive_errors / actual)) * 100.0),
        "naive_directional_accuracy": float(
            np.mean(np.sign(current - current) == np.sign(actual - current))
        ),
    }
    metrics["improvement_vs_naive_rmse_pct"] = (
        (naive_rmse - metrics["rmse"]) / naive_rmse * 100.0
    )
    return metrics


def _metrics_match(
    expected: dict[str, float],
    actual: dict[str, float],
) -> bool:
    """Compare exact metric keys with the protocol's absolute tolerance."""
    return all(
        name in actual
        and np.isclose(
            actual[name],
            expected[name],
            rtol=0.0,
            atol=METRIC_TOLERANCE,
        )
        for name in METRIC_NAMES
    )


def validate_prediction_frame(
    evaluation: ModelEvaluation,
    predictions: pd.DataFrame,
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
    manifest_hash: str,
) -> None:
    """Validate exact schema, identities, ordering, finiteness, and locked rows."""
    evaluation.record(
        "prediction_schema",
        tuple(predictions.columns) == PREDICTION_COLUMNS,
        list(PREDICTION_COLUMNS),
        list(predictions.columns),
        "Prediction CSV schema or column order is invalid.",
    )
    if tuple(predictions.columns) != PREDICTION_COLUMNS:
        return
    evaluation.record(
        "prediction_rows",
        len(predictions) == contract.prediction_rows,
        contract.prediction_rows,
        len(predictions),
        "Prediction row count does not match the locked manifest.",
    )
    identities = {
        "dataset_version": contract.dataset_version,
        "snapshot_name": contract.snapshot_name,
        "test_manifest_sha256": manifest_hash,
        "symbol": contract.symbol,
        "timeframe": contract.timeframe,
        "model": evaluation.model,
        "split": contract.split,
        "run_id": evaluation.run_id,
    }
    for column, expected in identities.items():
        evaluation.record(
            f"prediction_{column}",
            _exact_string_column(predictions, column, expected),
            expected,
            sorted(predictions[column].astype(str).unique().tolist()),
            f"Prediction column {column} is inconsistent.",
        )
    seed = pd.to_numeric(predictions["seed"], errors="coerce")
    evaluation.record(
        "prediction_seed",
        bool(seed.eq(contract.seed).all()),
        contract.seed,
        sorted(seed.dropna().unique().tolist()),
        "Prediction seed does not match the benchmark contract.",
    )
    _validate_prediction_rows(evaluation, predictions, manifest)


def _validate_prediction_rows(
    evaluation: ModelEvaluation,
    predictions: pd.DataFrame,
    manifest: pd.DataFrame,
) -> None:
    """Validate chronological and numeric prediction content against locked rows."""
    input_ts = pd.to_datetime(predictions["input_ts"], utc=True, errors="coerce")
    target_ts = pd.to_datetime(predictions["target_ts"], utc=True, errors="coerce")
    chronological = bool(
        input_ts.notna().all()
        and target_ts.notna().all()
        and target_ts.is_monotonic_increasing
        and not target_ts.duplicated().any()
        and (input_ts < target_ts).all()
    )
    evaluation.record(
        "prediction_chronology",
        chronological,
        "strictly ordered unique horizon-one targets",
        "valid" if chronological else "invalid",
        "Prediction timestamps are missing, duplicated, unordered, or misaligned.",
    )
    numeric_columns = ("current_close", "actual_close", "predicted_close")
    finite = _finite_numeric(predictions, numeric_columns)
    evaluation.record(
        "prediction_finite",
        finite,
        "all finite",
        "all finite" if finite else "invalid numeric values",
        "Prediction values contain missing, nonnumeric, NaN, or infinite values.",
    )
    row_columns = ("input_ts", "target_ts", "current_close", "actual_close")
    matches = finite and _manifest_rows_match(predictions, manifest, row_columns)
    evaluation.record(
        "locked_manifest_rows",
        matches,
        "exact locked-loader row identity",
        "match" if matches else "mismatch",
        "Prediction rows do not match the locked canonical manifest.",
    )


def _manifest_rows_match(
    predictions: pd.DataFrame,
    manifest: pd.DataFrame,
    columns: tuple[str, ...],
) -> bool:
    """Compare timestamp and price identity without coercing or dropping rows."""
    if len(predictions) != len(manifest):
        return False
    for column in columns[:2]:
        left = pd.to_datetime(predictions[column], utc=True, errors="coerce")
        right = pd.to_datetime(manifest[column], utc=True, errors="coerce")
        if not np.array_equal(left.to_numpy(), right.to_numpy()):
            return False
    for column in columns[2:]:
        left = pd.to_numeric(predictions[column], errors="coerce").to_numpy()
        right = pd.to_numeric(manifest[column], errors="coerce").to_numpy()
        if not np.array_equal(left, right):
            return False
    return True


def validate_summary_frame(
    evaluation: ModelEvaluation,
    summary: pd.DataFrame,
    contract: LockedBenchmarkContract,
    manifest_hash: str,
) -> None:
    """Validate the immutable source summary against recomputed and MLflow metrics."""
    evaluation.record(
        "summary_schema",
        tuple(summary.columns) == SUMMARY_COLUMNS,
        list(SUMMARY_COLUMNS),
        list(summary.columns),
        "Summary CSV schema or column order is invalid.",
    )
    if tuple(summary.columns) != SUMMARY_COLUMNS or len(summary) != 1:
        evaluation.record(
            "summary_rows",
            False,
            1,
            len(summary),
            "Summary CSV must contain exactly one row.",
        )
        return
    row = summary.iloc[0]
    evaluation.source_summary_status = str(row["status"])
    expected_identity: dict[str, Any] = {
        "dataset_version": contract.dataset_version,
        "snapshot_name": contract.snapshot_name,
        "test_manifest_sha256": manifest_hash,
        "symbol": contract.symbol,
        "timeframe": contract.timeframe,
        "model": evaluation.model,
        "split": contract.split,
        "n_samples": contract.prediction_rows,
        "run_id": evaluation.run_id,
        "seed": contract.seed,
    }
    for name, expected in expected_identity.items():
        actual = row[name]
        passed = str(actual) == str(expected)
        if isinstance(expected, int):
            passed = bool(
                pd.to_numeric(pd.Series([actual]), errors="coerce").eq(expected).all()
            )
        evaluation.record(
            f"summary_{name}",
            passed,
            expected,
            actual,
            f"Summary field {name} does not match the benchmark run.",
        )
    evaluation.record(
        "summary_status",
        evaluation.source_summary_status in SOURCE_SUMMARY_STATUSES,
        sorted(SOURCE_SUMMARY_STATUSES),
        evaluation.source_summary_status,
        "Source summary status is outside the protocol.",
    )
    evaluation.record(
        "summary_eligibility",
        evaluation.source_summary_status in ELIGIBLE_SOURCE_SUMMARY_STATUSES,
        sorted(ELIGIBLE_SOURCE_SUMMARY_STATUSES),
        evaluation.source_summary_status,
        "Source summary explicitly marks the run invalid.",
    )
    summary_metrics = {name: float(row[name]) for name in METRIC_NAMES}
    evaluation.record(
        "summary_metrics",
        _metrics_match(evaluation.recomputed_metrics, summary_metrics),
        evaluation.recomputed_metrics,
        summary_metrics,
        "Summary metrics do not match independent recomputation.",
    )
    evaluation.record(
        "mlflow_metrics",
        _metrics_match(evaluation.recomputed_metrics, evaluation.mlflow_metrics),
        evaluation.recomputed_metrics,
        evaluation.mlflow_metrics,
        "MLflow metrics do not match independent recomputation.",
    )


def validate_run_metadata(
    evaluation: ModelEvaluation,
    run: Any,
    contract: LockedBenchmarkContract,
    manifest_hash: str,
    evaluator_commit: str,
    repo_root: Path = REPO_ROOT,
) -> None:
    """Validate run status, provenance, required params, and required metrics."""
    evaluation.params = dict(run.data.params)
    evaluation.mlflow_metrics = {
        name: float(value) for name, value in run.data.metrics.items()
    }
    evaluation.source_commit = run.data.tags.get("mlflow.source.git.commit")
    evaluation.record(
        "run_status",
        str(run.info.status) == "FINISHED",
        "FINISHED",
        str(run.info.status),
        "MLflow run is not FINISHED.",
    )
    lifecycle_tags = {
        name: str(run.data.tags[name]).strip().lower()
        for name in ("candidate_status", "lifecycle_status")
        if name in run.data.tags
    }
    disallowed_lifecycle = {
        name: value
        for name, value in lifecycle_tags.items()
        if value in {"exploratory", "superseded", "excluded", "invalid"}
    }
    evaluation.record(
        "run_lifecycle",
        not disallowed_lifecycle,
        "not explicitly exploratory, superseded, excluded, or invalid",
        lifecycle_tags,
        "MLflow tags explicitly exclude this run from official evaluation.",
    )
    _validate_source_provenance(evaluation, evaluator_commit, repo_root)
    required = (*REQUIRED_RUN_PARAMS, *MODEL_REQUIRED_PARAMS[evaluation.model])
    missing = [name for name in required if name not in evaluation.params]
    evaluation.record(
        "required_params",
        not missing,
        list(required),
        {"missing": missing},
        "MLflow run is missing required parameters.",
    )
    missing_metrics = [
        name for name in METRIC_NAMES if name not in evaluation.mlflow_metrics
    ]
    evaluation.record(
        "required_metrics",
        not missing_metrics,
        list(METRIC_NAMES),
        {"missing": missing_metrics},
        "MLflow run is missing required metrics.",
    )
    if not missing:
        _validate_contract_params(evaluation, contract, manifest_hash)


def _validate_source_provenance(
    evaluation: ModelEvaluation,
    evaluator_commit: str,
    repo_root: Path,
) -> None:
    """Require merged provenance or the exact clean pre-merge evaluator commit."""
    source = evaluation.source_commit or ""
    source_format = bool(COMMIT_PATTERN.fullmatch(source))
    in_develop = source_format and git_is_ancestor(source, "origin/develop", repo_root)
    current_committed_source = source == evaluator_commit
    evaluation.record(
        "source_commit",
        source_format and (in_develop or current_committed_source),
        "ancestor of origin/develop or exact committed evaluator HEAD",
        {
            "commit": source or None,
            "in_origin_develop": in_develop,
            "matches_evaluator_commit": current_committed_source,
        },
        "Source commit is missing or is not accepted committed provenance.",
    )
    minimum = MINIMUM_SOURCE_COMMITS[evaluation.model]
    evaluation.record(
        "minimum_implementation_commit",
        source_format and git_is_ancestor(minimum, source, repo_root),
        minimum,
        source or None,
        "Source commit predates the model's required technical fix.",
    )


def _validate_contract_params(
    evaluation: ModelEvaluation,
    contract: LockedBenchmarkContract,
    manifest_hash: str,
) -> None:
    """Compare required MLflow identity params to the locked contract."""
    expected = {
        "dataset_version": contract.dataset_version,
        "snapshot_name": contract.snapshot_name,
        "test_manifest_sha256": manifest_hash,
        "symbol": contract.symbol,
        "timeframe": contract.timeframe,
        "model": evaluation.model,
        "target": contract.target,
        "horizon": str(contract.horizon),
        "seed": str(contract.seed),
    }
    actual = {name: evaluation.params.get(name) for name in expected}
    passed = all(str(actual[name]) == str(value) for name, value in expected.items())
    evaluation.record(
        "contract_params",
        passed,
        expected,
        actual,
        "MLflow params do not match the locked benchmark contract.",
    )
    if evaluation.model == "arima":
        order = tuple(
            int(evaluation.params[name]) for name in ("order_p", "order_d", "order_q")
        )
        evaluation.record(
            "arima_order",
            order == (1, 1, 1),
            [1, 1, 1],
            list(order),
            "ARIMA order does not match the official pilot.",
        )


def validate_required_artifacts(
    evaluation: ModelEvaluation,
) -> tuple[str | None, str | None]:
    """Validate exact required artifacts and resolve prediction/summary CSV paths."""
    missing = [
        path
        for path in REQUIRED_ARTIFACTS[evaluation.model]
        if path not in evaluation.artifact_paths
    ]
    evaluation.record(
        "required_artifacts",
        not missing,
        list(REQUIRED_ARTIFACTS[evaluation.model]),
        {"missing": missing},
        "MLflow run is missing required model-specific artifacts.",
    )
    try:
        prediction_path = _single_csv_artifact(evaluation.artifact_paths, "predictions")
        summary_path = _single_csv_artifact(evaluation.artifact_paths, "metrics")
    except BenchmarkValidationError as exc:
        evaluation.record(
            "csv_artifacts",
            False,
            "one prediction CSV and one summary CSV",
            evaluation.artifact_paths,
            str(exc),
        )
        return None, None
    evaluation.record(
        "csv_artifacts",
        True,
        "one prediction CSV and one summary CSV",
        [prediction_path, summary_path],
        "",
    )
    return prediction_path, summary_path


def validate_model_artifact(
    evaluation: ModelEvaluation,
    client: Any,
    download_root: Path,
) -> None:
    """Reload the model-specific serving state and run one finite smoke prediction."""
    try:
        if evaluation.model == "xgboost":
            _validate_xgboost_artifact(evaluation, client, download_root)
        elif evaluation.model == "random_forest":
            _validate_random_forest_artifact(evaluation)
        elif evaluation.model == "gru":
            _validate_gru_artifact(evaluation, client, download_root)
        elif evaluation.model == "arima":
            _validate_arima_artifact(evaluation, client, download_root)
    except Exception as exc:
        evaluation.record(
            "model_artifact_reload",
            False,
            "reloadable artifact with finite prediction",
            type(exc).__name__,
            f"Model artifact validation failed: {exc}",
        )


def _feature_names(evaluation: ModelEvaluation) -> list[str]:
    """Return nonempty ordered feature metadata from MLflow params."""
    features = [
        name.strip()
        for name in evaluation.params.get("feature_list", "").split(",")
        if name.strip()
    ]
    if not features:
        raise BenchmarkValidationError("Feature ordering metadata is empty.")
    return features


def _validate_xgboost_artifact(
    evaluation: ModelEvaluation,
    client: Any,
    download_root: Path,
) -> None:
    """Reload XGBoost, its scaler, and exact feature ordering."""
    import mlflow.xgboost

    model = mlflow.xgboost.load_model(f"runs:/{evaluation.run_id}/model")
    scaler_path = _download_artifact(
        client,
        evaluation.run_id,
        "preprocessing/standard_scaler.joblib",
        download_root,
    )
    scaler = joblib.load(scaler_path)
    features = _feature_names(evaluation)
    scaled = scaler.transform(np.zeros((1, len(features)), dtype=np.float64))
    sample = pd.DataFrame(scaled, columns=features)
    prediction = np.asarray(model.predict(sample), dtype=np.float64)
    booster_names = list(model.get_booster().feature_names or [])
    passed = bool(
        prediction.shape == (1,)
        and np.isfinite(prediction).all()
        and int(model.n_features_in_) == len(features)
        and int(scaler.n_features_in_) == len(features)
        and booster_names == features
    )
    evaluation.record(
        "model_artifact_reload",
        passed,
        {"features": features, "finite_prediction": True},
        {
            "features": booster_names,
            "finite_prediction": bool(np.isfinite(prediction).all()),
        },
        "XGBoost model, scaler, or feature ordering is inconsistent.",
    )


def _validate_random_forest_artifact(evaluation: ModelEvaluation) -> None:
    """Reload Random Forest and verify feature-aware finite prediction."""
    import mlflow.sklearn

    model = mlflow.sklearn.load_model(f"runs:/{evaluation.run_id}/model")
    features = _feature_names(evaluation)
    sample = pd.DataFrame(np.zeros((1, len(features))), columns=features)
    prediction = np.asarray(model.predict(sample), dtype=np.float64)
    artifact_features = list(getattr(model, "feature_names_in_", []))
    passed = bool(
        prediction.shape == (1,)
        and np.isfinite(prediction).all()
        and int(model.n_features_in_) == len(features)
        and artifact_features == features
    )
    evaluation.record(
        "model_artifact_reload",
        passed,
        {"features": features, "finite_prediction": True},
        {
            "features": artifact_features,
            "finite_prediction": bool(np.isfinite(prediction).all()),
        },
        "Random Forest model or feature ordering is inconsistent.",
    )


def _validate_gru_artifact(
    evaluation: ModelEvaluation,
    client: Any,
    download_root: Path,
) -> None:
    """Reload GRU, strict state dict, both scalers, and architecture metadata."""
    import mlflow.pytorch
    import torch

    model = mlflow.pytorch.load_model(
        f"runs:/{evaluation.run_id}/model",
        map_location="cpu",
    )
    state_path = _download_artifact(
        client, evaluation.run_id, "model_state/gru_state_dict.pt", download_root
    )
    feature_scaler = joblib.load(
        _download_artifact(
            client,
            evaluation.run_id,
            "preprocessing/feature_scaler.joblib",
            download_root,
        )
    )
    target_scaler = joblib.load(
        _download_artifact(
            client,
            evaluation.run_id,
            "preprocessing/target_scaler.joblib",
            download_root,
        )
    )
    metadata_path = _download_artifact(
        client, evaluation.run_id, "metadata/reproducibility.json", download_root
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    state = torch.load(state_path, map_location="cpu", weights_only=True)
    incompatible = model.load_state_dict(state, strict=True)
    sequence_length = int(evaluation.params["sequence_length"])
    input_size = int(evaluation.params["input_size"])
    with torch.no_grad():
        prediction = model(torch.zeros((1, sequence_length, input_size))).numpy()
    config = metadata.get("config", {})
    architecture_names = tuple(
        name for name in MODEL_REQUIRED_PARAMS["gru"] if name != "feature_list"
    )
    passed = bool(
        not incompatible.missing_keys
        and not incompatible.unexpected_keys
        and np.isfinite(prediction).all()
        and int(feature_scaler.n_features_in_) == input_size
        and int(target_scaler.n_features_in_) == 1
        and all(name in config for name in architecture_names)
        and all(
            str(config[name]) == str(evaluation.params[name])
            for name in architecture_names
        )
    )
    evaluation.record(
        "model_artifact_reload",
        passed,
        "strict GRU state, matching metadata/scalers, finite prediction",
        {
            "strict": not incompatible.missing_keys
            and not incompatible.unexpected_keys,
            "finite_prediction": bool(np.isfinite(prediction).all()),
        },
        "GRU state, metadata, scaler, or prediction validation failed.",
    )


def _validate_arima_artifact(
    evaluation: ModelEvaluation,
    client: Any,
    download_root: Path,
) -> None:
    """Reload the immutable pre-test Statsmodels artifact and forecast once."""
    import mlflow.statsmodels

    model = mlflow.statsmodels.load_model(f"runs:/{evaluation.run_id}/model")
    metadata_path = _download_artifact(
        client, evaluation.run_id, "metadata/pre_test_model.json", download_root
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    forecast = np.asarray(model.forecast(steps=1), dtype=np.float64)
    passed = bool(
        int(model.nobs) == 444
        and len(model.model.endog) == 444
        and metadata.get("state_role") == "pre_test_deployable"
        and metadata.get("contains_test_history") is False
        and int(metadata.get("observation_count", -1)) == 444
        and forecast.shape == (1,)
        and np.isfinite(forecast).all()
    )
    evaluation.record(
        "model_artifact_reload",
        passed,
        {"nobs": 444, "contains_test_history": False, "finite_forecast": True},
        {
            "nobs": int(model.nobs),
            "contains_test_history": metadata.get("contains_test_history"),
            "finite_forecast": bool(np.isfinite(forecast).all()),
        },
        "ARIMA artifact is not the required reloadable pre-test state.",
    )


def evaluate_model_run(
    client: Any,
    model: str,
    run_id: str,
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
    manifest_hash: str,
    evaluator_commit: str,
    download_root: Path,
    repo_root: Path = REPO_ROOT,
    *,
    reload_model: bool = True,
) -> ModelEvaluation:
    """Evaluate one explicit run without silently dropping any failed check."""
    evaluation = ModelEvaluation(model=model, run_id=run_id)
    try:
        run = client.get_run(run_id)
    except Exception as exc:
        evaluation.record(
            "run_exists",
            False,
            "existing MLflow run",
            type(exc).__name__,
            f"MLflow run does not exist or is inaccessible: {exc}",
        )
        return evaluation
    evaluation.record("run_exists", True, "existing MLflow run", run_id, "")
    validate_run_metadata(
        evaluation, run, contract, manifest_hash, evaluator_commit, repo_root
    )
    try:
        evaluation.artifact_paths = _list_artifacts_recursive(client, run_id)
    except Exception as exc:
        evaluation.record(
            "artifact_uri",
            False,
            "accessible artifact tree",
            type(exc).__name__,
            f"Artifact URI is inaccessible: {exc}",
        )
        return evaluation
    evaluation.record(
        "artifact_uri",
        bool(evaluation.artifact_paths),
        "nonempty accessible artifact tree",
        evaluation.artifact_paths,
        "Artifact tree is empty.",
    )
    prediction_artifact, summary_artifact = validate_required_artifacts(evaluation)
    if prediction_artifact is None or summary_artifact is None:
        return evaluation
    _download_and_validate_csvs(
        evaluation,
        client,
        prediction_artifact,
        summary_artifact,
        contract,
        manifest,
        manifest_hash,
        download_root,
    )
    if reload_model:
        validate_model_artifact(evaluation, client, download_root)
    return evaluation


def _download_and_validate_csvs(
    evaluation: ModelEvaluation,
    client: Any,
    prediction_artifact: str,
    summary_artifact: str,
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
    manifest_hash: str,
    download_root: Path,
) -> None:
    """Download immutable CSV artifacts and run all content checks."""
    try:
        prediction_path = _download_artifact(
            client, evaluation.run_id, prediction_artifact, download_root
        )
        summary_path = _download_artifact(
            client, evaluation.run_id, summary_artifact, download_root
        )
        predictions = pd.read_csv(prediction_path)
        summary = pd.read_csv(summary_path)
    except Exception as exc:
        evaluation.record(
            "csv_download",
            False,
            "readable prediction and summary CSVs",
            type(exc).__name__,
            f"CSV artifact download or parsing failed: {exc}",
        )
        return
    evaluation.record("csv_download", True, "readable CSVs", "readable CSVs", "")
    evaluation.predictions = predictions
    validate_prediction_frame(
        evaluation, predictions, contract, manifest, manifest_hash
    )
    if tuple(predictions.columns) == PREDICTION_COLUMNS:
        try:
            evaluation.recomputed_metrics = recompute_metrics(predictions)
        except BenchmarkValidationError as exc:
            evaluation.record(
                "metric_recomputation",
                False,
                "finite protocol metrics",
                type(exc).__name__,
                str(exc),
            )
            return
        relationship = (
            evaluation.recomputed_metrics["rmse"] + METRIC_TOLERANCE
            >= evaluation.recomputed_metrics["mae"]
        )
        evaluation.record(
            "metric_recomputation",
            relationship,
            "finite metrics with RMSE >= MAE",
            evaluation.recomputed_metrics,
            "Recomputed metric quality gates failed.",
        )
        validate_summary_frame(evaluation, summary, contract, manifest_hash)


def finalize_eligibility(
    evaluations: dict[str, ModelEvaluation],
) -> bool:
    """Validate cross-model identity and set final valid/invalid/excluded statuses."""
    complete = set(evaluations) == set(MODEL_NAMES)
    candidates_pass = complete and all(
        not evaluation.failure_reasons for evaluation in evaluations.values()
    )
    if candidates_pass:
        candidates_pass = _validate_naive_identity(evaluations)
    if candidates_pass:
        for evaluation in evaluations.values():
            evaluation.status = "valid"
        return True
    for evaluation in evaluations.values():
        evaluation.status = "invalid" if evaluation.failure_reasons else "excluded"
        if not evaluation.failure_reasons:
            evaluation.record(
                "complete_four_model_benchmark",
                False,
                "four valid runs",
                "another model failed",
                "Run excluded because the four-model benchmark is incomplete.",
            )
    return False


def _validate_naive_identity(evaluations: dict[str, ModelEvaluation]) -> bool:
    """Require all four recomputed Naive metrics to match within protocol tolerance."""
    baseline = evaluations[MODEL_NAMES[0]].recomputed_metrics
    naive_names = tuple(name for name in METRIC_NAMES if name.startswith("naive_"))
    all_match = True
    for model, evaluation in evaluations.items():
        values = evaluation.recomputed_metrics
        matches = all(
            np.isclose(
                values[name],
                baseline[name],
                rtol=0.0,
                atol=METRIC_TOLERANCE,
            )
            for name in naive_names
        )
        evaluation.record(
            "naive_baseline_identity",
            matches,
            {name: baseline[name] for name in naive_names},
            {name: values[name] for name in naive_names},
            f"Naive baseline differs for model {model}.",
        )
        all_match = all_match and matches
    return all_match


def rank_valid_models(
    evaluations: dict[str, ModelEvaluation],
) -> list[ModelEvaluation]:
    """Apply the protocol's exact metric order and stable model-name fallback."""
    if set(evaluations) != set(MODEL_NAMES) or any(
        evaluation.status != "valid" for evaluation in evaluations.values()
    ):
        raise BenchmarkValidationError("Final ranking requires four valid models.")
    return sorted(
        evaluations.values(),
        key=lambda item: (
            item.recomputed_metrics["rmse"],
            item.recomputed_metrics["mae"],
            -item.recomputed_metrics["directional_accuracy"],
            item.model,
        ),
    )


def build_overview_rows(
    evaluations: dict[str, ModelEvaluation],
    contract: LockedBenchmarkContract,
    manifest_hash: str,
    ranking: list[ModelEvaluation],
) -> list[dict[str, Any]]:
    """Build exact protocol rows in deterministic ranking or model order."""
    ranks = {evaluation.model: index + 1 for index, evaluation in enumerate(ranking)}
    ordered = ranking if ranking else [evaluations[model] for model in MODEL_NAMES]
    rows: list[dict[str, Any]] = []
    for evaluation in ordered:
        metrics = evaluation.recomputed_metrics
        row = {
            "rank": ranks.get(evaluation.model, ""),
            "dataset_version": contract.dataset_version,
            "snapshot_name": contract.snapshot_name,
            "test_manifest_sha256": manifest_hash,
            "symbol": contract.symbol,
            "timeframe": contract.timeframe,
            "model": evaluation.model,
            "n_samples": contract.prediction_rows,
            "mae": metrics.get("mae", ""),
            "rmse": metrics.get("rmse", ""),
            "mape_pct": metrics.get("mape_pct", ""),
            "directional_accuracy": metrics.get("directional_accuracy", ""),
            "naive_mae": metrics.get("naive_mae", ""),
            "naive_rmse": metrics.get("naive_rmse", ""),
            "naive_mape_pct": metrics.get("naive_mape_pct", ""),
            "improvement_vs_naive_rmse_pct": metrics.get(
                "improvement_vs_naive_rmse_pct", ""
            ),
            "run_id": evaluation.run_id,
            "seed": contract.seed,
            "status": evaluation.status,
        }
        rows.append({name: row[name] for name in OVERVIEW_COLUMNS})
    return rows


def generated_timestamp() -> str:
    """Return an explicit UTC timestamp for human and machine reports."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_audit_payload(
    contract: LockedBenchmarkContract,
    manifest_hash: str,
    evaluations: dict[str, ModelEvaluation],
    ranking: list[ModelEvaluation],
    evaluator_commit: str,
    generated_at: str,
) -> dict[str, Any]:
    """Build the machine-readable benchmark evidence document."""
    return {
        "benchmark_contract": {
            **contract.as_dict(),
            "test_manifest_sha256": manifest_hash,
        },
        "models": {model: evaluations[model].as_audit_dict() for model in MODEL_NAMES},
        "run_ids": {model: evaluations[model].run_id for model in MODEL_NAMES},
        "source_commits": {
            model: evaluations[model].source_commit for model in MODEL_NAMES
        },
        "checks": {
            "four_models_valid": all(
                evaluation.status == "valid" for evaluation in evaluations.values()
            ),
            "cross_model_row_identity": all(
                any(
                    check.name == "locked_manifest_rows" and check.status == "pass"
                    for check in evaluation.checks
                )
                for evaluation in evaluations.values()
            ),
            "naive_identity": all(
                any(
                    check.name == "naive_baseline_identity" and check.status == "pass"
                    for check in evaluation.checks
                )
                for evaluation in evaluations.values()
            ),
        },
        "expected": {
            "models": list(MODEL_NAMES),
            "status": "valid",
            "prediction_rows": contract.prediction_rows,
        },
        "actual": {
            "valid_models": [
                model for model in MODEL_NAMES if evaluations[model].status == "valid"
            ],
            "excluded_models": [
                model for model in MODEL_NAMES if evaluations[model].status != "valid"
            ],
        },
        "status": (
            "valid"
            if all(evaluation.status == "valid" for evaluation in evaluations.values())
            else "invalid"
        ),
        "failure_reason": {
            model: evaluations[model].failure_reasons
            for model in MODEL_NAMES
            if evaluations[model].failure_reasons
        },
        "ranking_rule": {
            "primary": "rmse_asc",
            "secondary": "mae_asc",
            "tertiary": "directional_accuracy_desc",
            "deterministic_fallback": "model_name_asc",
        },
        "ranking": [
            {
                "rank": index + 1,
                "model": evaluation.model,
                **evaluation.recomputed_metrics,
            }
            for index, evaluation in enumerate(ranking)
        ],
        "generated_at": generated_at,
        "evaluator_source_commit": evaluator_commit,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "mlflow": mlflow.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }


def render_report(
    contract: LockedBenchmarkContract,
    manifest_hash: str,
    evaluations: dict[str, ModelEvaluation],
    ranking: list[ModelEvaluation],
    evaluator_commit: str,
    generated_at: str,
    command: str,
) -> str:
    """Render the required human-readable benchmark report from validated data."""
    lines = [
        "# ACB 1d Four-Model Benchmark",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Evaluator source commit: `{evaluator_commit}`",
        "- Workflow: `single-contributor`",
        "",
        "## Benchmark contract",
        "",
        f"- Dataset/snapshot: `{contract.dataset_version}` / `{contract.snapshot_name}`",
        f"- Symbol/timeframe: `{contract.symbol}` / `{contract.timeframe}`",
        f"- Target/horizon: `{contract.target}` / `{contract.horizon}`",
        f"- Split/seed/rows: `{contract.split}` / `{contract.seed}` / `{contract.prediction_rows}`",
        f"- Manifest: `{manifest_hash}`",
        "",
        "## Ranking rule",
        "",
        "RMSE ascending, then MAE ascending, then Directional Accuracy descending. "
        "Model name ascending is only a deterministic display fallback.",
        "",
        "## Official runs and eligibility",
        "",
        "| Model | Run ID | Source commit | Source summary | Eligibility |",
        "|---|---|---|---|---|",
    ]
    for model in MODEL_NAMES:
        evaluation = evaluations[model]
        lines.append(
            f"| {model} | `{evaluation.run_id}` | "
            f"`{evaluation.source_commit}` | `{evaluation.source_summary_status}` | "
            f"{evaluation.status} |"
        )
    lines.extend(_report_ranking_lines(ranking))
    excluded = [
        evaluation
        for evaluation in evaluations.values()
        if evaluation.status in {"invalid", "excluded"}
    ]
    lines.extend(
        [
            "",
            "## Exclusions",
            "",
            (
                "None among the four explicitly selected official runs."
                if not excluded
                else "; ".join(
                    f"`{item.model}`: {', '.join(item.failure_reasons)}"
                    for item in excluded
                )
            ),
        ]
    )
    lines.extend(_report_naive_lines(ranking))
    lines.extend(
        [
            "",
            "## Cross-model validation",
            "",
            "- Locked manifest row identity: PASS",
            "- Canonical manifest hash: PASS",
            "- Independent metric recomputation: PASS",
            "- Naive baseline identity: PASS",
            "",
            "## Environment",
            "",
            f"- Python: `{platform.python_version()}`",
            f"- Platform: `{platform.platform()}`",
            f"- MLflow: `{mlflow.__version__}`",
            f"- NumPy: `{np.__version__}`",
            f"- Pandas: `{pd.__version__}`",
            "",
            "## Reproduction command",
            "",
            "```text",
            command,
            "```",
            "",
            "## Limitations",
            "",
            "- This is a single locked ACB 1d holdout benchmark, not a claim of "
            "statistical superiority across assets, periods, or repeated samples.",
            "- A negative RMSE improvement means the model did not beat the "
            "horizon-one Naive baseline on this test manifest.",
            "- Source training summaries remain immutable; benchmark eligibility is "
            "recorded separately by this evaluator.",
            "",
            "## Conclusion",
            "",
            (
                "Issue #20 benchmark gates passed for all four official runs; "
                "the result is ready for PR review and post-merge verification."
                if ranking
                else "Issue #20 remains open because no official ranking was produced."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _report_ranking_lines(ranking: list[ModelEvaluation]) -> list[str]:
    """Render full-precision ranking and Naive comparison rows."""
    lines = [
        "",
        "## Final ranking",
        "",
        "| Rank | Model | MAE | RMSE | MAPE % | Directional accuracy | "
        "Improvement vs Naive RMSE % |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    if not ranking:
        return [*lines, "| N/A | No official ranking | N/A | N/A | N/A | N/A | N/A |"]
    for rank, evaluation in enumerate(ranking, start=1):
        metrics = evaluation.recomputed_metrics
        lines.append(
            f"| {rank} | {evaluation.model} | {metrics['mae']} | "
            f"{metrics['rmse']} | {metrics['mape_pct']} | "
            f"{metrics['directional_accuracy']} | "
            f"{metrics['improvement_vs_naive_rmse_pct']} |"
        )
    return lines


def _report_naive_lines(ranking: list[ModelEvaluation]) -> list[str]:
    """Render the one canonical Naive baseline shared by all valid models."""
    lines = [
        "",
        "## Naive baseline comparison",
        "",
        "| MAE | RMSE | MAPE % | Directional accuracy |",
        "|---:|---:|---:|---:|",
    ]
    if not ranking:
        return [*lines, "| N/A | N/A | N/A | N/A |"]
    metrics = ranking[0].recomputed_metrics
    return [
        *lines,
        f"| {metrics['naive_mae']} | {metrics['naive_rmse']} | "
        f"{metrics['naive_mape_pct']} | "
        f"{metrics['naive_directional_accuracy']} |",
    ]


def _write_overview(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write exact protocol CSV without a Pandas index."""
    import csv

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OVERVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def stage_outputs(
    output_dir: Path,
    overview_rows: list[dict[str, Any]],
    report: str,
    audit: dict[str, Any],
) -> Path:
    """Write all output files to one same-filesystem staging directory."""
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staged-", dir=output_dir.parent)
    )
    _write_overview(staged / OUTPUT_FILENAMES[0], overview_rows)
    (staged / OUTPUT_FILENAMES[1]).write_text(report, encoding="utf-8", newline="\n")
    (staged / OUTPUT_FILENAMES[2]).write_text(
        json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return staged


def publish_staged_outputs(staged: Path, output_dir: Path) -> None:
    """Replace the complete output directory with rollback on rename failure."""
    backup = output_dir.with_name(f".{output_dir.name}.backup-{uuid.uuid4().hex}")
    had_previous = output_dir.exists()
    try:
        if had_previous:
            output_dir.replace(backup)
        staged.replace(output_dir)
    except Exception:
        if not output_dir.exists() and backup.exists():
            backup.replace(output_dir)
        raise
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    if backup.exists():
        shutil.rmtree(backup)


def write_failure_audit(output_dir: Path, audit: dict[str, Any]) -> Path:
    """Persist failure evidence beside, never inside, the official output directory."""
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    destination = output_dir.with_name(f"{output_dir.name}_failed_audit.json")
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, destination)
    return destination


def log_benchmark_evidence(
    staged: Path,
    contract: LockedBenchmarkContract,
    manifest_hash: str,
    evaluations: dict[str, ModelEvaluation],
    evaluator_commit: str,
    ranking: list[ModelEvaluation],
) -> str:
    """Log one non-model MLflow run containing final benchmark evidence."""
    init_mlflow()
    mlflow.set_experiment(BENCHMARK_EXPERIMENT)
    params: dict[str, Any] = {
        "benchmark": "acb_1d_four_model",
        **contract.as_dict(),
        "test_manifest_sha256": manifest_hash,
        **{f"{model}_run_id": evaluations[model].run_id for model in MODEL_NAMES},
        "ranking_primary": "rmse_asc",
        "ranking_secondary": "mae_asc",
        "ranking_tertiary": "directional_accuracy_desc",
        "evaluator_source_commit": evaluator_commit,
        "workflow": "single-contributor",
    }
    with mlflow.start_run(run_name="acb_1d_four_model_evaluator") as run:
        mlflow.log_params(params)
        mlflow.set_tags(
            {
                "run_role": "benchmark_evaluator",
                "register_as_model": "false",
            }
        )
        mlflow.log_metrics(
            {
                "eligible_models": float(len(ranking)),
                "best_rmse": ranking[0].recomputed_metrics["rmse"],
                "best_mae": ranking[0].recomputed_metrics["mae"],
            }
        )
        for filename in OUTPUT_FILENAMES:
            mlflow.log_artifact(str(staged / filename))
        return str(run.info.run_id)


def benchmark_command(run_ids: dict[str, str], output_dir: Path) -> str:
    """Render one root-relative reproducibility command without local absolute paths."""
    parts = ["python -m services.training.benchmark"]
    for model in MODEL_NAMES:
        option = model.replace("_", "-")
        parts.append(f"  --{option}-run-id {run_ids[model]}")
    try:
        relative_output = output_dir.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        relative_output = Path("artifacts/benchmarks/ACB_1d")
    parts.append(f"  --output-dir {relative_output.as_posix()}")
    return " \\\n".join(parts)


def run_benchmark(
    args: argparse.Namespace,
    *,
    client: Any | None = None,
    repo_root: Path = REPO_ROOT,
    reload_models: bool = True,
    log_evidence: bool = True,
) -> BenchmarkResult:
    """Execute eligibility, ranking, atomic output, and MLflow evidence logging."""
    run_ids = explicit_run_ids(args)
    require_clean_worktree(repo_root)
    evaluator_commit = current_source_commit(repo_root)
    contract = load_benchmark_contract()
    manifest, manifest_hash = build_locked_test_manifest(contract)
    init_mlflow()
    tracking_client = mlflow.tracking.MlflowClient() if client is None else client
    generated_at = generated_timestamp()
    evaluations: dict[str, ModelEvaluation] = {}
    with tempfile.TemporaryDirectory(prefix="benchmark_downloads_") as temp_dir:
        download_root = Path(temp_dir)
        for model in MODEL_NAMES:
            evaluations[model] = evaluate_model_run(
                tracking_client,
                model,
                run_ids[model],
                contract,
                manifest,
                manifest_hash,
                evaluator_commit,
                download_root,
                repo_root,
                reload_model=reload_models,
            )
    success = finalize_eligibility(evaluations)
    ranking = rank_valid_models(evaluations) if success else []
    audit = build_audit_payload(
        contract,
        manifest_hash,
        evaluations,
        ranking,
        evaluator_commit,
        generated_at,
    )
    if not success:
        failure_path = write_failure_audit(args.output_dir, audit)
        raise BenchmarkValidationError(
            f"Benchmark contract failed; audit written to {failure_path.name}.",
            audit,
        )
    command = benchmark_command(run_ids, args.output_dir)
    report = render_report(
        contract,
        manifest_hash,
        evaluations,
        ranking,
        evaluator_commit,
        generated_at,
        command,
    )
    overview_rows = build_overview_rows(evaluations, contract, manifest_hash, ranking)
    staged = stage_outputs(args.output_dir, overview_rows, report, audit)
    try:
        evaluator_run_id = (
            log_benchmark_evidence(
                staged,
                contract,
                manifest_hash,
                evaluations,
                evaluator_commit,
                ranking,
            )
            if log_evidence
            else "not-logged"
        )
        publish_staged_outputs(staged, args.output_dir)
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        raise
    return BenchmarkResult(
        output_dir=args.output_dir,
        evaluator_run_id=evaluator_run_id,
        ranking=tuple(overview_rows),
        generated_at=generated_at,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the official evaluator and return a contract-aware process exit code."""
    setup_logging()
    args = parse_args(argv)
    try:
        result = run_benchmark(args)
    except BenchmarkValidationError as exc:
        logger.error("%s", exc)
        return 1
    except Exception:
        logger.exception("Benchmark evaluator failed unexpectedly.")
        return 1
    logger.info(
        "Benchmark completed: output=%s evaluator_run_id=%s",
        result.output_dir,
        result.evaluator_run_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
