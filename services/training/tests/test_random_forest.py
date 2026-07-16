"""Test suite for the Random Forest training pipeline.

Mirrors ``test_xgboost.py`` to ensure Random Forest uses the same DataLoader,
feature set, split logic, and evaluation metrics as XGBoost.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, cast

import numpy as np
import optuna
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

from services.training import train_random_forest
from services.training.models.random_forest_model import RandomForestModelWrapper
from services.training.models.xgboost_features import (
    FEATURE_LIST,
    SPLIT_NAMES,
    build_xgboost_features,
)

METRIC_NAMES = {"mae", "rmse", "mape"}


# ── Shared test helpers ────────────────────────────────────────────────────────


class _PredictionModel:
    """Minimal duck-type of RandomForestModelWrapper for unit testing."""

    def __init__(self, predictions: np.ndarray) -> None:
        self._predictions = predictions

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        assert len(X) == len(self._predictions)
        return self._predictions.copy()


def _rf_params(n_estimators: int, seed: int = 7) -> dict[str, Any]:
    """Return a lightweight RF parameter dict for fast tests."""
    return {
        "n_estimators": n_estimators,
        "max_depth": 3,
        "min_samples_split": 5,
        "min_samples_leaf": 2,
        "max_features": "sqrt",
        "random_state": seed,
        "n_jobs": 1,
    }


def _result_metrics() -> dict[str, float | None]:
    """Build a stub metrics dict matching RESULT_METRIC_FIELDNAMES."""
    return {
        field_name: float(index)
        for index, field_name in enumerate(
            train_random_forest.RESULT_METRIC_FIELDNAMES,
            start=1,
        )
    }


def _feature_row(
    splits: dict[str, pd.DataFrame],
    timestamp: pd.Timestamp,
) -> np.ndarray:
    """Extract the feature vector for a specific timestamp across all splits."""
    combined = pd.concat(splits.values(), ignore_index=True)
    matching_rows = combined.loc[combined["ts"].eq(timestamp), FEATURE_LIST]
    assert len(matching_rows) == 1
    return matching_rows.iloc[0].to_numpy(dtype=float)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def ohlcv_frame() -> pd.DataFrame:
    """Synthetic OHLCV frame with 72 rows and chronological split labels."""
    row_count = 72
    row_number = np.arange(row_count, dtype=float)
    close = 100.0 + 0.4 * row_number + 2.0 * np.sin(row_number / 3.0)
    split = np.where(
        row_number < 48,
        "train",
        np.where(row_number < 60, "val", "test"),
    )
    frame = pd.DataFrame(
        {
            "ts": pd.date_range(
                "2025-01-01",
                periods=row_count,
                freq="D",
                tz="UTC",
            ),
            "open": close - 0.25,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0 + 5.0 * row_number + (row_number % 7.0) * 10.0,
            "split": split,
        }
    )
    # next_close is created per split to avoid leaking across boundaries.
    frame["next_close"] = frame.groupby("split", sort=False)["close"].shift(-1)
    return frame


@pytest.fixture
def feature_splits(ohlcv_frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Feature splits produced by the shared XGBoost feature pipeline."""
    return build_xgboost_features(ohlcv_frame)


@pytest.fixture
def rf_data() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Small synthetic train/val pair for model-level unit tests."""
    train_signal = np.linspace(0.0, 1.0, 40)
    val_signal = np.linspace(1.1, 1.4, 10)
    X_train = pd.DataFrame(
        {
            "signal": train_signal,
            "trend": train_signal ** 2,
        }
    )
    X_val = pd.DataFrame(
        {
            "signal": val_signal,
            "trend": val_signal ** 2,
        }
    )
    y_train = pd.Series(train_signal * 100.0 + 50.0, name="next_close")
    y_val = pd.Series(val_signal * 100.0 + 50.0, name="next_close")
    return X_train, y_train, X_val, y_val


# ── Feature contract tests (same feature set as XGBoost) ──────────────────────


def test_no_lookahead_features(ohlcv_frame: pd.DataFrame) -> None:
    """Features at time t must not change when future rows are perturbed."""
    cutoff = ohlcv_frame.loc[40, "ts"]
    original_splits = build_xgboost_features(ohlcv_frame)

    changed_frame = ohlcv_frame.copy()
    future_mask = changed_frame["ts"].gt(cutoff)
    changed_frame.loc[future_mask, ["open", "high", "low", "close"]] += 10_000.0
    changed_frame.loc[future_mask, "volume"] *= 100.0
    target_mask = changed_frame["ts"].ge(cutoff)
    changed_frame.loc[target_mask, "next_close"] += 25_000.0
    changed_splits = build_xgboost_features(changed_frame)

    np.testing.assert_allclose(
        _feature_row(original_splits, cutoff),
        _feature_row(changed_splits, cutoff),
        rtol=0.0,
        atol=0.0,
    )


def test_split_boundary_respected(
    feature_splits: dict[str, pd.DataFrame],
) -> None:
    """Each chronological split must be non-overlapping and ordered."""
    timestamp_sets: dict[str, set[pd.Timestamp]] = {}
    for split_name in SPLIT_NAMES:
        split_frame = feature_splits[split_name]
        assert not split_frame.empty
        assert set(split_frame["split"]) == {split_name}
        timestamp_sets[split_name] = set(split_frame["ts"])

    assert timestamp_sets["train"].isdisjoint(timestamp_sets["val"])
    assert timestamp_sets["train"].isdisjoint(timestamp_sets["test"])
    assert timestamp_sets["val"].isdisjoint(timestamp_sets["test"])
    assert feature_splits["train"]["ts"].max() < feature_splits["val"]["ts"].min()
    assert feature_splits["val"]["ts"].max() < feature_splits["test"]["ts"].min()


# ── Scaler contract tests ──────────────────────────────────────────────────────


def test_scaler_fit_train_only(
    feature_splits: dict[str, pd.DataFrame],
) -> None:
    """StandardScaler mean must match train-only mean, not the full-dataset mean."""
    scaled_data = train_random_forest.prepare_scaled_dataset(feature_splits)
    train_mean = feature_splits["train"].loc[:, FEATURE_LIST].mean().to_numpy()
    all_features = pd.concat(
        [feature_splits[name] for name in SPLIT_NAMES],
        ignore_index=True,
    ).loc[:, FEATURE_LIST]

    np.testing.assert_allclose(
        scaled_data.scaler.mean_,
        train_mean,
        rtol=1e-12,
        atol=1e-12,
    )
    assert not np.allclose(
        scaled_data.scaler.mean_,
        all_features.mean().to_numpy(),
        rtol=1e-7,
        atol=1e-9,
    )


def test_prepare_scaled_dataset_raises_on_empty_split(
    feature_splits: dict[str, pd.DataFrame],
) -> None:
    """prepare_scaled_dataset must raise ValueError when any split is empty."""
    bad_splits = {**feature_splits, "val": pd.DataFrame()}
    with pytest.raises(ValueError, match="non-empty"):
        train_random_forest.prepare_scaled_dataset(bad_splits)


# ── Model wrapper tests ────────────────────────────────────────────────────────


def test_rf_model_fit_predict(
    rf_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    """Fitted model must return predictions of the correct shape."""
    X_train, y_train, X_val, _ = rf_data
    model = RandomForestModelWrapper(params=_rf_params(n_estimators=10))
    model.fit(X_train, y_train)
    predictions = model.predict(X_val)
    assert predictions.shape == (len(X_val),)
    assert np.all(np.isfinite(predictions))


def test_rf_feature_importances(
    rf_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    """Feature importances must cover all training columns and sum to ≈ 1."""
    X_train, y_train, _, _ = rf_data
    model = RandomForestModelWrapper(params=_rf_params(n_estimators=10))
    model.fit(X_train, y_train)
    importances = model.get_feature_importances(list(X_train.columns))

    assert set(importances.keys()) == set(X_train.columns)
    total = sum(importances.values())
    assert total == pytest.approx(1.0, abs=1e-6)


def test_rf_get_params_returns_dict(
    rf_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    """get_params() must return a non-empty dict after fitting."""
    X_train, y_train, _, _ = rf_data
    model = RandomForestModelWrapper(params=_rf_params(n_estimators=5))
    model.fit(X_train, y_train)
    params = model.get_params()
    assert isinstance(params, dict)
    assert "n_estimators" in params
    assert params["n_estimators"] == 5


def test_rf_save_load_roundtrip(
    tmp_path: Path,
    rf_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    """save() + load() must produce byte-identical predictions."""
    X_train, y_train, X_val, _ = rf_data
    model = RandomForestModelWrapper(params=_rf_params(n_estimators=10))
    model.fit(X_train, y_train)
    predictions_before = model.predict(X_val)

    model_path = tmp_path / "rf_model.joblib"
    model.save(str(model_path))
    assert model_path.exists()

    loaded_model = RandomForestModelWrapper(params=_rf_params(n_estimators=10))
    loaded_model.load(str(model_path))
    predictions_after = loaded_model.predict(X_val)

    np.testing.assert_allclose(
        predictions_before,
        predictions_after,
        rtol=0.0,
        atol=1e-9,
    )


# ── Optuna objective test ──────────────────────────────────────────────────────


def test_optuna_objective_returns_finite_mae(
    rf_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    """Optuna objective must return a finite float for a fixed trial."""
    X_train, y_train, X_val, y_val = rf_data
    trial = optuna.trial.FixedTrial(
        {
            "n_estimators": 20,
            "max_depth": 3,
            "min_samples_split": 5,
            "min_samples_leaf": 2,
            "max_features": "sqrt",
        }
    )
    objective_value = train_random_forest.objective_optuna(
        trial,
        X_train,
        y_train,
        X_val,
        y_val,
        seed=42,
    )
    assert np.isfinite(objective_value)
    assert objective_value >= 0.0


# ── Evaluation helper tests ────────────────────────────────────────────────────


def test_evaluate_split_reports_full_naive_comparison() -> None:
    """_evaluate_split must return all model + naive + improvement metrics."""
    y_true = pd.Series([102.0, 99.0, 105.0], name="next_close")
    predictions = np.array([101.0, 101.0, 104.0])
    previous_close = pd.Series([100.0, 100.0, 103.0], name="close")
    X = pd.DataFrame({"feature": [1.0, 2.0, 3.0]})
    model = cast(RandomForestModelWrapper, _PredictionModel(predictions))

    metrics = train_random_forest._evaluate_split(
        model,
        X,
        y_true,
        previous_close,
        "test",
    )
    required_metrics = {
        f"{group_prefix}{metric_name}_test"
        for group_prefix in (
            "",
            "naive_",
            "improvement_pct_",
            "improvement_abs_",
        )
        for metric_name in METRIC_NAMES
    }

    assert required_metrics <= set(metrics)
    assert metrics["naive_rmse_test"] == pytest.approx(
        np.sqrt(np.mean(np.square(y_true.to_numpy() - previous_close.to_numpy())))
    )


# ── CSV result schema tests ────────────────────────────────────────────────────


def test_append_result_writes_exact_schema_and_serializes_none(
    tmp_path: Path,
) -> None:
    """append_result must write 27 columns and serialise None as empty string."""
    results_path = tmp_path / "random_forest_results.csv"
    metrics = _result_metrics()
    metrics["improvement_pct_rmse_test"] = None

    train_random_forest.append_result(
        ticker="ACB",
        timeframe="1d",
        metrics=metrics,
        run_id="run-1",
        results_path=results_path,
    )
    train_random_forest.append_result(
        ticker="ACB",
        timeframe="1d",
        metrics=metrics,
        run_id="run-2",
        results_path=results_path,
    )

    with results_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    assert tuple(reader.fieldnames or ()) == train_random_forest.RESULT_FIELDNAMES
    assert len(reader.fieldnames or ()) == 27
    assert len(rows) == 2
    assert rows[0]["improvement_pct_rmse_test"] == ""
    assert "None" not in results_path.read_text(encoding="utf-8")


def test_append_result_rejects_mismatched_header_without_writing(
    tmp_path: Path,
) -> None:
    """append_result must raise ValueError and leave the file unchanged."""
    results_path = tmp_path / "random_forest_results.csv"
    results_path.write_text(
        "ticker,timeframe,mae_val,wrong_col\nACB,1d,1,2\n",
        encoding="utf-8",
    )
    contents_before = results_path.read_bytes()

    with pytest.raises(ValueError, match="required 27-column schema"):
        train_random_forest.append_result(
            ticker="ACB",
            timeframe="1d",
            metrics=_result_metrics(),
            run_id="new-run",
            results_path=results_path,
        )

    assert results_path.read_bytes() == contents_before


def test_append_result_creates_parent_directory(tmp_path: Path) -> None:
    """append_result must create missing parent directories."""
    nested_path = tmp_path / "deep" / "nested" / "rf_results.csv"
    train_random_forest.append_result(
        ticker="FPT",
        timeframe="1d",
        metrics=_result_metrics(),
        run_id="run-xyz",
        results_path=nested_path,
    )
    assert nested_path.exists()
    with nested_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["ticker"] == "FPT"


# ── Full integration fixture test ──────────────────────────────────────────────


def test_evaluate_model_returns_val_and_test_metrics(
    feature_splits: dict[str, pd.DataFrame],
) -> None:
    """evaluate_model must return metrics for both val and test suffixes."""
    data = train_random_forest.prepare_scaled_dataset(feature_splits)
    model = RandomForestModelWrapper(params=_rf_params(n_estimators=10))
    model.fit(data.X_train, data.y_train)

    metrics = train_random_forest.evaluate_model(model, data, feature_splits)

    for suffix in ("val", "test"):
        for base_name in ("mae", "rmse", "mape"):
            assert f"{base_name}_{suffix}" in metrics, (
                f"Missing metric: {base_name}_{suffix}"
            )
            assert f"naive_{base_name}_{suffix}" in metrics
            assert f"improvement_pct_{base_name}_{suffix}" in metrics
            assert f"improvement_abs_{base_name}_{suffix}" in metrics
