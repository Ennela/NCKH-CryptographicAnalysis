"""Causal feature engineering for the XGBoost forecasting model."""

from __future__ import annotations

import pandas as pd

from shared.utils.metrics import (
    calculate_macd,
    calculate_returns,
    calculate_rsi,
    calculate_volatility,
)

DEFAULT_LAG_PERIODS: tuple[int, ...] = (1, 3, 5, 10, 20)
DEFAULT_ROLLING_MEAN_WINDOWS: tuple[int, ...] = (5, 10, 20)
DEFAULT_ROLLING_STD_WINDOWS: tuple[int, ...] = (5, 20)
DEFAULT_EXTREMA_WINDOW = 10
DEFAULT_VOLATILITY_WINDOW = 14
DEFAULT_RSI_PERIOD = 14
DEFAULT_MACD_FAST = 12
DEFAULT_MACD_SLOW = 26
DEFAULT_MACD_SIGNAL = 9
DEFAULT_BOLLINGER_WINDOW = 20
DEFAULT_BOLLINGER_STD_MULTIPLIER = 2.0
DEFAULT_ATR_WINDOW = 14

BASE_FEATURES: tuple[str, ...] = (
    "returns",
    "volatility",
    "rsi",
    "macd",
    "macd_signal",
)
SPLIT_NAMES: tuple[str, ...] = ("train", "val", "test")
REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {"ts", "open", "high", "low", "close", "volume", "next_close", "split"}
)


def _build_feature_names(
    lag_periods: tuple[int, ...],
    rolling_mean_windows: tuple[int, ...],
    rolling_std_windows: tuple[int, ...],
    extrema_window: int,
    bollinger_window: int,
    atr_window: int,
) -> list[str]:
    """Build the ordered feature registry for one window configuration."""
    return [
        *BASE_FEATURES,
        *(f"close_lag_{period}" for period in lag_periods),
        *(f"rolling_mean_{window}" for window in rolling_mean_windows),
        *(f"rolling_std_{window}" for window in rolling_std_windows),
        f"rolling_min_{extrema_window}",
        f"rolling_max_{extrema_window}",
        f"bollinger_band_width_{bollinger_window}",
        f"atr_{atr_window}",
    ]


# Registry for the public builder's default window configuration.
FEATURE_LIST: list[str] = _build_feature_names(
    DEFAULT_LAG_PERIODS,
    DEFAULT_ROLLING_MEAN_WINDOWS,
    DEFAULT_ROLLING_STD_WINDOWS,
    DEFAULT_EXTREMA_WINDOW,
    DEFAULT_BOLLINGER_WINDOW,
    DEFAULT_ATR_WINDOW,
)


def _validate_windows(name: str, windows: tuple[int, ...]) -> None:
    """Require a non-empty set of unique positive window lengths."""
    if not windows or any(
        not isinstance(window, int) or isinstance(window, bool) or window <= 0
        for window in windows
    ):
        raise ValueError(f"{name} must contain positive integers.")
    if len(set(windows)) != len(windows):
        raise ValueError(f"{name} must not contain duplicate values.")


def _validate_input(df: pd.DataFrame) -> None:
    """Validate the continuous loader output required by feature engineering."""
    missing_columns = REQUIRED_COLUMNS.difference(df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Input DataFrame is missing required columns: {missing}.")
    if df["split"].isna().any():
        raise ValueError("Input DataFrame contains missing split labels.")

    invalid_splits = set(df["split"].astype(str)).difference(SPLIT_NAMES)
    if invalid_splits:
        invalid = ", ".join(sorted(invalid_splits))
        raise ValueError(f"Input DataFrame contains invalid splits: {invalid}.")


def _calculate_bollinger_band_width(
    close: pd.Series,
    window: int,
    standard_deviation_multiplier: float,
) -> pd.Series:
    """Return normalized Bollinger Band width using current and past closes."""
    middle_band = close.rolling(window=window).mean()
    rolling_std = close.rolling(window=window).std()
    upper_band = middle_band + standard_deviation_multiplier * rolling_std
    lower_band = middle_band - standard_deviation_multiplier * rolling_std
    width = (upper_band - lower_band) / middle_band
    return width.where(middle_band.ne(0.0))


def _calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int,
) -> pd.Series:
    """Return Average True Range from current range and previous close."""
    previous_close = close.shift(1)
    true_range_components = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    )
    true_range = true_range_components.max(axis=1)
    return true_range.rolling(window=window).mean()


def _add_shared_indicators(
    df: pd.DataFrame,
    volatility_window: int,
    rsi_period: int,
    macd_fast: int,
    macd_slow: int,
    macd_signal: int,
) -> None:
    """Add indicators implemented in shared.utils.metrics in place."""
    df["returns"] = calculate_returns(df["close"])
    df["volatility"] = calculate_volatility(
        df["returns"],
        window=volatility_window,
    )
    df["rsi"] = calculate_rsi(df["close"], period=rsi_period)
    macd_line, signal_line = calculate_macd(
        df["close"],
        fast=macd_fast,
        slow=macd_slow,
        signal=macd_signal,
    )
    df["macd"] = macd_line
    df["macd_signal"] = signal_line


def _add_lag_and_rolling_features(
    df: pd.DataFrame,
    lag_periods: tuple[int, ...],
    rolling_mean_windows: tuple[int, ...],
    rolling_std_windows: tuple[int, ...],
    extrema_window: int,
) -> None:
    """Add close lags and causal rolling statistics in place."""
    for period in lag_periods:
        df[f"close_lag_{period}"] = df["close"].shift(period)
    for window in rolling_mean_windows:
        df[f"rolling_mean_{window}"] = df["close"].rolling(window=window).mean()
    for window in rolling_std_windows:
        df[f"rolling_std_{window}"] = df["close"].rolling(window=window).std()

    df[f"rolling_min_{extrema_window}"] = (
        df["close"].rolling(window=extrema_window).min()
    )
    df[f"rolling_max_{extrema_window}"] = (
        df["close"].rolling(window=extrema_window).max()
    )


def _validate_feature_parameters(
    lag_periods: tuple[int, ...],
    rolling_mean_windows: tuple[int, ...],
    rolling_std_windows: tuple[int, ...],
    scalar_windows: dict[str, int],
    macd_fast: int,
    macd_slow: int,
    bollinger_std_multiplier: float,
) -> None:
    """Validate all configurable feature periods before calculations."""
    _validate_windows("lag_periods", lag_periods)
    _validate_windows("rolling_mean_windows", rolling_mean_windows)
    _validate_windows("rolling_std_windows", rolling_std_windows)
    if any(
        not isinstance(window, int) or isinstance(window, bool) or window <= 0
        for window in scalar_windows.values()
    ):
        raise ValueError("All indicator windows must be positive integers.")
    if macd_fast >= macd_slow:
        raise ValueError("macd_fast must be smaller than macd_slow.")
    if bollinger_std_multiplier <= 0:
        raise ValueError("bollinger_std_multiplier must be positive.")


def build_xgboost_features(
    df: pd.DataFrame,
    lag_periods: tuple[int, ...] = DEFAULT_LAG_PERIODS,
    rolling_mean_windows: tuple[int, ...] = DEFAULT_ROLLING_MEAN_WINDOWS,
    rolling_std_windows: tuple[int, ...] = DEFAULT_ROLLING_STD_WINDOWS,
    extrema_window: int = DEFAULT_EXTREMA_WINDOW,
    volatility_window: int = DEFAULT_VOLATILITY_WINDOW,
    rsi_period: int = DEFAULT_RSI_PERIOD,
    macd_fast: int = DEFAULT_MACD_FAST,
    macd_slow: int = DEFAULT_MACD_SLOW,
    macd_signal: int = DEFAULT_MACD_SIGNAL,
    bollinger_window: int = DEFAULT_BOLLINGER_WINDOW,
    bollinger_std_multiplier: float = DEFAULT_BOLLINGER_STD_MULTIPLIER,
    atr_window: int = DEFAULT_ATR_WINDOW,
) -> dict[str, pd.DataFrame]:
    """Build causal features on the full series, then return chronological splits."""
    _validate_input(df)
    scalar_windows = {
        "extrema_window": extrema_window,
        "volatility_window": volatility_window,
        "rsi_period": rsi_period,
        "macd_fast": macd_fast,
        "macd_slow": macd_slow,
        "macd_signal": macd_signal,
        "bollinger_window": bollinger_window,
        "atr_window": atr_window,
    }
    _validate_feature_parameters(
        lag_periods,
        rolling_mean_windows,
        rolling_std_windows,
        scalar_windows,
        macd_fast,
        macd_slow,
        bollinger_std_multiplier,
    )

    featured = df.sort_values("ts", kind="mergesort").reset_index(drop=True).copy()
    _add_shared_indicators(
        featured,
        volatility_window,
        rsi_period,
        macd_fast,
        macd_slow,
        macd_signal,
    )
    _add_lag_and_rolling_features(
        featured,
        lag_periods,
        rolling_mean_windows,
        rolling_std_windows,
        extrema_window,
    )
    featured[f"bollinger_band_width_{bollinger_window}"] = (
        _calculate_bollinger_band_width(
            featured["close"],
            bollinger_window,
            bollinger_std_multiplier,
        )
    )
    featured[f"atr_{atr_window}"] = _calculate_atr(
        featured["high"],
        featured["low"],
        featured["close"],
        atr_window,
    )

    featured = featured.dropna().reset_index(drop=True)
    return {
        split_name: featured.loc[featured["split"].eq(split_name)].reset_index(
            drop=True
        )
        for split_name in SPLIT_NAMES
    }
