"""Causal feature engineering owned by the Random Forest pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd

SPLIT_NAMES: tuple[str, ...] = ("train", "val", "test")
LAG_PERIODS: tuple[int, ...] = (1, 3, 5, 10, 20)
ROLLING_WINDOWS: tuple[int, ...] = (5, 10, 20)
REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {"ts", "open", "high", "low", "close", "volume", "next_close", "split"}
)
METADATA_COLUMNS: tuple[str, ...] = (
    "input_ts",
    "target_ts",
    "current_close",
    "actual_close",
)
FEATURE_LIST: tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "return_1",
    "volume_return_1",
    *(f"close_lag_{period}" for period in LAG_PERIODS),
    *(f"rolling_mean_{window}" for window in ROLLING_WINDOWS),
    *(f"rolling_std_{window}" for window in ROLLING_WINDOWS),
)


def _validate_input(df: pd.DataFrame) -> None:
    """Validate the continuous locked-dataset frame."""
    missing_columns = REQUIRED_COLUMNS.difference(df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Input DataFrame is missing required columns: {missing}.")
    invalid_splits = set(df["split"].dropna().astype(str)).difference(SPLIT_NAMES)
    if df["split"].isna().any() or invalid_splits:
        raise ValueError("Input DataFrame contains invalid split labels.")


def _add_alignment_columns(featured: pd.DataFrame) -> None:
    """Preserve the horizon-one input and target identity before row filtering."""
    featured["input_ts"] = featured["ts"]
    featured["target_ts"] = featured.groupby("split", sort=False)["ts"].shift(-1)
    featured["current_close"] = featured["close"]
    featured["actual_close"] = featured["next_close"]


def _add_causal_features(featured: pd.DataFrame) -> None:
    """Add current-row, lagged, and rolling features without future values."""
    featured["return_1"] = featured["close"].pct_change(fill_method=None)
    featured["volume_return_1"] = featured["volume"].pct_change(fill_method=None)
    for period in LAG_PERIODS:
        featured[f"close_lag_{period}"] = featured["close"].shift(period)
    for window in ROLLING_WINDOWS:
        rolling_close = featured["close"].rolling(window=window)
        featured[f"rolling_mean_{window}"] = rolling_close.mean()
        featured[f"rolling_std_{window}"] = rolling_close.std()


def _validate_output(featured: pd.DataFrame) -> None:
    """Reject invalid feature values or broken horizon-one alignment."""
    numeric_columns = [*FEATURE_LIST, "current_close", "actual_close", "next_close"]
    numeric_values = featured.loc[:, numeric_columns].to_numpy(dtype=np.float64)
    if not np.isfinite(numeric_values).all():
        raise ValueError("Random Forest features contain NaN or infinite values.")
    if not featured["input_ts"].lt(featured["target_ts"]).all():
        raise ValueError("Each Random Forest input_ts must precede target_ts.")
    if not np.array_equal(
        featured["actual_close"].to_numpy(dtype=np.float64),
        featured["next_close"].to_numpy(dtype=np.float64),
    ):
        raise ValueError("Random Forest target must be next_close.")


def build_random_forest_features(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build features on the continuous series, then return chronological splits."""
    _validate_input(df)
    featured = df.sort_values("ts", kind="mergesort").reset_index(drop=True).copy()
    _add_alignment_columns(featured)
    _add_causal_features(featured)
    required_output = [*FEATURE_LIST, *METADATA_COLUMNS, "next_close"]
    featured = featured.dropna(subset=required_output).reset_index(drop=True)
    _validate_output(featured)
    return {
        split_name: featured.loc[featured["split"].eq(split_name)].reset_index(
            drop=True
        )
        for split_name in SPLIT_NAMES
    }
