"""Standalone, reproducible training entrypoint for the XGBoost model."""

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
from services.training.models.xgboost_features import (
    FEATURE_LIST,
    build_xgboost_features,
)
from services.training.models.xgboost_model import XGBoostModelWrapper
from shared.dataset.loader import assert_locked_dataset, load_full
from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_N_TRIALS = 50
DEFAULT_SEED = 42
EARLY_STOPPING_ROUNDS = 50
TARGET_COLUMN = "next_close"
SCALER_ARTIFACT_NAME = "standard_scaler.joblib"
RESULTS_PATH = Path(__file__).resolve().parents[2] / "results" / "xgboost_results.csv"

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

N_ESTIMATORS_RANGE: tuple[int, int] = (50, 200)
MAX_DEPTH_RANGE: tuple[int, int] = (3, 9)
LEARNING_RATE_RANGE: tuple[float, float] = (0.01, 0.2)
SAMPLING_RANGE: tuple[float, float] = (0.6, 1.0)
REGULARIZATION_RANGE: tuple[float, float] = (1e-4, 10.0)

ModelParams = dict[str, Any]
MetricValue = float | None
EvaluationMetrics = dict[str, MetricValue]
SplitSuffix = Literal["val", "test"]


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
    parser.add_argument("--ticker", required=True, help="Ticker in the locked dataset")
    parser.add_argument(
        "--timeframe",
        required=True,
        help="Timeframe in the locked dataset, for example 1d or 1h",
    )
    parser.add_argument("--n-trials", type=_positive_int, default=DEFAULT_N_TRIALS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


def set_random_seed(seed: int) -> None:
    """Seed Python and NumPy before any tuning or model training."""
    random.seed(seed)
    np.random.seed(seed)


def _scaled_frame(
    values: np.ndarray,
    source: pd.DataFrame,
) -> pd.DataFrame:
    """Restore feature names and indices after a scaler transformation."""
    return pd.DataFrame(values, columns=FEATURE_LIST, index=source.index)


def prepare_scaled_dataset(
    splits: dict[str, pd.DataFrame],
) -> ScaledDataset:
    """Fit StandardScaler on train only, then transform validation and test."""
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


def _trial_params(trial: optuna.Trial, seed: int) -> ModelParams:
    """Sample one reproducible XGBoost parameter configuration."""
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
    }


def objective_optuna(
    trial: optuna.Trial,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    seed: int,
) -> float:
    """Minimize locked-validation MAE without touching the test split."""
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
    """Tune hyperparameters against the locked validation split."""
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
    }


def train_final_model(
    data: ScaledDataset,
    best_params: ModelParams,
) -> XGBoostModelWrapper:
    """Fit the final model on train with early stopping against validation."""
    model = XGBoostModelWrapper(params=best_params)
    model.fit(
        data.X_train,
        data.y_train,
        X_val=data.X_val,
        y_val=data.y_val,
        early_stopping_rounds=EARLY_STOPPING_ROUNDS,
    )
    return model


def _evaluate_split(
    model: XGBoostModelWrapper,
    X: pd.DataFrame,
    y: pd.Series,
    previous_close: pd.Series,
    suffix: SplitSuffix,
) -> EvaluationMetrics:
    """Evaluate one held-out split against its current-close naive forecast."""
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
    model: XGBoostModelWrapper,
    data: ScaledDataset,
    splits: dict[str, pd.DataFrame],
) -> EvaluationMetrics:
    """Report validation and final test metrics, including naive baselines."""
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


def _log_scaler_artifact(scaler: StandardScaler, run_id: str) -> None:
    """Serialize the train-fitted scaler into the same MLflow run."""
    with tempfile.TemporaryDirectory(prefix="xgboost_scaler_") as temp_dir:
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
    model: XGBoostModelWrapper,
    scaler: StandardScaler,
) -> str:
    """Log parameters, metrics, model, and scaler to one MLflow run."""
    ticker_safe = ticker.replace("/", "-")
    live_model_params = {
        name: value
        for name, value in model.model.get_params().items()
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
    if model.best_iteration is not None:
        logged_params["best_iteration"] = model.best_iteration

    defined_metrics = {
        metric_name: metric_value
        for metric_name, metric_value in metrics.items()
        if metric_value is not None
    }
    run_id = log_experiment_run(
        experiment_name=f"{ticker_safe}_{timeframe}_xgboost",
        run_name=f"xgboost_{ticker_safe}_{timeframe}",
        params=logged_params,
        metrics=defined_metrics,
        model=model.model,
        model_name_in_registry=f"{ticker_safe}_{timeframe}_xgboost",
    )
    _log_scaler_artifact(scaler, run_id)
    return str(run_id)


def append_result(
    ticker: str,
    timeframe: str,
    metrics: Mapping[str, MetricValue],
    run_id: str,
    results_path: Path = RESULTS_PATH,
) -> None:
    """Append one row only when an existing CSV uses the exact 27-column schema."""
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
            "Failed to append XGBoost results to %s: %s", results_path, exc
        )
        raise


def run_training(args: argparse.Namespace) -> str:
    """Execute the locked-data XGBoost tuning, training, and reporting flow."""
    set_random_seed(args.seed)
    assert_locked_dataset()

    full_df = load_full(args.ticker, args.timeframe)
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
    logger.info("XGBoost training completed. MLflow run ID: %s", run_id)
    return run_id


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    args = parse_args(argv)
    setup_logging()
    run_training(args)


if __name__ == "__main__":
    main()
