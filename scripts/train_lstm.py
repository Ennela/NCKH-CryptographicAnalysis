import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import MinMaxScaler
from torch import nn, optim
from torch.utils.data import DataLoader, TensorDataset

from shared.utils.logging import setup_logging

# Ensure repo root is importable when running from scripts/ directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.training.dataset_contract import (
    get_split_config,
    get_timeframe_contract,
    load_dataset_contract,
    normalize_ticker,
    validate_row_count,
)
from services.training.data_loader import DataLoader as OhlcvDataLoader
from services.training.mlflow_utils import init_mlflow
from services.training.models.nn_models import LSTMForecaster, create_sequences

MODELS_DIR = REPO_ROOT / "services" / "training" / "models"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an LSTM close-price forecasting model.")
    parser.add_argument(
        "--ticker",
        type=str,
        default="BTCUSDT",
        help="Ticker symbol to train on (e.g. BTCUSDT, FPT).",
    )
    parser.add_argument(
        "--resolution",
        type=str,
        default="1d",
        choices=["1d", "1h"],
        help="Timeframe to use for training.",
    )
    parser.add_argument(
        "--dataset-config",
        type=str,
        default="configs/group_dataset.json",
        help="Dataset contract JSON file.",
    )
    parser.add_argument(
        "--sequence-length",
        type=int,
        default=30,
        help="Number of past steps used as input for each prediction.",
    )
    parser.add_argument(
        "--hidden-dim",
        type=int,
        default=64,
        help="Hidden dimension size for the LSTM.",
    )
    parser.add_argument(
        "--num-layers",
        type=int,
        default=2,
        help="Number of LSTM layers.",
    )
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.2,
        help="Dropout probability applied between LSTM layers.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for training.",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=1e-3,
        help="Learning rate for Adam optimizer.",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Number of training epochs.",
    )
    parser.add_argument(
        "--allow-custom-data",
        action="store_true",
        help="Allow running without the shared dataset contract for custom data.",
    )
    return parser.parse_args()


def configure_logger() -> logging.Logger:
    setup_logging()
    return logging.getLogger(__name__)


def load_contract_or_exit(args: argparse.Namespace, logger: logging.Logger) -> dict[str, Any] | None:
    dataset_config_path = None if args.dataset_config.lower() == "none" else args.dataset_config
    contract = load_dataset_contract(dataset_config_path)
    if contract is None:
        if not args.allow_custom_data:
            logger.error(
                "Dataset contract is disabled. Use --allow-custom-data to run on custom data."
            )
            sys.exit(1)
        logger.warning(
            "Running without dataset contract. Results will NOT be valid for official reports."
        )
        return None
    return contract


def split_by_time(df: pd.DataFrame, train_ratio: float, validation_ratio: float):
    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + validation_ratio))
    return (
        df.iloc[:train_end].reset_index(drop=True),
        df.iloc[train_end:val_end].reset_index(drop=True),
        df.iloc[val_end:].reset_index(drop=True),
    )


def build_dataset(series: pd.Series, sequence_length: int):
    values = series.astype(float).to_numpy()
    if len(values) <= sequence_length:
        return np.empty((0, sequence_length, 1), dtype=float), np.empty((0,), dtype=float)

    features = values.reshape(-1, 1)
    X, y = create_sequences(features, values, sequence_length)
    return X.astype(np.float32), y.astype(np.float32)


def build_loader(dataset: TensorDataset, batch_size: int, shuffle: bool = False):
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, drop_last=False)

def evaluate_model(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    scaler: MinMaxScaler,
) -> tuple[float, float, float, np.ndarray, np.ndarray]:
    model.eval()
    predictions: list[np.ndarray] = []
    truths: list[np.ndarray] = []

    with torch.no_grad():
        for X_batch, y_batch in loader:
            X_batch = X_batch.to(device)
            y_pred = model(X_batch).squeeze(-1).cpu().numpy()
            predictions.append(y_pred)
            truths.append(y_batch.numpy())

    if not predictions:
        raise ValueError("No data available for evaluation.")

    y_pred = np.concatenate(predictions, axis=0)
    y_true = np.concatenate(truths, axis=0)

    y_pred_inv = scaler.inverse_transform(y_pred.reshape(-1, 1)).reshape(-1)
    y_true_inv = scaler.inverse_transform(y_true.reshape(-1, 1)).reshape(-1)

    mse = float(np.mean((y_true_inv - y_pred_inv) ** 2))
    mae = float(np.mean(np.abs(y_true_inv - y_pred_inv)))
    rmse = float(np.sqrt(mse))
    return mse, mae, rmse, y_true_inv, y_pred_inv


def save_model_state(model: nn.Module, ticker: str, resolution: str) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"lstm_{ticker}_{resolution}_{timestamp}.pt"
    path = MODELS_DIR / filename
    torch.save(model.state_dict(), path)
    return path


def main() -> None:
    args = parse_args()
    logger = configure_logger()
    init_mlflow()

    contract = load_contract_or_exit(args, logger)
    if contract is not None:
        timeframe_contract = get_timeframe_contract(contract, normalize_ticker(args.ticker), args.resolution)
        logger.info(
            "Using dataset contract %s for %s %s",
            contract["dataset_version"],
            args.ticker,
            args.resolution,
        )
    else:
        timeframe_contract = None

    loader = OhlcvDataLoader(ticker_id=args.ticker, resolution=args.resolution)
    raw_df = loader.load_raw_data(
        start_ts=timeframe_contract.get("start_ts") if timeframe_contract else None,
        end_ts=timeframe_contract.get("end_ts") if timeframe_contract else None,
    )

    if raw_df.empty:
        logger.error("No OHLCV data found for %s %s", args.ticker, args.resolution)
        sys.exit(1)

    if contract is not None:
        validate_row_count(contract, normalize_ticker(args.ticker), args.resolution, len(raw_df))

    train_ratio, validation_ratio = get_split_config(contract)
    train_df, val_df, test_df = split_by_time(raw_df, train_ratio, validation_ratio)
    logger.info(
        "Split sizes: train=%d val=%d test=%d", len(train_df), len(val_df), len(test_df)
    )

    if len(test_df) <= args.sequence_length:
        logger.error(
            "Test partition is too small for sequence length %d. "
            "Please reduce --sequence-length or load more data.",
            args.sequence_length,
        )
        sys.exit(1)

    scaler = MinMaxScaler(feature_range=(0.0, 1.0))
    train_close = train_df["close"].astype(float).to_numpy().reshape(-1, 1)
    scaler.fit(train_close)

    X_train, y_train = build_dataset(pd.Series(train_close.flatten()), args.sequence_length)
    X_val, y_val = build_dataset(pd.Series(val_df["close"].astype(float).to_numpy()), args.sequence_length)
    X_test, y_test = build_dataset(pd.Series(test_df["close"].astype(float).to_numpy()), args.sequence_length)

    if X_train.size == 0 or X_val.size == 0 or X_test.size == 0:
        logger.error("One of the partitions has insufficient sequence data. Cannot train.")
        sys.exit(1)

    scaler = MinMaxScaler(feature_range=(0.0, 1.0))
    scaled_train_close = scaler.fit_transform(train_close)
    train_series_scaled = pd.Series(scaled_train_close.flatten())
    X_train, y_train = build_dataset(train_series_scaled, args.sequence_length)

    val_close = val_df["close"].astype(float).to_numpy().reshape(-1, 1)
    X_val, y_val = build_dataset(pd.Series(scaler.transform(val_close).flatten()), args.sequence_length)

    test_close = test_df["close"].astype(float).to_numpy().reshape(-1, 1)
    X_test, y_test = build_dataset(pd.Series(scaler.transform(test_close).flatten()), args.sequence_length)

    train_dataset = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    val_dataset = TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val))
    test_dataset = TensorDataset(torch.from_numpy(X_test), torch.from_numpy(y_test))

    train_loader = build_loader(train_dataset, args.batch_size, shuffle=False)
    val_loader = build_loader(val_dataset, args.batch_size, shuffle=False)
    test_loader = build_loader(test_dataset, args.batch_size, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = LSTMForecaster(
        input_dim=1,
        hidden_dim=args.hidden_dim,
        num_layers=args.num_layers,
        output_dim=1,
        dropout=args.dropout,
    ).to(device)

    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=args.learning_rate)

    experiment_name = f"{normalize_ticker(args.ticker)}_LSTM"
    run_name = f"lstm_{normalize_ticker(args.ticker)}_{args.resolution}"
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name=run_name) as run:
        params = {
            "ticker": normalize_ticker(args.ticker),
            "resolution": args.resolution,
            "sequence_length": args.sequence_length,
            "hidden_dim": args.hidden_dim,
            "num_layers": args.num_layers,
            "dropout": args.dropout,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "epochs": args.epochs,
            "train_ratio": train_ratio,
            "validation_ratio": validation_ratio,
        }
        mlflow.log_params(params)

        for epoch in range(1, args.epochs + 1):
            model.train()
            total_loss = 0.0
            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(device)
                y_batch = y_batch.to(device)
                optimizer.zero_grad()
                y_pred = model(X_batch).squeeze(-1)
                loss = criterion(y_pred, y_batch)
                loss.backward()
                optimizer.step()
                total_loss += loss.item() * X_batch.size(0)

            train_loss = total_loss / len(train_loader.dataset)
            train_rmse = float(np.sqrt(train_loss))
            train_mae = float(
                torch.mean(torch.abs(model(torch.from_numpy(X_train).to(device)).squeeze(-1) - torch.from_numpy(y_train).to(device))).item()
            )

            val_mse, val_mae, val_rmse, _, _ = evaluate_model(model, val_loader, device, scaler)
            epoch_metrics = {
                "epoch_train_mse": train_loss,
                "epoch_train_mae": train_mae,
                "epoch_train_rmse": train_rmse,
                "epoch_val_mse": val_mse,
                "epoch_val_mae": val_mae,
                "epoch_val_rmse": val_rmse,
            }
            mlflow.log_metrics(epoch_metrics, step=epoch)
            logger.info(
                "Epoch %d: train_mse=%.6f val_mse=%.6f val_mae=%.6f val_rmse=%.6f",
                epoch,
                train_loss,
                val_mse,
                val_mae,
                val_rmse,
            )

        test_mse, test_mae, test_rmse, y_true_inv, y_pred_inv = evaluate_model(
            model, test_loader, device, scaler
        )
        final_metrics = {
            "test_mse": test_mse,
            "test_mae": test_mae,
            "test_rmse": test_rmse,
        }
        mlflow.log_metrics(final_metrics)
        logger.info(
            "Test results: mse=%.6f mae=%.6f rmse=%.6f",
            test_mse,
            test_mae,
            test_rmse,
        )

        model_path = "model.pth"
        torch.save(model.state_dict(), model_path)
        mlflow.log_artifact(model_path, artifact_path="model")
        os.remove(model_path)

        model_file = save_model_state(model, normalize_ticker(args.ticker), args.resolution)
        logger.info("Saved model weights to %s", model_file)
        logger.info("MLflow run completed: %s", run.info.run_id)

    logger.info(
        "Training finished. Model artifact and metrics logged to MLflow."
    )


if __name__ == "__main__":
    main()
