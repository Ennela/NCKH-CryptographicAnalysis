"""Live feature builders must mirror the training-time pipelines exactly."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features import (
    MIN_HISTORY_ROWS,
    RANDOM_FOREST_FEATURE_LIST,
    XGBOOST_FEATURE_LIST,
    build_random_forest_live_features,
    build_xgboost_live_features,
    latest_feature_row,
)


def _ohlcv_frame(rows: int = 120) -> pd.DataFrame:
    index = np.arange(rows, dtype=float)
    close = 100.0 + 0.4 * index + 2.0 * np.sin(index / 3.0)
    return pd.DataFrame(
        {
            "ts": pd.date_range("2025-01-01", periods=rows, freq="D", tz="UTC"),
            "open": close - 0.25,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0 + 5.0 * index + (index % 7.0) * 10.0,
        }
    )


def test_xgboost_live_features_populate_latest_row() -> None:
    featured = build_xgboost_live_features(_ohlcv_frame())
    row = latest_feature_row(featured, XGBOOST_FEATURE_LIST)
    assert list(row.columns) == XGBOOST_FEATURE_LIST
    assert row.notna().all(axis=None)


def test_random_forest_live_features_populate_latest_row() -> None:
    featured = build_random_forest_live_features(_ohlcv_frame())
    row = latest_feature_row(featured, RANDOM_FOREST_FEATURE_LIST)
    assert list(row.columns) == RANDOM_FOREST_FEATURE_LIST
    assert row.notna().all(axis=None)


def test_short_history_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least"):
        build_xgboost_live_features(_ohlcv_frame(MIN_HISTORY_ROWS - 1))


def test_missing_feature_on_latest_row_is_rejected() -> None:
    featured = build_xgboost_live_features(_ohlcv_frame(21))
    # 21 rows satisfy close_lag_20 but not every rolling window on the last row
    # combined with returns-based indicators computed from row 1 onwards.
    featured.loc[featured.index[-1], "rsi"] = np.nan
    with pytest.raises(ValueError, match="rsi"):
        latest_feature_row(featured, XGBOOST_FEATURE_LIST)


def _training_frame(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    rows = len(frame)
    split = np.where(
        np.arange(rows) < rows - 40,
        "train",
        np.where(np.arange(rows) < rows - 20, "val", "test"),
    )
    frame["split"] = split
    frame["next_close"] = frame.groupby("split", sort=False)["close"].shift(-1)
    return frame


def test_xgboost_parity_with_training_builder() -> None:
    training_features = pytest.importorskip(
        "services.training.models.xgboost_features",
        reason="training package not importable",
    )
    raw = _ohlcv_frame()
    trained = pd.concat(
        training_features.build_xgboost_features(_training_frame(raw)).values(),
        ignore_index=True,
    )
    live = build_xgboost_live_features(raw)

    assert training_features.FEATURE_LIST == XGBOOST_FEATURE_LIST
    merged = trained.merge(live, on="ts", suffixes=("_train", "_live"))
    assert len(merged) == len(trained)
    for feature in XGBOOST_FEATURE_LIST:
        np.testing.assert_allclose(
            merged[f"{feature}_train"].to_numpy(dtype=float),
            merged[f"{feature}_live"].to_numpy(dtype=float),
            rtol=1e-10,
            atol=1e-10,
            err_msg=f"Feature mismatch vs training pipeline: {feature}",
        )


def test_random_forest_parity_with_training_builder() -> None:
    training_features = pytest.importorskip(
        "services.training.models.random_forest_features",
        reason="training package not importable",
    )
    raw = _ohlcv_frame()
    trained = pd.concat(
        training_features.build_random_forest_features(_training_frame(raw)).values(),
        ignore_index=True,
    )
    live = build_random_forest_live_features(raw)

    assert list(training_features.FEATURE_LIST) == RANDOM_FOREST_FEATURE_LIST
    overlap = [
        feature
        for feature in RANDOM_FOREST_FEATURE_LIST
        if feature not in ("open", "high", "low", "close", "volume")
    ]
    merged = trained.merge(live, on="ts", suffixes=("_train", "_live"))
    assert len(merged) == len(trained)
    for feature in overlap:
        np.testing.assert_allclose(
            merged[f"{feature}_train"].to_numpy(dtype=float),
            merged[f"{feature}_live"].to_numpy(dtype=float),
            rtol=1e-10,
            atol=1e-10,
            err_msg=f"Feature mismatch vs training pipeline: {feature}",
        )
