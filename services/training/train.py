"""
Stock and Crypto Training Pipeline.

Supports 4 models: ARIMA, Random Forest, XGBoost, GRU.
Reads data from ``market.ohlcv``, engineers features, splits by time
(train 70% / val 15% / test 15%), computes Naive baseline, and logs
all metrics to MLflow.
"""

import argparse
import logging
import random
import sys
from typing import Any, Dict

import numpy as np
import optuna
import torch

from shared.utils.logging import setup_logging
from data_loader import DataLoader, FEATURE_COLUMNS
from models.arima_model import ARIMABaseline
from models.xgboost_model import XGBoostModelWrapper
from models.random_forest_model import RandomForestModelWrapper
from evaluate import evaluate_predictions, add_improvement_vs_naive
from mlflow_utils import log_experiment_run
from dataset_contract import (
    DatasetContract,
    get_split_config,
    get_target_config,
    get_timeframe_contract,
    load_dataset_contract,
    validate_row_count,
)

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# ==============================================================================
# Reproducibility — fix random seeds (AGENTS.md §6)
# ==============================================================================

RANDOM_SEED: int = 42

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)


# ==============================================================================
# CLI
# ==============================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stock and Crypto Training Pipeline")
    parser.add_argument(
        "--ticker",
        type=str,
        default="BTC/USDT",
        help="Ticker ID to train on (e.g. BTCUSDT, BTC/USDT, FPT)",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["arima", "xgboost", "random_forest", "gru", "lstm"],
        default="xgboost",
        help="Algorithm to train",
    )
    parser.add_argument(
        "--resolution", type=str, default="1d", help="Resolution: 1h or 1d"
    )
    parser.add_argument(
        "--tune", action="store_true", help="Perform hyperparameter tuning with Optuna"
    )
    parser.add_argument(
        "--dataset-config",
        type=str,
        default="configs/group_dataset.json",
        help="Dataset contract JSON. Use 'none' to disable contract enforcement.",
    )
    parser.add_argument(
        "--allow-custom-data",
        action="store_true",
        default=False,
        help=(
            "Acknowledge that results with custom data cannot be used in "
            "official reports."
        ),
    )
    return parser.parse_args()


def _load_dataset_contract_or_exit(args: argparse.Namespace) -> DatasetContract | None:
    """Load the dataset contract and reject accidental official-data bypasses."""
    dataset_config_path = (
        None if args.dataset_config.lower() == "none" else args.dataset_config
    )
    dataset_contract = load_dataset_contract(dataset_config_path)

    if dataset_contract is None:
        if not args.allow_custom_data:
            logger.error(
                "[WARNING] Dataset contract disabled (--dataset-config none). "
                "Results from this run CANNOT be used in official reports. "
                "If this is a debug run with custom data, add --allow-custom-data."
            )
            sys.exit(1)

        logger.warning(
            "Running with CUSTOM DATA (no contract). Results will NOT be valid "
            "for official reports."
        )

    return dataset_contract


def _dataset_tracking_params(
    dataset_contract: DatasetContract | None,
) -> dict[str, str]:
    """Return MLflow dataset metadata for official or custom-data runs."""
    if dataset_contract is None:
        return {
            "dataset_version": "CUSTOM",
            "source_snapshot_name": "CUSTOM",
            "dataset_contract": "NONE - CUSTOM DATA",
        }

    return {
        "dataset_version": str(dataset_contract["dataset_version"]),
        "source_snapshot_name": str(dataset_contract["source_snapshot_name"]),
    }


# ==============================================================================
# Optuna helper (XGBoost)
# ==============================================================================


def objective_optuna(
    trial: optuna.Trial,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> float:
    """Optuna objective function for tuning XGBoost parameters."""
    params: Dict[str, Any] = {
        "n_estimators": trial.suggest_int("n_estimators", 50, 200),
        "max_depth": trial.suggest_int("max_depth", 3, 9),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
    }

    model = XGBoostModelWrapper(params=params)
    model.fit(X_train, y_train)

    preds = model.predict(X_val)
    mae = float(np.mean(np.abs(y_val - preds)))
    return mae


# ==============================================================================
# Main pipeline
# ==============================================================================


def run_pipeline() -> None:
    args = parse_args()
    logger.info("Running pipeline for %s using %s model", args.ticker, args.model)

    dataset_contract = _load_dataset_contract_or_exit(args)
    dataset_timeframe = None
    if dataset_contract is not None:
        dataset_timeframe = get_timeframe_contract(
            dataset_contract,
            args.ticker,
            args.resolution,
        )
        logger.info(
            "Using dataset contract %s (%s)",
            dataset_contract["dataset_version"],
            dataset_contract["source_snapshot_name"],
        )

    # ------------------------------------------------------------------
    # 1. Load Data
    # ------------------------------------------------------------------
    loader = DataLoader(ticker_id=args.ticker, resolution=args.resolution)
    raw_df = loader.load_raw_data(
        limit=None,
        start_ts=dataset_timeframe["start_ts"] if dataset_timeframe else None,
        end_ts=dataset_timeframe["end_ts"] if dataset_timeframe else None,
    )

    if raw_df.empty:
        logger.error(
            "No historical prices found for %s. "
            "Please seed database or run ingestion first.",
            args.ticker,
        )
        return

    if dataset_contract is not None:
        validate_row_count(
            dataset_contract,
            loader.ticker_id,
            args.resolution,
            len(raw_df),
        )

    # ------------------------------------------------------------------
    # 2. Feature Engineering
    # ------------------------------------------------------------------
    features_df = loader.engineer_features(raw_df)
    logger.info("Feature engineering complete — %d rows, %d columns",
                len(features_df), len(features_df.columns))

    # ------------------------------------------------------------------
    # 3. Add target BEFORE split (avoids boundary data loss)
    # ------------------------------------------------------------------
    target_horizon, target_mode = get_target_config(dataset_contract)
    features_df = DataLoader.add_target(
        features_df,
        horizon=target_horizon,
        target_mode=target_mode,
    )

    # ------------------------------------------------------------------
    # 4. Train / Validation / Test split (sequential, no shuffle)
    # ------------------------------------------------------------------
    train_ratio, validation_ratio = get_split_config(dataset_contract)
    train_df, val_df, test_df = loader.prepare_train_validation_test_split(
        features_df,
        train_ratio=train_ratio,
        validation_ratio=validation_ratio,
    )

    if len(test_df) < 5:
        logger.error(
            "Test set too small (%d rows). Need more data to evaluate.",
            len(test_df),
        )
        return

    # Feature / target arrays for ML models
    feature_cols = [c for c in FEATURE_COLUMNS if c in train_df.columns]
    target_col = "target"

    X_train = train_df[feature_cols]
    y_train = train_df[target_col]
    X_val = val_df[feature_cols]
    y_val = val_df[target_col]
    X_test = test_df[feature_cols]
    y_test = test_df[target_col]

    # previous_close at time t (for DA and naive baseline):
    # close[t] is in the same row as target[t] = close[t+1]
    previous_close_test = test_df["close"].values

    logger.info(
        "Features: %s  |  Train=%d  Val=%d  Test=%d",
        feature_cols, len(X_train), len(X_val), len(X_test),
    )

    # ------------------------------------------------------------------
    # 5. Train model
    # ------------------------------------------------------------------
    trained_model: Any = None
    params_logged: Dict[str, Any] = {}
    preds: np.ndarray | None = None
    base_params: Dict[str, Any] = {
        "ticker": loader.ticker_id,
        "resolution": args.resolution,
        "target_mode": target_mode,
        "target_horizon": target_horizon,
        "train_ratio": train_ratio,
        "validation_ratio": validation_ratio,
    }
    base_params.update(_dataset_tracking_params(dataset_contract))

    if args.model == "arima":
        # ARIMA is univariate — fits directly on close prices
        arima = ARIMABaseline(p=2, d=1, q=2)
        arima.fit(train_df["close"])
        trained_model = arima
        params_logged = {"p": 2, "d": 1, "q": 2}

        # Forecast steps = len(test_df)
        preds = np.array(arima.predict(steps=len(test_df)))

    elif args.model == "xgboost":
        if args.tune:
            logger.info("Starting Optuna hyperparameter optimization...")
            study = optuna.create_study(direction="minimize")
            study.optimize(
                lambda trial: objective_optuna(
                    trial,
                    X_train.values, y_train.values,
                    X_val.values, y_val.values,
                ),
                n_trials=10,
            )
            logger.info("Best trial params: %s", study.best_params)
            params_logged = study.best_params
        else:
            params_logged = {
                "n_estimators": 100,
                "max_depth": 5,
                "learning_rate": 0.05,
            }

        xgb_wrapper = XGBoostModelWrapper(params=params_logged)
        xgb_wrapper.fit(X_train, y_train)
        trained_model = xgb_wrapper.model
        preds = xgb_wrapper.predict(X_test)

    elif args.model == "random_forest":
        if args.tune:
            logger.info("Optuna tuning not yet implemented for Random Forest. Using defaults.")

        params_logged = {
            "n_estimators": 200,
            "max_depth": 10,
            "min_samples_split": 5,
            "min_samples_leaf": 2,
            "random_state": RANDOM_SEED,
        }

        rf_wrapper = RandomForestModelWrapper(params=params_logged)
        rf_wrapper.fit(X_train, y_train)
        trained_model = rf_wrapper.model
        preds = rf_wrapper.predict(X_test)

    elif args.model in ("gru", "lstm"):
        # TODO: Implement full PyTorch training loop.
        # Requires: TimeSeriesDataset, DataLoader, train/eval loop,
        # scaler (fit on train only), create_sequences(), early stopping.
        # See models/nn_models.py for GRUForecaster and create_sequences().
        raise NotImplementedError(
            f"{args.model.upper()} training loop is not yet implemented. "
            f"See services/training/models/nn_models.py for the model class "
            f"and create_sequences() helper. Contributions welcome!"
        )

    # ------------------------------------------------------------------
    # 6. Evaluate
    # ------------------------------------------------------------------
    if preds is not None:
        metrics = evaluate_predictions(
            y_true=y_test.values,
            y_pred=preds,
            previous_close=previous_close_test,
        )
        metrics = add_improvement_vs_naive(metrics)
    else:
        logger.error("No predictions generated — skipping evaluation.")
        return

    # ------------------------------------------------------------------
    # 7. Log results to MLflow
    # ------------------------------------------------------------------
    # Sanitize ticker for MLflow naming (/ is not allowed)
    ticker_safe = loader.ticker_id.replace("/", "-")

    params_logged = {**base_params, **params_logged}

    run_id = log_experiment_run(
        experiment_name=f"{ticker_safe}_Forecast",
        run_name=f"{args.model}_run",
        params=params_logged,
        metrics=metrics,
        model=trained_model,
        model_name_in_registry=f"{ticker_safe}_{args.model}",
    )

    logger.info("Training pipeline finished successfully! MLflow Run ID: %s", run_id)


if __name__ == "__main__":
    run_pipeline()
