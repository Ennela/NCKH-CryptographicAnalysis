import csv
from pathlib import Path
from typing import Any, cast

import numpy as np
import optuna
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

from services.training import train_xgboost
from services.training.evaluate import compare_with_naive
from services.training.models import xgboost_model as xgboost_model_module
from services.training.models.xgboost_features import (
    FEATURE_LIST,
    SPLIT_NAMES,
    build_xgboost_features,
)
from services.training.models.xgboost_model import XGBoostModelWrapper

METRIC_NAMES = {"mae", "rmse", "mape"}


class _LiveParamsRegressor:
    def get_params(self) -> dict[str, Any]:
        return {
            "n_estimators": 12,
            "early_stopping_rounds": 7,
            "unused_parameter": None,
        }


class _LoggingModel:
    def __init__(self) -> None:
        self.model = _LiveParamsRegressor()
        self.best_iteration = 3


class _PredictionModel:
    def __init__(self, predictions: np.ndarray) -> None:
        self._predictions = predictions

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        assert len(X) == len(self._predictions)
        return self._predictions.copy()


def _dummy_tree_explainer(model: object) -> object:
    return object()


def _xgboost_params(n_estimators: int) -> dict[str, Any]:
    return {
        "n_estimators": n_estimators,
        "max_depth": 2,
        "learning_rate": 0.3,
        "objective": "reg:squarederror",
        "eval_metric": "rmse",
        "tree_method": "hist",
        "base_score": 0.0,
        "n_jobs": 1,
        "random_state": 7,
        "verbosity": 0,
    }


def _result_metrics() -> dict[str, float | None]:
    return {
        field_name: float(index)
        for index, field_name in enumerate(
            train_xgboost.RESULT_METRIC_FIELDNAMES,
            start=1,
        )
    }


def _feature_row(
    splits: dict[str, pd.DataFrame],
    timestamp: pd.Timestamp,
) -> np.ndarray:
    combined = pd.concat(splits.values(), ignore_index=True)
    matching_rows = combined.loc[combined["ts"].eq(timestamp), FEATURE_LIST]
    assert len(matching_rows) == 1
    return matching_rows.iloc[0].to_numpy(dtype=float)


@pytest.fixture(autouse=True)
def disable_shap_explainer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        xgboost_model_module.shap,
        "TreeExplainer",
        _dummy_tree_explainer,
    )


@pytest.fixture
def ohlcv_frame() -> pd.DataFrame:
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
    frame["next_close"] = frame.groupby("split", sort=False)["close"].shift(-1)
    return frame


@pytest.fixture
def feature_splits(ohlcv_frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return build_xgboost_features(ohlcv_frame)


@pytest.fixture
def xgboost_data() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    train_signal = np.linspace(0.0, 1.0, 24)
    val_signal = np.linspace(1.1, 1.4, 8)
    X_train = pd.DataFrame(
        {
            "signal": train_signal,
            "trend": train_signal**2,
        }
    )
    X_val = pd.DataFrame(
        {
            "signal": val_signal,
            "trend": val_signal**2,
        }
    )
    y_train = pd.Series(np.full(len(X_train), 100.0), name="next_close")
    y_val = pd.Series(np.full(len(X_val), -100.0), name="next_close")
    return X_train, y_train, X_val, y_val


def test_no_lookahead_features(ohlcv_frame: pd.DataFrame) -> None:
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


def test_scaler_fit_train_only(
    feature_splits: dict[str, pd.DataFrame],
) -> None:
    scaled_data = train_xgboost.prepare_scaled_dataset(feature_splits)
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


def test_early_stopping_uses_val(
    xgboost_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    X_train, y_train, X_val, y_val = xgboost_data
    n_estimators = 12
    model = XGBoostModelWrapper(params=_xgboost_params(n_estimators))

    model.fit(
        X_train,
        y_train,
        X_val=X_val,
        y_val=y_val,
        early_stopping_rounds=2,
    )

    assert model.best_iteration is not None
    assert 0 <= model.best_iteration < n_estimators
    assert model.model.get_params()["early_stopping_rounds"] == 2

    model.fit(X_train, y_train)
    assert model.model.get_params()["early_stopping_rounds"] is None


def test_optuna_objective_does_not_build_shap_explainer(
    monkeypatch: pytest.MonkeyPatch,
    xgboost_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    def fail_if_called(model: object) -> object:
        raise AssertionError("Optuna objective must not create a SHAP explainer")

    monkeypatch.setattr(
        xgboost_model_module.shap,
        "TreeExplainer",
        fail_if_called,
    )
    X_train, y_train, X_val, y_val = xgboost_data
    trial = optuna.trial.FixedTrial(
        {
            "n_estimators": 50,
            "max_depth": 3,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.01,
            "reg_lambda": 0.01,
        }
    )

    objective_value = train_xgboost.objective_optuna(
        trial,
        X_train,
        y_train,
        X_val,
        y_val,
        seed=42,
    )

    assert np.isfinite(objective_value)


def test_shap_explainer_is_created_lazily(
    monkeypatch: pytest.MonkeyPatch,
    xgboost_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    created_for: list[object] = []

    class _FakeTreeExplainer:
        def __init__(self, model: object) -> None:
            created_for.append(model)

        def shap_values(self, values: pd.DataFrame) -> np.ndarray:
            return np.zeros(values.shape, dtype=float)

    monkeypatch.setattr(
        xgboost_model_module.shap,
        "TreeExplainer",
        _FakeTreeExplainer,
    )
    X_train, y_train, X_val, _ = xgboost_data
    model = XGBoostModelWrapper(params=_xgboost_params(n_estimators=8))

    model.fit(X_train, y_train)
    assert model.explainer is None

    importances = model.get_feature_importances(list(X_train.columns))
    assert set(importances) == set(X_train.columns)
    assert model.explainer is None

    first_values = model.calculate_shap_values(X_val)
    second_values = model.calculate_shap_values(X_val)

    assert created_for == [model.model]
    np.testing.assert_array_equal(first_values, np.zeros(X_val.shape))
    np.testing.assert_array_equal(second_values, first_values)


def test_save_load_roundtrip(
    tmp_path: Path,
    xgboost_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    X_train, y_train, X_val, _ = xgboost_data
    model = XGBoostModelWrapper(params=_xgboost_params(n_estimators=8))
    model.fit(X_train, y_train)
    predictions_before_save = model.predict(X_val)

    model_path = tmp_path / "xgboost_model.json"
    model.save(str(model_path))
    loaded_model = XGBoostModelWrapper(params=_xgboost_params(n_estimators=8))
    loaded_model.load(str(model_path))
    assert loaded_model.explainer is None
    predictions_after_load = loaded_model.predict(X_val)

    np.testing.assert_allclose(
        predictions_before_save,
        predictions_after_load,
        rtol=0.0,
        atol=1e-6,
    )


def test_compare_with_naive_reports() -> None:
    y_true = np.array([102.0, 99.0, 105.0])
    y_pred = np.array([101.0, 101.0, 104.0])
    y_naive = np.array([100.0, 100.0, 103.0])

    comparison = compare_with_naive(y_true, y_pred, y_naive)

    assert set(comparison) == {
        "model",
        "naive",
        "improvement_pct",
        "improvement_abs",
    }
    assert all(set(comparison[group_name]) == METRIC_NAMES for group_name in comparison)

    zero_baseline_comparison = compare_with_naive(y_true, y_pred, y_true)
    assert all(
        value is None for value in zero_baseline_comparison["improvement_pct"].values()
    )
    assert all(
        value is not None
        for value in zero_baseline_comparison["improvement_abs"].values()
    )


def test_compare_with_naive_near_zero_baseline_is_undefined() -> None:
    y_true = np.array([1.0])
    y_pred = np.array([2.0])
    y_naive = np.array([1.0 + 1e-12])

    comparison = compare_with_naive(y_true, y_pred, y_naive)

    naive_rmse = comparison["naive"]["rmse"]
    model_rmse = comparison["model"]["rmse"]
    absolute_improvement = comparison["improvement_abs"]["rmse"]
    assert naive_rmse is not None
    assert model_rmse is not None
    assert absolute_improvement is not None
    assert 0.0 < naive_rmse < 1e-9
    assert comparison["improvement_pct"]["rmse"] is None
    assert absolute_improvement == pytest.approx(naive_rmse - model_rmse)


def test_evaluate_split_reports_full_naive_comparison() -> None:
    y_true = pd.Series([102.0, 99.0, 105.0], name="next_close")
    predictions = np.array([101.0, 101.0, 104.0])
    previous_close = pd.Series([100.0, 100.0, 103.0], name="close")
    X = pd.DataFrame({"feature": [1.0, 2.0, 3.0]})
    model = cast(XGBoostModelWrapper, _PredictionModel(predictions))

    metrics = train_xgboost._evaluate_split(
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
    assert "improvement_vs_naive_rmse_pct_test" not in metrics
    assert metrics["naive_rmse_test"] == pytest.approx(
        np.sqrt(np.mean(np.square(y_true.to_numpy() - previous_close.to_numpy())))
    )


def test_append_result_writes_exact_schema_and_serializes_none(
    tmp_path: Path,
) -> None:
    results_path = tmp_path / "xgboost_results.csv"
    metrics = _result_metrics()
    metrics["improvement_pct_rmse_test"] = None

    train_xgboost.append_result(
        ticker="ACB",
        timeframe="1d",
        metrics=metrics,
        run_id="run-1",
        results_path=results_path,
    )
    train_xgboost.append_result(
        ticker="ACB",
        timeframe="1d",
        metrics=metrics,
        run_id="run-2",
        results_path=results_path,
    )

    with results_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    assert tuple(reader.fieldnames or ()) == train_xgboost.RESULT_FIELDNAMES
    assert len(reader.fieldnames or ()) == 27
    assert len(rows) == 2
    assert rows[0]["improvement_pct_rmse_test"] == ""
    assert "None" not in results_path.read_text(encoding="utf-8")


def test_append_result_rejects_mismatched_header_without_writing(
    tmp_path: Path,
) -> None:
    results_path = tmp_path / "xgboost_results.csv"
    results_path.write_text(
        "ticker,timeframe,mae_val,rmse_val,mape_val,mae_test,rmse_test,"
        "mape_test,naive_rmse_test,improvement_vs_naive_rmse_pct_test,"
        "mlflow_run_id\nACB,1d,1,1,1,1,1,1,1,1,old-run\n",
        encoding="utf-8",
    )
    contents_before = results_path.read_bytes()

    with pytest.raises(ValueError, match="required 27-column schema"):
        train_xgboost.append_result(
            ticker="ACB",
            timeframe="1d",
            metrics=_result_metrics(),
            run_id="new-run",
            results_path=results_path,
        )

    assert results_path.read_bytes() == contents_before


def test_mlflow_logs_live_model_params(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_log_experiment_run(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "test-run-id"

    def fake_log_scaler_artifact(scaler: StandardScaler, run_id: str) -> None:
        assert isinstance(scaler, StandardScaler)
        assert run_id == "test-run-id"

    monkeypatch.setattr(
        train_xgboost,
        "log_experiment_run",
        fake_log_experiment_run,
    )
    monkeypatch.setattr(
        train_xgboost,
        "_log_scaler_artifact",
        fake_log_scaler_artifact,
    )
    model = cast(XGBoostModelWrapper, _LoggingModel())

    run_id = train_xgboost.log_training_run(
        ticker="FPT",
        timeframe="1d",
        seed=42,
        n_trials=2,
        best_params={
            "n_estimators": 99,
            "early_stopping_rounds": 50,
        },
        metrics={
            "mae_test": 1.0,
            "improvement_pct_rmse_test": None,
        },
        model=model,
        scaler=StandardScaler(),
    )

    logged_params = captured["params"]
    assert run_id == "test-run-id"
    assert logged_params["n_estimators"] == 12
    assert logged_params["early_stopping_rounds"] == 7
    assert "unused_parameter" not in logged_params
    assert captured["metrics"] == {"mae_test": 1.0}
