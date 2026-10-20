"""Pure pandas helpers behind the data-analytics endpoints.

Kept free of FastAPI/DB code so the formulas can be unit-tested directly.

- ``compute_indicators``: SMA 20/50, RSI 14 and MACD (12, 26, 9) over a
  chronological OHLCV frame. RSI/MACD reuse ``shared.utils.metrics`` so the
  values shown on the dashboard match the features the models were trained on.
- ``profile_quality``: completeness and anomaly counts of one symbol's
  history, using the same IQR rule (k = 1.5) as the ingestion cleaning
  pipeline (services/ingestion/app/cleaning.py::detect_outliers).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from shared.utils.metrics import calculate_macd, calculate_rsi

# Extra bars loaded before the requested window so SMA 50 and the EWM-based
# RSI/MACD are warmed up on the first displayed bar.
INDICATOR_WARMUP_BARS = 60
IQR_MULTIPLIER = 1.5
MIN_ROWS_FOR_IQR = 10

INDICATOR_COLUMNS: tuple[str, ...] = (
    "sma_20",
    "sma_50",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
)


def compute_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Append technical indicator columns to a chronological OHLCV frame.

    Input: frame with ``close`` sorted by ``ts`` ascending.
    Output: copy with INDICATOR_COLUMNS added; rows inside each indicator's
    warm-up window hold NaN (rolling windows are trailing — no look-ahead).
    """
    result = frame.reset_index(drop=True).copy()
    close = result["close"].astype(float)
    result["sma_20"] = close.rolling(window=20).mean()
    result["sma_50"] = close.rolling(window=50).mean()
    rsi = calculate_rsi(close, period=14)
    # The EWM-based RSI has values from bar 1 but is unstable before one period.
    rsi.iloc[:14] = np.nan
    result["rsi_14"] = rsi
    macd_line, signal_line = calculate_macd(close, fast=12, slow=26, signal=9)
    result["macd"] = macd_line
    result["macd_signal"] = signal_line
    result["macd_hist"] = macd_line - signal_line
    # EWM series have values from bar 0 but are not meaningful before the slow span.
    result.loc[:25, ["macd", "macd_signal", "macd_hist"]] = np.nan
    return result


def expected_bar_count(
    first_ts: pd.Timestamp, last_ts: pd.Timestamp, asset_class: str, timeframe: str
) -> int:
    """Number of bars a complete series would have between two timestamps.

    Stocks trade Monday–Friday (Vietnamese public holidays are not modelled,
    so they show up as missing bars); crypto trades every day, every hour.
    """
    if timeframe == "1h":
        return int((last_ts - first_ts) / pd.Timedelta(hours=1)) + 1
    if asset_class == "stock":
        return len(pd.bdate_range(first_ts.normalize(), last_ts.normalize()))
    return (last_ts.normalize() - first_ts.normalize()).days + 1


def _iqr_outlier_count(values: pd.Series) -> int:
    """Count values outside [Q1 - k·IQR, Q3 + k·IQR] (same rule as cleaning.py)."""
    clean = values.dropna().astype(float)
    if len(clean) < MIN_ROWS_FOR_IQR:
        return 0
    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - IQR_MULTIPLIER * iqr, q3 + IQR_MULTIPLIER * iqr
    return int(((clean < lower) | (clean > upper)).sum())


@dataclass
class QualityProfile:
    """Measured data quality of one symbol/timeframe series."""

    bars: int
    first_ts: pd.Timestamp | None
    last_ts: pd.Timestamp | None
    expected_bars: int
    missing_bars: int
    completeness_pct: float
    zero_volume_bars: int
    invalid_ohlc_bars: int
    return_outliers: int
    volume_outliers: int


def profile_quality(
    frame: pd.DataFrame, asset_class: str, timeframe: str
) -> QualityProfile:
    """Measure completeness and anomalies of a chronological OHLCV frame.

    Outliers are counted on bar-to-bar returns rather than price levels: over a
    multi-year history a trending price would make the level-based IQR flag
    whole regimes, while return outliers isolate genuine spikes.
    """
    if frame.empty:
        return QualityProfile(0, None, None, 0, 0, 0.0, 0, 0, 0, 0)

    first_ts, last_ts = frame["ts"].iloc[0], frame["ts"].iloc[-1]
    bars = len(frame)
    expected = max(expected_bar_count(first_ts, last_ts, asset_class, timeframe), bars)
    body_low = frame[["open", "close"]].min(axis=1)
    body_high = frame[["open", "close"]].max(axis=1)
    invalid = (frame["low"] > body_low) | (frame["high"] < body_high)

    return QualityProfile(
        bars=bars,
        first_ts=first_ts,
        last_ts=last_ts,
        expected_bars=expected,
        missing_bars=expected - bars,
        completeness_pct=round(100.0 * bars / expected, 2),
        zero_volume_bars=int((frame["volume"] == 0).sum()),
        invalid_ohlc_bars=int(invalid.sum()),
        return_outliers=_iqr_outlier_count(frame["close"].pct_change()),
        volume_outliers=_iqr_outlier_count(frame["volume"]),
    )
