import argparse
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

from shared.utils.logging import setup_logging

# Ensure repo root is on sys.path when running from scripts/ directly
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.training.data_loader import DataLoader
from services.training.dataset_contract import (
    get_split_config,
    get_timeframe_contract,
    load_dataset_contract,
    normalize_ticker,
    validate_row_count,
)


RESULTS_DIR = Path("results")
DEFAULT_RESULTS_PATH = RESULTS_DIR / "arima_baseline_results.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ARIMA and naive baselines over market OHLCV data."
    )
    parser.add_argument(
        "--dataset-config",
        type=str,
        default="configs/group_dataset.json",
        help="Path to dataset contract JSON.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_RESULTS_PATH),
        help="Destination CSV file for metrics.",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help=(
            "Optional comma-separated list of tickers to evaluate. "
            "Defaults to all symbols defined in the dataset contract."
        ),
    )
    parser.add_argument(
        "--timeframes",
        type=str,
        default="",
        help=(
            "Optional comma-separated list of timeframes to evaluate. "
            "Defaults to all timeframes defined in the dataset contract."
        ),
    )
    return parser.parse_args()


def configure_logger() -> logging.Logger:
    setup_logging()
    return logging.getLogger(__name__)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.shape != y_pred.shape:
        raise ValueError("Actual and predicted arrays must have the same shape.")

    mse = float(np.mean(np.square(y_true - y_pred)))
    mae = float(np.mean(np.abs(y_true - y_pred)))

    mask = y_true != 0.0
    if np.any(mask):
        mape = float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])))
    else:
        mape = float(np.mean(np.abs(y_true - y_pred))) if y_true.size > 0 else 0.0

    return {"mse": mse, "mae": mae, "mape": mape}


def build_symbol_timeframe_pairs(
    contract: dict[str, Any],
    symbol_filter: str,
    timeframe_filter: str,
) -> list[tuple[str, str]]:
    symbols = [item.strip().upper() for item in symbol_filter.split(",") if item.strip()]
    timeframes = [item.strip() for item in timeframe_filter.split(",") if item.strip()]

    pairs: list[tuple[str, str]] = []
    for asset_config in contract["assets"].values():
        for symbol in asset_config["symbols"]:
            normalized_symbol = normalize_ticker(symbol)
            for timeframe in asset_config["timeframes"]:
                if symbols and normalized_symbol not in symbols:
                    continue
                if timeframes and timeframe not in timeframes:
                    continue
                pairs.append((normalized_symbol, timeframe))

    if not pairs:
        raise ValueError(
            "No symbol/timeframe pairs found for the given contract filters. "
            "Check --symbols and --timeframes values."
        )
    return pairs


def train_test_split_by_time(
    df: pd.DataFrame, train_ratio: float, validation_ratio: float
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + validation_ratio))

    train_df = df.iloc[:train_end].reset_index(drop=True)
    val_df = df.iloc[train_end:val_end].reset_index(drop=True)
    test_df = df.iloc[val_end:].reset_index(drop=True)
    return train_df, val_df, test_df


def fit_arima_forecast(train_close: pd.Series, forecast_steps: int) -> np.ndarray:
    if len(train_close) < 10:
        raise ValueError("Not enough training samples to fit ARIMA reliably.")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        model = ARIMA(
            train_close,
            order=(1, 1, 1),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fitted = model.fit()

    forecast = fitted.forecast(steps=forecast_steps)
    return np.asarray(forecast, dtype=float)


def build_naive_forecast(train_close: pd.Series, test_close: pd.Series) -> np.ndarray:
    if len(test_close) == 0:
        return np.array([], dtype=float)

    predictions = np.empty(len(test_close), dtype=float)
    predictions[0] = float(train_close.iloc[-1])
    if len(test_close) > 1:
        predictions[1:] = test_close.iloc[:-1].astype(float).values
    return predictions


def load_contract() -> dict[str, Any]:
    contract = load_dataset_contract("configs/group_dataset.json")
    if contract is None:
        raise ValueError("Dataset contract not found or invalid.")
    return contract


def run_baseline_for_pair(
    ticker: str,
    timeframe: str,
    dataset_contract: dict[str, Any],
    train_ratio: float,
    validation_ratio: float,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    logger.info("Evaluating %s %s", ticker, timeframe)
    timeframe_contract = get_timeframe_contract(dataset_contract, ticker, timeframe)

    loader = DataLoader(ticker_id=ticker, resolution=timeframe)
    raw_df = loader.load_raw_data(
        start_ts=timeframe_contract.get("start_ts"),
        end_ts=timeframe_contract.get("end_ts"),
    )

    if raw_df.empty:
        logger.warning("No OHLCV rows found for %s %s; skipping.", ticker, timeframe)
        return []

    validate_row_count(dataset_contract, ticker, timeframe, len(raw_df))

    train_df, val_df, test_df = train_test_split_by_time(
        raw_df, train_ratio=train_ratio, validation_ratio=validation_ratio
    )
    logger.info(
        "Split sizes for %s %s: train=%d val=%d test=%d",
        ticker,
        timeframe,
        len(train_df),
        len(val_df),
        len(test_df),
    )

    if len(test_df) < 5:
        logger.warning(
            "Test partition too small for %s %s (rows=%d); skipping.",
            ticker,
            timeframe,
            len(test_df),
        )
        return []

    test_close = test_df["close"].astype(float)
    results: list[dict[str, Any]] = []

    try:
        arima_pred = fit_arima_forecast(train_df["close"].astype(float), len(test_df))
        arima_metrics = compute_metrics(test_close.values, arima_pred)
        results.append(
            {
                "symbol": ticker,
                "timeframe": timeframe,
                "model_type": "arima",
                **arima_metrics,
            }
        )
        logger.info(
            "ARIMA %s %s -> mse=%.4f mae=%.4f mape=%.4f",
            ticker,
            timeframe,
            arima_metrics["mse"],
            arima_metrics["mae"],
            arima_metrics["mape"],
        )
    except Exception as exc:
        logger.warning(
            "ARIMA training failed for %s %s: %s. Skipping ARIMA metrics.",
            ticker,
            timeframe,
            exc,
        )

    try:
        naive_pred = build_naive_forecast(train_df["close"].astype(float), test_close)
        naive_metrics = compute_metrics(test_close.values, naive_pred)
        results.append(
            {
                "symbol": ticker,
                "timeframe": timeframe,
                "model_type": "naive",
                **naive_metrics,
            }
        )
        logger.info(
            "Naive %s %s -> mse=%.4f mae=%.4f mape=%.4f",
            ticker,
            timeframe,
            naive_metrics["mse"],
            naive_metrics["mae"],
            naive_metrics["mape"],
        )
    except Exception as exc:
        logger.warning(
            "Naive baseline failed for %s %s: %s.",
            ticker,
            timeframe,
            exc,
        )

    return results


def main() -> None:
    args = parse_args()
    logger = configure_logger()

    contract = load_dataset_contract(args.dataset_config)
    if contract is None:
        raise ValueError(f"Could not load dataset contract from {args.dataset_config}")

    train_ratio, validation_ratio = get_split_config(contract)
    pairs = build_symbol_timeframe_pairs(contract, args.symbols, args.timeframes)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output)

    rows: list[dict[str, Any]] = []
    for ticker, timeframe in pairs:
        rows.extend(
            run_baseline_for_pair(
                ticker=ticker,
                timeframe=timeframe,
                dataset_contract=contract,
                train_ratio=train_ratio,
                validation_ratio=validation_ratio,
                logger=logger,
            )
        )

    if not rows:
        logger.error("No baseline results were generated.")
        raise SystemExit(1)

    df = pd.DataFrame(rows)
    df = df[["symbol", "timeframe", "model_type", "mse", "mae", "mape"]]
    df.to_csv(output_path, index=False)
    logger.info("Saved baseline results to %s", output_path)


if __name__ == "__main__":
    main()
