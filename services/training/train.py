import argparse
import logging
import numpy as np
import optuna
from shared.utils.logging import setup_logging
from data_loader import DataLoader
from models.arima_model import ARIMABaseline
from models.xgboost_model import XGBoostModelWrapper
from evaluate import evaluate_predictions
from mlflow_utils import log_experiment_run

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Stock and Crypto Training Pipeline")
    parser.add_argument(
        "--ticker", type=str, default="BTC/USDT", help="Ticker ID to train on"
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["arima", "xgboost", "lstm", "gru"],
        default="xgboost",
        help="Algorithm to train",
    )
    parser.add_argument(
        "--resolution", type=str, default="1d", help="Resolution: 1h or 1d"
    )
    parser.add_argument(
        "--tune", action="store_true", help="Perform hyperparameter tuning with Optuna"
    )
    return parser.parse_args()


def objective_optuna(trial: optuna.Trial, X_train, y_train, X_val, y_val) -> float:
    """Optuna objective function for tuning XGBoost parameters."""
    # TODO: Define search space
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 50, 200),
        "max_depth": trial.suggest_int("max_depth", 3, 9),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
    }

    # Train
    model = XGBoostModelWrapper(params=params)
    model.fit(X_train, y_train)

    # Predict
    preds = model.predict(X_val)

    # Evaluate MAE
    mae = np.mean(np.abs(y_val.values - preds))
    return float(mae)


def run_pipeline():
    args = parse_args()
    logger.info(f"Running pipeline for {args.ticker} using {args.model} model")

    # 1. Load Data
    loader = DataLoader(ticker_id=args.ticker, resolution=args.resolution)
    raw_df = loader.load_raw_data(limit=1000)

    if raw_df.empty:
        logger.error(
            f"No historical prices found for {args.ticker}. Please seed database or run ingestion first."
        )
        return

    # 2. Feature Engineering
    features_df = loader.engineer_features(raw_df)
    loader.save_features_to_db(features_df)

    # 3. Train Test Split
    train_df, test_df = loader.prepare_train_test_split(features_df)

    # Define targets and features
    feature_cols = ["returns", "volatility", "rsi", "macd", "macd_signal"]
    target_col = "close"

    # Settle features & labels (For XGBoost/ML baseline)
    # We predict next day's close price, so target is close shifted by -1
    train_df["target"] = train_df[target_col].shift(-1)
    test_df["target"] = test_df[target_col].shift(-1)

    train_df = train_df.dropna()
    test_df = test_df.dropna()

    X_train, y_train = train_df[feature_cols], train_df["target"]
    X_test, y_test = test_df[feature_cols], test_df["target"]

    # 4. Training & Optuna Tuning
    trained_model = None
    params_logged = {}

    if args.model == "arima":
        # ARIMA is univariate, fits directly on prices
        arima = ARIMABaseline(p=2, d=1, q=2)
        arima.fit(train_df[target_col])
        trained_model = arima
        params_logged = {"p": 2, "d": 1, "q": 2}

        # Evaluate
        preds = arima.predict(steps=len(test_df))
        metrics = evaluate_predictions(test_df[target_col].values, preds)

    elif args.model == "xgboost":
        if args.tune:
            logger.info("Starting Optuna hyperparameter optimization...")
            # Sequential split for Optuna train/val validation
            X_tr, X_val = (
                X_train.iloc[: int(len(X_train) * 0.8)],
                X_train.iloc[int(len(X_train) * 0.8) :],
            )
            y_tr, y_val = (
                y_train.iloc[: int(len(y_train) * 0.8)],
                y_train.iloc[int(len(y_train) * 0.8) :],
            )

            study = optuna.create_study(direction="minimize")
            study.optimize(
                lambda trial: objective_optuna(trial, X_tr, y_tr, X_val, y_val),
                n_trials=10,
            )
            logger.info(f"Best trial params: {study.best_params}")
            params_logged = study.best_params
        else:
            params_logged = {"n_estimators": 100, "max_depth": 5, "learning_rate": 0.05}

        xgb_wrapper = XGBoostModelWrapper(params=params_logged)
        xgb_wrapper.fit(X_train, y_train)
        trained_model = xgb_wrapper.model

        # Evaluate
        preds = xgb_wrapper.predict(X_test)
        metrics = evaluate_predictions(y_test.values, preds)

    elif args.model in ("lstm", "gru"):
        # TODO: Implement sequence shaping, PyTorch Dataset, PyTorch training loop
        logger.info(
            f"PyTorch deep learning model {args.model} placeholder training execution."
        )
        # For boilerplate, we'll log a mock run
        metrics = {"mae": 1.25, "rmse": 1.75, "mape": 0.015}
        params_logged = {"epochs": 10, "batch_size": 32, "lr": 0.001}
        # Create a mock neural net class to log
        from models.nn_models import LSTMForecaster

        trained_model = LSTMForecaster(
            input_dim=len(feature_cols), hidden_dim=64, num_layers=2
        )

    # 5. Log results and save model in MLflow Registry
    run_id = log_experiment_run(
        experiment_name=f"{args.ticker.replace('/', '-')}_Forecast",
        run_name=f"{args.model}_run",
        params=params_logged,
        metrics=metrics,
        model=trained_model,
        model_name_in_registry=f"{args.ticker.replace('/', '-')}_{args.model}",
    )

    logger.info(f"Training pipeline finished successfully! MLflow Run ID: {run_id}")


if __name__ == "__main__":
    run_pipeline()
