"""Live feature engineering for inference.

Mirrors the training-time feature pipelines so that a model served from the
MLflow Registry receives inputs with the exact column names, order, and
formulas it was trained on:

- XGBoost: services/training/models/xgboost_features.py (19 features)
- Random Forest: services/training/models/random_forest_features.py (18 features)

The training builders cannot be reused directly for live data because they
require ``next_close``/``split`` columns and drop the newest bar (whose target
is still unknown). These builders operate on a plain OHLCV frame instead and
keep the newest row. Parity with the training formulas is enforced by
``services/inference/tests/test_features.py``.
"""

from __future__ import annotations

import pandas as pd

from shared.utils.metrics import (
    calculate_macd,
    calculate_returns,
    calculate_rsi,
    calculate_volatility,
)

OHLCV_COLUMNS: tuple[str, ...] = ("ts", "open", "high", "low", "close", "volume")

# Same ordered registry as services/training/models/xgboost_features.FEATURE_LIST
XGBOOST_FEATURE_LIST: list[str] = [
    "returns",
    "volatility",
    "rsi",
    "macd",
    "macd_signal",
    "close_lag_1",
    "close_lag_3",
    "close_lag_5",
    "close_lag_10",
    "close_lag_20",
    "rolling_mean_5",
    "rolling_mean_10",
    "rolling_mean_20",
    "rolling_std_5",
    "rolling_std_20",
    "rolling_min_10",
    "rolling_max_10",
    "bollinger_band_width_20",
    "atr_14",
]

# Same ordered registry as services/training/models/random_forest_features.FEATURE_LIST
RANDOM_FOREST_FEATURE_LIST: list[str] = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "return_1",
    "volume_return_1",
    "close_lag_1",
    "close_lag_3",
    "close_lag_5",
    "close_lag_10",
    "close_lag_20",
    "rolling_mean_5",
    "rolling_mean_10",
    "rolling_mean_20",
    "rolling_std_5",
    "rolling_std_10",
    "rolling_std_20",
]

# close_lag_20 is the binding constraint; EWM indicators (RSI/MACD) need a
# longer warm-up before they converge to the training-time values.
MIN_HISTORY_ROWS = 21


def _validate_ohlcv(df: pd.DataFrame) -> None:
    """Require a chronological OHLCV frame with enough rows for all lags."""
    missing = set(OHLCV_COLUMNS).difference(df.columns)
    if missing:
        raise ValueError(f"OHLCV frame is missing columns: {sorted(missing)}.")
    if len(df) < MIN_HISTORY_ROWS:
        raise ValueError(
            f"Need at least {MIN_HISTORY_ROWS} OHLCV rows to build features, "
            f"got {len(df)}."
        )
    if not df["ts"].is_monotonic_increasing:
        raise ValueError("OHLCV frame must be sorted by ts ascending.")


def build_xgboost_live_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the 19 XGBoost features on a live OHLCV frame.

    Input: frame with OHLCV_COLUMNS sorted by ts ascending.
    Output: copy of the frame with the 19 feature columns appended; the last
    row is fully populated when enough history is provided.
    """
    _validate_ohlcv(df)
    featured = df.reset_index(drop=True).copy()

    featured["returns"] = calculate_returns(featured["close"])
    featured["volatility"] = calculate_volatility(featured["returns"], window=14)
    featured["rsi"] = calculate_rsi(featured["close"], period=14)
    macd_line, signal_line = calculate_macd(
        featured["close"], fast=12, slow=26, signal=9
    )
    featured["macd"] = macd_line
    featured["macd_signal"] = signal_line

    for period in (1, 3, 5, 10, 20):
        featured[f"close_lag_{period}"] = featured["close"].shift(period)
    for window in (5, 10, 20):
        featured[f"rolling_mean_{window}"] = featured["close"].rolling(window).mean()
    for window in (5, 20):
        featured[f"rolling_std_{window}"] = featured["close"].rolling(window).std()
    featured["rolling_min_10"] = featured["close"].rolling(10).min()
    featured["rolling_max_10"] = featured["close"].rolling(10).max()

    middle_band = featured["close"].rolling(20).mean()
    rolling_std = featured["close"].rolling(20).std()
    upper_band = middle_band + 2.0 * rolling_std
    lower_band = middle_band - 2.0 * rolling_std
    width = (upper_band - lower_band) / middle_band
    featured["bollinger_band_width_20"] = width.where(middle_band.ne(0.0))

    previous_close = featured["close"].shift(1)
    true_range = pd.concat(
        [
            featured["high"] - featured["low"],
            (featured["high"] - previous_close).abs(),
            (featured["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    featured["atr_14"] = true_range.rolling(14).mean()

    return featured


def build_random_forest_live_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the 18 Random Forest features on a live OHLCV frame."""
    _validate_ohlcv(df)
    featured = df.reset_index(drop=True).copy()

    featured["return_1"] = featured["close"].pct_change(fill_method=None)
    featured["volume_return_1"] = featured["volume"].pct_change(fill_method=None)
    for period in (1, 3, 5, 10, 20):
        featured[f"close_lag_{period}"] = featured["close"].shift(period)
    for window in (5, 10, 20):
        featured[f"rolling_mean_{window}"] = featured["close"].rolling(window).mean()
        featured[f"rolling_std_{window}"] = featured["close"].rolling(window).std()

    return featured


def latest_feature_row(featured: pd.DataFrame, feature_list: list[str]) -> pd.DataFrame:
    """Return the newest row as a one-row frame with feature columns in order.

    Raises when any feature on that row is missing — the caller did not
    provide enough history.
    """
    row = featured.iloc[[-1]][feature_list]
    if row.isna().any(axis=None):
        missing = [name for name in feature_list if pd.isna(row.iloc[0][name])]
        raise ValueError(
            f"Not enough history to compute features: {missing} are NaN "
            "on the latest bar."
        )
    return row.reset_index(drop=True)
