"""Standalone, reproducible training entrypoint for the Random Forest model.

Uses the *same* DataLoader, feature set, train/val/test split, and metrics as
the XGBoost pipeline so results are directly comparable.

Usage:
    python -m services.training.train_random_forest \\
        --ticker FPT --timeframe 1d --n-trials 50 --seed 42
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import joblib
import mlflow
import numpy as np
import optuna
import pandas as pd
from sklearn.preprocessing import StandardScaler

from services.training.evaluate import (
    compare_with_naive,
    evaluate_predictions,
)
from services.training.mlflow_utils import log_experiment_run
from services.training.models.random_forest_model import RandomForestModelWrapper

# ── Shared feature contract (same as XGBoost, enforced here) ──────────────────
from services.training.models.xgboost_features import (
    FEATURE_LIST,
    build_xgboost_features,
)
from shared.dataset.loader import assert_locked_dataset, load_full
from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_N_TRIALS: int = 50
DEFAULT_SEED: int = 42
TARGET_COLUMN: str = "next_close"
SCALER_ARTIFACT_NAME: str = "standard_scaler.joblib"
RESULTS_PATH: Path = (
    Path(__file__).resolve().parents[2] / "results" / "random_forest_results.csv"
)

# ── Result schema — identical to XGBoost 27-column layout ─────────────────────
RESULT_FIELDNAMES: tuple[str, ...] = (
    "ticker",
    "timeframe",
    "mae_val",
    "rmse_val",
    "mape_val",
    "mae_test",
    "rmse_test",
    "mape_test",
    "mlflow_run_id",
    "naive_mae_val",
    "naive_rmse_val",
    "naive_mape_val",
    "improvement_pct_mae_val",
    "improvement_pct_rmse_val",
    "improvement_pct_mape_val",
    "improvement_abs_mae_val",
    "improvement_abs_rmse_val",
    "improvement_abs_mape_val",
    "naive_mae_test",
    "naive_rmse_test",
    "naive_mape_test",
    "improvement_pct_mae_test",
    "improvement_pct_rmse_test",
    "improvement_pct_mape_test",
    "improvement_abs_mae_test",
    "improvement_abs_rmse_test",
    "improvement_abs_mape_test",
)
RESULT_METADATA_FIELDNAMES: tuple[str, ...] = (
    "ticker",
    "timeframe",
    "mlflow_run_id",
)
RESULT_METRIC_FIELDNAMES: tuple[str, ...] = tuple(
    field_name
    for field_name in RESULT_FIELDNAMES
    if field_name not in RESULT_METADATA_FIELDNAMES
)

# ── Optuna search ranges for Random Forest hyperparameters ────────────────────
N_ESTIMATORS_RANGE: tuple[int, int] = (50, 500)
MAX_DEPTH_RANGE: tuple[int, int] = (3, 20)
MIN_SAMPLES_SPLIT_RANGE: tuple[int, int] = (2, 20)
MIN_SAMPLES_LEAF_RANGE: tuple[int, int] = (1, 10)
MAX_FEATURES_CHOICES: tuple[str, ...] = ("sqrt", "log2")

# ── Type aliases ──────────────────────────────────────────────────────────────
ModelParams = dict[str, Any]
MetricValue = float | None
EvaluationMetrics = dict[str, MetricValue]
SplitSuffix = Literal["val", "test"]


# ── Data container ─────────────────────────────────────────────────────────────
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


# ── CLI ────────────────────────────────────────────────────────────────────────

def _positive_int(value: str) -> int:
    """Parse a strictly positive integer for argparse."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the standalone Random Forest training CLI.

    Input:
        argv: list of string arguments (``None`` reads ``sys.argv``).

    Output:
        Parsed namespace with ``ticker``, ``timeframe``, ``n_trials``, ``seed``.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Ticker in the locked dataset")
    parser.add_argument(
        "--timeframe",
        required=True,
        help="Timeframe in the locked dataset, e.g. 1d or 1h",
    )
    parser.add_argument("--n-trials", type=_positive_int, default=DEFAULT_N_TRIALS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


# ── Reproducibility ────────────────────────────────────────────────────────────

def set_random_seed(seed: int) -> None:
    """Seed Python and NumPy RNGs before any tuning or model training.

    Input:
        seed: integer seed value.
    """
    random.seed(seed)
    np.random.seed(seed)


# ── Feature scaling (same logic as XGBoost pipeline) ─────────────────────────

def _scaled_frame(
    values: np.ndarray,
    source: pd.DataFrame,
) -> pd.DataFrame:
    """Restore feature names and indices after a scaler transformation.

    Input:
        values: numpy array of shape (n_samples, n_features).
        source: original DataFrame whose columns and index are restored.

    Output:
        DataFrame with FEATURE_LIST columns and source's index.
    """
    return pd.DataFrame(values, columns=FEATURE_LIST, index=source.index)


def prepare_scaled_dataset(
    splits: dict[str, pd.DataFrame],
) -> ScaledDataset:
    """Fit StandardScaler on train only, then transform validation and test.

    The scaler is fitted exclusively on the training split to prevent
    data leakage into validation or test.

    Input:
        splits: dict with keys ``"train"``, ``"val"``, ``"test"``, each
            a DataFrame produced by ``build_xgboost_features``.

    Output:
        :class:`ScaledDataset` with the fitted scaler and scaled splits.
    """
    train_df = splits["train"]
    val_df = splits["val"]
    test_df = splits["test"]
    if any(split.empty for split in (train_df, val_df, test_df)):
        raise ValueError("Train, validation, and test splits must all be non-empty.")

    train_features = train_df.loc[:, FEATURE_LIST]
    val_features = val_df.loc[:, FEATURE_LIST]
    test_features = test_df.loc[:, FEATURE_LIST]
    scaler = StandardScaler()
    scaler.fit(train_features)

    return ScaledDataset(
        scaler=scaler,
        X_train=_scaled_frame(scaler.transform(train_features), train_features),
        y_train=train_df[TARGET_COLUMN],
        X_val=_scaled_frame(scaler.transform(val_features), val_features),
        y_val=val_df[TARGET_COLUMN],
        X_test=_scaled_frame(scaler.transform(test_features), test_features),
        y_test=test_df[TARGET_COLUMN],
    )


# ── Optuna hyperparameter tuning ───────────────────────────────────────────────

def _trial_params(trial: optuna.Trial, seed: int) -> ModelParams:
    """Sample one reproducible Random Forest parameter configuration.

    Input:
        trial: Optuna trial object.
        seed:  integer seed forwarded as ``random_state``.

    Output:
        Dict of hyperparameter name → sampled value.
    """
    return {
        "n_estimators": trial.suggest_int("n_estimators", *N_ESTIMATORS_RANGE),
        "max_depth": trial.suggest_int("max_depth", *MAX_DEPTH_RANGE),
        "min_samples_split": trial.suggest_int(
            "min_samples_split", *MIN_SAMPLES_SPLIT_RANGE
        ),
        "min_samples_leaf": trial.suggest_int(
            "min_samples_leaf", *MIN_SAMPLES_LEAF_RANGE
        ),
        "max_features": trial.suggest_categorical(
            "max_features", list(MAX_FEATURES_CHOICES)
        ),
        "random_state": seed,
        "n_jobs": -1,
    }


def objective_optuna(
    trial: optuna.Trial,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    seed: int,
) -> float:
    """Minimise locked-validation MAE without touching the test split.

    Input:
        trial:   Optuna trial object.
        X_train: training feature matrix.
        y_train: training targets.
        X_val:   validation feature matrix.
        y_val:   validation targets.
        seed:    RNG seed for reproducibility.

    Output:
        Validation MAE (float) — Optuna minimises this.
    """
    model = RandomForestModelWrapper(params=_trial_params(trial, seed))
    model.fit(X_train, y_train)
    predictions = model.predict(X_val)
    return float(np.mean(np.abs(y_val.to_numpy() - predictions)))


def optimize_params(
    data: ScaledDataset,
    n_trials: int,
    seed: int,
) -> ModelParams:
    """Tune hyperparameters against the locked validation split.

    Input:
        data:     :class:`ScaledDataset` with pre-scaled feature splits.
        n_trials: number of Optuna trials to run.
        seed:     RNG seed for the TPE sampler.

    Output:
        Best parameter dict (including ``random_state`` and ``n_jobs``).
    """
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
        "random_state": seed,
        "n_jobs": -1,
    }


# ── Model training ─────────────────────────────────────────────────────────────

def train_final_model(
    data: ScaledDataset,
    best_params: ModelParams,
) -> RandomForestModelWrapper:
    """Fit the final Random Forest on the training split with best params.

    Input:
        data:        :class:`ScaledDataset` with pre-scaled feature splits.
        best_params: hyperparameter dict from :func:`optimize_params`.

    Output:
        Fitted :class:`RandomForestModelWrapper`.
    """
    model = RandomForestModelWrapper(params=best_params)
    model.fit(data.X_train, data.y_train)
    return model


# ── Evaluation ─────────────────────────────────────────────────────────────────

def _evaluate_split(
    model: RandomForestModelWrapper,
    X: pd.DataFrame,
    y: pd.Series,
    previous_close: pd.Series,
    suffix: SplitSuffix,
) -> EvaluationMetrics:
    """Evaluate one held-out split against its current-close naive forecast.

    Input:
        model:         fitted :class:`RandomForestModelWrapper`.
        X:             feature matrix for this split.
        y:             true target values.
        previous_close: close prices at time *t* (naive forecast anchor).
        suffix:        ``"val"`` or ``"test"`` — appended to metric keys.

    Output:
        Dict of ``{metric_name}_{suffix}`` → value.
    """
    y_true = y.to_numpy()
    y_pred = model.predict(X)
    y_naive = previous_close.to_numpy()

    base_metrics = evaluate_predictions(
        y_true=y_true,
        y_pred=y_pred,
        previous_close=y_naive,
    )
    comparison = compare_with_naive(
        y_true=y_true,
        y_pred=y_pred,
        y_naive=y_naive,
    )

    metrics: EvaluationMetrics = {**base_metrics}
    for group_name, group_metrics in comparison.items():
        prefix = "" if group_name == "model" else f"{group_name}_"
        metrics.update(
            {
                f"{prefix}{metric_name}": value
                for metric_name, value in group_metrics.items()
            }
        )

    return {f"{metric_name}_{suffix}": value for metric_name, value in metrics.items()}


def evaluate_model(
    model: RandomForestModelWrapper,
    data: ScaledDataset,
    splits: dict[str, pd.DataFrame],
) -> EvaluationMetrics:
    """Report validation and final test metrics, including naive baselines.

    Input:
        model:  fitted :class:`RandomForestModelWrapper`.
        data:   :class:`ScaledDataset` with scaled features.
        splits: raw splits dict from ``build_xgboost_features`` (for ``close``
                column used in naive baseline).

    Output:
        Combined dict of val and test metrics.
    """
    val_metrics = _evaluate_split(
        model,
        data.X_val,
        data.y_val,
        splits["val"]["close"],
        "val",
    )
    test_metrics = _evaluate_split(
        model,
        data.X_test,
        data.y_test,
        splits["test"]["close"],
        "test",
    )
    return {**val_metrics, **test_metrics}


# ── MLflow logging ─────────────────────────────────────────────────────────────

def _log_scaler_artifact(scaler: StandardScaler, run_id: str) -> None:
    """Serialise the train-fitted scaler into the same MLflow run.

    Input:
        scaler: fitted :class:`~sklearn.preprocessing.StandardScaler`.
        run_id: existing MLflow run ID to attach the artifact to.
    """
    with tempfile.TemporaryDirectory(prefix="rf_scaler_") as temp_dir:
        scaler_path = Path(temp_dir) / SCALER_ARTIFACT_NAME
        joblib.dump(scaler, scaler_path)
        with mlflow.start_run(run_id=run_id):
            mlflow.log_artifact(str(scaler_path), artifact_path="preprocessing")


def log_training_run(
    ticker: str,
    timeframe: str,
    seed: int,
    n_trials: int,
    best_params: ModelParams,
    metrics: Mapping[str, MetricValue],
    model: RandomForestModelWrapper,
    scaler: StandardScaler,
) -> str:
    """Log parameters, metrics, model, and scaler to one MLflow run.

    Input:
        ticker:      asset ticker string (e.g. ``"FPT"`` or ``"BTC/USDT"``).
        timeframe:   data resolution (e.g. ``"1d"``).
        seed:        RNG seed used for this run.
        n_trials:    number of Optuna trials that were run.
        best_params: best hyperparameters from Optuna.
        metrics:     evaluation metric dict (``None`` values filtered out).
        model:       fitted :class:`RandomForestModelWrapper`.
        scaler:      train-fitted :class:`~sklearn.preprocessing.StandardScaler`.

    Output:
        MLflow run ID string.
    """
    ticker_safe = ticker.replace("/", "-")
    live_model_params = {
        name: value
        for name, value in model.get_params().items()
        if value is not None
    }
    logged_params = {
        **best_params,
        **live_model_params,
        "ticker": ticker,
        "timeframe": timeframe,
        "seed": seed,
        "n_trials": n_trials,
        "feature_list": ",".join(FEATURE_LIST),
    }

    defined_metrics = {
        metric_name: metric_value
        for metric_name, metric_value in metrics.items()
        if metric_value is not None
    }
    run_id = log_experiment_run(
        experiment_name=f"{ticker_safe}_{timeframe}_random_forest",
        run_name=f"random_forest_{ticker_safe}_{timeframe}",
        params=logged_params,
        metrics=defined_metrics,
        model=model.model,
        model_name_in_registry=f"{ticker_safe}_{timeframe}_random_forest",
    )
    _log_scaler_artifact(scaler, run_id)
    return str(run_id)


# ── CSV result export ──────────────────────────────────────────────────────────

def append_result(
    ticker: str,
    timeframe: str,
    metrics: Mapping[str, MetricValue],
    run_id: str,
    results_path: Path = RESULTS_PATH,
) -> None:
    """Append one result row only when an existing CSV uses the exact 27-column schema.

    Input:
        ticker:       asset ticker string.
        timeframe:    data resolution.
        metrics:      evaluation metric dict (``None`` serialised as empty string).
        run_id:       MLflow run ID.
        results_path: destination CSV path (created if absent).
    """
    try:
        file_exists = results_path.exists()
        if file_exists:
            with results_path.open("r", newline="", encoding="utf-8") as csv_file:
                existing_header = tuple(next(csv.reader(csv_file), []))
            if existing_header != RESULT_FIELDNAMES:
                raise ValueError(
                    f"Refusing to append to {results_path}: CSV header does not "
                    f"match the required 27-column schema. "
                    f"Expected {RESULT_FIELDNAMES}, got {existing_header}."
                )
        else:
            results_path.parent.mkdir(parents=True, exist_ok=True)

        row: dict[str, float | str] = {
            "ticker": ticker,
            "timeframe": timeframe,
            **{
                field_name: "" if metrics[field_name] is None else metrics[field_name]
                for field_name in RESULT_METRIC_FIELDNAMES
            },
            "mlflow_run_id": run_id,
        }
        with results_path.open("a", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=RESULT_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except OSError as exc:
        logger.exception(
            "Failed to append Random Forest results to %s: %s", results_path, exc
        )
        raise


# ── Orchestrator ───────────────────────────────────────────────────────────────

def run_training(args: argparse.Namespace) -> str:
    """Execute the locked-data RF tuning, training, and reporting flow.

    Input:
        args: parsed CLI namespace (``ticker``, ``timeframe``, ``n_trials``,
              ``seed``).

    Output:
        MLflow run ID string.
    """
    set_random_seed(args.seed)
    assert_locked_dataset()

    full_df = load_full(args.ticker, args.timeframe)
    # Use the same feature pipeline as XGBoost for direct comparability.
    splits = build_xgboost_features(full_df)
    data = prepare_scaled_dataset(splits)
    best_params = optimize_params(data, args.n_trials, args.seed)
    model = train_final_model(data, best_params)
    metrics = evaluate_model(model, data, splits)
    run_id = log_training_run(
        args.ticker,
        args.timeframe,
        args.seed,
        args.n_trials,
        best_params,
        metrics,
        model,
        data.scaler,
    )
    append_result(args.ticker, args.timeframe, metrics, run_id)
    logger.info("Random Forest training completed. MLflow run ID: %s", run_id)
    return run_id


# ── CLI entrypoint ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    args = parse_args(argv)
    setup_logging()
    run_training(args)


if __name__ == "__main__":
    main()
