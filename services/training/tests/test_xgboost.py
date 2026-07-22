import csv
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, cast

import numpy as np
import optuna
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

from services.training import train_xgboost
from services.training.models import xgboost_model as xgboost_model_module
from services.training.models.xgboost_features import (
    AUDIT_COLUMNS,
    FEATURE_LIST,
    SPLIT_NAMES,
    build_xgboost_features,
)
from services.training.models.xgboost_model import XGBoostModelWrapper


class _LiveParamsRegressor:
    def get_params(self) -> dict[str, Any]:
        return {
            "n_estimators": 12,
            "early_stopping_rounds": 7,
            "missing": np.nan,
            "unused_parameter": None,
        }


class _LoggingModel:
    def __init__(self) -> None:
        self.model = _LiveParamsRegressor()
        self.best_iteration = 3


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


def _metric_values() -> train_xgboost.MetricValues:
    return train_xgboost.evaluate_metric_vectors(
        np.array([102.0, 99.0, 105.0]),
        np.array([101.0, 101.0, 104.0]),
        np.array([100.0, 100.0, 103.0]),
    )


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
    row_count = 90
    row_number = np.arange(row_count, dtype=float)
    close = 100.0 + 0.4 * row_number + 2.0 * np.sin(row_number / 3.0)
    split = np.where(
        row_number < 60,
        "train",
        np.where(row_number < 75, "val", "test"),
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
def metadata() -> train_xgboost.DatasetMetadata:
    return train_xgboost.DatasetMetadata(
        dataset_version="group_dataset_v1",
        snapshot_name="ohlcv_full_current",
    )


@pytest.fixture
def test_manifest(
    feature_splits: dict[str, pd.DataFrame],
    metadata: train_xgboost.DatasetMetadata,
) -> pd.DataFrame:
    return train_xgboost.build_test_manifest(
        feature_splits["test"], metadata, "ACB", "1d"
    )


@pytest.fixture
def xgboost_data() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    train_signal = np.linspace(0.0, 1.0, 24)
    val_signal = np.linspace(1.1, 1.4, 8)
    X_train = pd.DataFrame({"signal": train_signal, "trend": train_signal**2})
    X_val = pd.DataFrame({"signal": val_signal, "trend": val_signal**2})
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
    changed_frame["next_close"] = changed_frame.groupby("split", sort=False)[
        "close"
    ].shift(-1)
    changed_splits = build_xgboost_features(changed_frame)

    np.testing.assert_allclose(
        _feature_row(original_splits, cutoff),
        _feature_row(changed_splits, cutoff),
        rtol=0.0,
        atol=0.0,
    )


def test_features_use_continuous_history_across_splits(
    ohlcv_frame: pd.DataFrame,
    feature_splits: dict[str, pd.DataFrame],
) -> None:
    first_val_ts = ohlcv_frame.loc[ohlcv_frame["split"].eq("val"), "ts"].iloc[0]
    first_test_ts = ohlcv_frame.loc[ohlcv_frame["split"].eq("test"), "ts"].iloc[0]

    assert feature_splits["val"]["ts"].iloc[0] == first_val_ts
    assert feature_splits["test"]["ts"].iloc[0] == first_test_ts


def test_split_boundary_and_audit_columns_are_preserved(
    ohlcv_frame: pd.DataFrame,
    feature_splits: dict[str, pd.DataFrame],
) -> None:
    raw_by_timestamp = ohlcv_frame.set_index("ts")
    timestamp_sets: dict[str, set[pd.Timestamp]] = {}
    for split_name in SPLIT_NAMES:
        split_frame = feature_splits[split_name]
        assert not split_frame.empty
        assert set(split_frame["split"]) == {split_name}
        assert set(AUDIT_COLUMNS) <= set(split_frame.columns)
        assert split_frame["input_ts"].equals(split_frame["ts"])
        np.testing.assert_array_equal(
            split_frame["current_close"], split_frame["close"]
        )
        np.testing.assert_array_equal(
            split_frame["actual_close"], split_frame["next_close"]
        )
        expected_actual = raw_by_timestamp.loc[
            split_frame["target_ts"], "close"
        ].to_numpy()
        np.testing.assert_array_equal(split_frame["actual_close"], expected_actual)
        assert split_frame["input_ts"].lt(split_frame["target_ts"]).all()
        timestamp_sets[split_name] = set(split_frame["ts"])

    assert timestamp_sets["train"].isdisjoint(timestamp_sets["val"])
    assert timestamp_sets["train"].isdisjoint(timestamp_sets["test"])
    assert timestamp_sets["val"].isdisjoint(timestamp_sets["test"])


def test_scaler_fit_train_only(feature_splits: dict[str, pd.DataFrame]) -> None:
    scaled_data = train_xgboost.prepare_scaled_dataset(feature_splits)
    train_mean = feature_splits["train"].loc[:, FEATURE_LIST].mean().to_numpy()
    all_features = pd.concat(
        [feature_splits[name] for name in SPLIT_NAMES], ignore_index=True
    ).loc[:, FEATURE_LIST]

    np.testing.assert_allclose(
        scaled_data.scaler.mean_, train_mean, rtol=1e-12, atol=1e-12
    )
    assert not np.allclose(
        scaled_data.scaler.mean_,
        all_features.mean().to_numpy(),
        rtol=1e-7,
        atol=1e-9,
    )


def test_early_stopping_uses_validation(
    xgboost_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    X_train, y_train, X_val, y_val = xgboost_data
    model = XGBoostModelWrapper(params=_xgboost_params(n_estimators=12))
    model.fit(
        X_train,
        y_train,
        X_val=X_val,
        y_val=y_val,
        early_stopping_rounds=2,
    )

    assert model.best_iteration is not None
    assert 0 <= model.best_iteration < 12
    assert model.model.get_params()["early_stopping_rounds"] == 2
    model.fit(X_train, y_train)
    assert model.model.get_params()["early_stopping_rounds"] is None


def test_optuna_objective_does_not_build_shap_explainer(
    monkeypatch: pytest.MonkeyPatch,
    xgboost_data: tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series],
) -> None:
    def fail_if_called(model: object) -> object:
        raise AssertionError("Optuna objective must not create a SHAP explainer")

    monkeypatch.setattr(xgboost_model_module.shap, "TreeExplainer", fail_if_called)
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
        trial, X_train, y_train, X_val, y_val, seed=42
    )
    assert np.isfinite(objective_value)


def test_optuna_optimization_never_passes_test_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    X_train = pd.DataFrame({"feature": [1.0]})
    X_val = pd.DataFrame({"feature": [2.0]})
    X_test = pd.DataFrame({"test_only": [999.0]})
    y_train = pd.Series([1.0])
    y_val = pd.Series([2.0])
    y_test = pd.Series([999.0])
    data = train_xgboost.ScaledDataset(
        scaler=StandardScaler(),
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
    )
    captured: list[tuple[Any, ...]] = []

    def fake_objective(*args: Any, **kwargs: Any) -> float:
        captured.append(args)
        return 1.0

    monkeypatch.setattr(train_xgboost, "objective_optuna", fake_objective)
    train_xgboost.optimize_params(data, n_trials=1, seed=42)

    assert len(captured) == 1
    assert captured[0][1] is X_train
    assert captured[0][2] is y_train
    assert captured[0][3] is X_val
    assert captured[0][4] is y_val
    assert all(value is not X_test and value is not y_test for value in captured[0])


def test_pilot_uses_one_trial_without_changing_optuna_search_space() -> None:
    args = train_xgboost.parse_args(
        ["--ticker", "ACB", "--timeframe", "1d", "--seed", "42"]
    )

    assert args.n_trials == 1
    assert train_xgboost.N_ESTIMATORS_RANGE == (50, 200)
    assert train_xgboost.MAX_DEPTH_RANGE == (3, 9)
    assert train_xgboost.LEARNING_RATE_RANGE == (0.01, 0.2)
    assert train_xgboost.SAMPLING_RANGE == (0.6, 1.0)
    assert train_xgboost.REGULARIZATION_RANGE == (1e-4, 10.0)
    assert train_xgboost.XGBOOST_N_JOBS == 1


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

    monkeypatch.setattr(xgboost_model_module.shap, "TreeExplainer", _FakeTreeExplainer)
    X_train, y_train, X_val, _ = xgboost_data
    model = XGBoostModelWrapper(params=_xgboost_params(n_estimators=8))
    model.fit(X_train, y_train)
    assert model.explainer is None

    model.calculate_shap_values(X_val)
    model.calculate_shap_values(X_val)
    assert created_for == [model.model]


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
    predictions_after_load = loaded_model.predict(X_val)
    np.testing.assert_allclose(
        predictions_before_save, predictions_after_load, rtol=0.0, atol=1e-6
    )


def test_manifest_uses_utc_and_aligned_target_timestamps(
    test_manifest: pd.DataFrame,
) -> None:
    assert tuple(test_manifest.columns) == train_xgboost.MANIFEST_FIELDNAMES
    assert test_manifest["input_ts"].str.endswith("Z").all()
    assert test_manifest["target_ts"].str.endswith("Z").all()
    input_ts = pd.to_datetime(test_manifest["input_ts"], utc=True)
    target_ts = pd.to_datetime(test_manifest["target_ts"], utc=True)
    assert input_ts.lt(target_ts).all()
    assert target_ts.is_monotonic_increasing


def test_manifest_hash_is_stable_for_logically_equal_data(
    test_manifest: pd.DataFrame,
) -> None:
    expected_hash = train_xgboost.calculate_test_manifest_sha256(test_manifest)
    equivalent = test_manifest.iloc[::-1].reset_index(drop=True).copy()
    equivalent["input_ts"] = equivalent["input_ts"].str.replace(
        "Z", "+00:00", regex=False
    )
    equivalent["target_ts"] = equivalent["target_ts"].str.replace(
        "Z", "+00:00", regex=False
    )

    assert len(expected_hash) == 64
    assert train_xgboost.calculate_test_manifest_sha256(equivalent) == expected_hash


def test_naive_prediction_is_exactly_current_close() -> None:
    current_close = np.array([100.0, 101.5, 99.0])
    naive = train_xgboost.build_naive_predictions(current_close)

    np.testing.assert_array_equal(naive, current_close)
    assert naive is not current_close


def test_metrics_are_finite_and_rmse_is_not_below_mae() -> None:
    metrics = _metric_values()

    assert all(np.isfinite(value) for value in metrics.values())
    assert metrics["rmse"] + train_xgboost.RMSE_TOLERANCE >= metrics["mae"]
    assert metrics["naive_rmse"] + train_xgboost.RMSE_TOLERANCE >= metrics["naive_mae"]
    assert metrics["mape_pct"] > 0.0
    assert 0.0 <= metrics["directional_accuracy"] <= 1.0


@pytest.mark.parametrize(
    ("argument", "values"),
    [
        ("y_true", np.array([1.0, np.nan])),
        ("y_pred", np.array([1.0, np.inf])),
        ("current_close", np.array([1.0, -np.inf])),
    ],
)
def test_metrics_reject_nan_and_inf(argument: str, values: np.ndarray) -> None:
    inputs = {
        "y_true": np.array([1.0, 2.0]),
        "y_pred": np.array([1.0, 2.0]),
        "current_close": np.array([0.5, 1.5]),
    }
    inputs[argument] = values

    with pytest.raises(ValueError, match="finite"):
        train_xgboost.evaluate_metric_vectors(**inputs)


def test_prediction_count_matches_all_valid_test_samples(
    test_manifest: pd.DataFrame,
) -> None:
    predictions = np.linspace(100.0, 110.0, len(test_manifest))
    manifest_hash = train_xgboost.calculate_test_manifest_sha256(test_manifest)
    prediction_frame = train_xgboost.build_prediction_frame(
        test_manifest, predictions, manifest_hash, "run-1", 42
    )

    assert len(prediction_frame) == len(test_manifest)
    with pytest.raises(ValueError, match="count"):
        train_xgboost.build_prediction_frame(
            test_manifest, predictions[:-1], manifest_hash, "run-1", 42
        )


def test_protocol_csv_headers_and_column_order_are_exact(
    tmp_path: Path,
    test_manifest: pd.DataFrame,
    metadata: train_xgboost.DatasetMetadata,
) -> None:
    predictions = test_manifest["actual_close"].to_numpy() - 0.5
    manifest_hash = train_xgboost.calculate_test_manifest_sha256(test_manifest)
    metrics = train_xgboost.evaluate_metric_vectors(
        test_manifest["actual_close"], predictions, test_manifest["current_close"]
    )
    prediction_frame = train_xgboost.build_prediction_frame(
        test_manifest, predictions, manifest_hash, "run-1", 42
    )
    summary_frame = train_xgboost.build_summary_frame(
        metadata,
        "ACB",
        "1d",
        manifest_hash,
        metrics,
        len(test_manifest),
        "run-1",
        42,
    )
    prediction_path = tmp_path / "prediction.csv"
    summary_path = tmp_path / "summary.csv"
    train_xgboost.write_protocol_csv(
        prediction_frame, prediction_path, train_xgboost.PREDICTION_FIELDNAMES
    )
    train_xgboost.write_protocol_csv(
        summary_frame, summary_path, train_xgboost.SUMMARY_FIELDNAMES
    )

    with prediction_path.open("r", newline="", encoding="utf-8") as csv_file:
        prediction_header = tuple(next(csv.reader(csv_file)))
    with summary_path.open("r", newline="", encoding="utf-8") as csv_file:
        summary_header = tuple(next(csv.reader(csv_file)))
    assert prediction_header == train_xgboost.PREDICTION_FIELDNAMES
    assert summary_header == train_xgboost.SUMMARY_FIELDNAMES
    assert len(prediction_header) == 14
    assert len(summary_header) == 20
    assert "MSE" not in prediction_header
    assert summary_frame.loc[0, "n_samples"] == len(test_manifest)


def test_prediction_frame_rejects_non_finite_predictions(
    test_manifest: pd.DataFrame,
) -> None:
    predictions = np.ones(len(test_manifest))
    predictions[-1] = np.inf
    manifest_hash = train_xgboost.calculate_test_manifest_sha256(test_manifest)

    with pytest.raises(ValueError, match="finite"):
        train_xgboost.build_prediction_frame(
            test_manifest, predictions, manifest_hash, "run-1", 42
        )


def test_mlflow_logs_protocol_metadata_hyperparameters_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
    metadata: train_xgboost.DatasetMetadata,
) -> None:
    captured: dict[str, Any] = {}

    def fake_log_experiment_run(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "test-run-id"

    monkeypatch.setattr(train_xgboost, "log_experiment_run", fake_log_experiment_run)
    model = cast(XGBoostModelWrapper, _LoggingModel())
    metrics = _metric_values()
    manifest_hash = "a" * 64
    run_id = train_xgboost.log_training_run(
        metadata,
        "ACB",
        "1d",
        manifest_hash,
        42,
        2,
        {"n_estimators": 99, "early_stopping_rounds": 50},
        metrics,
        model,
    )

    logged_params = captured["params"]
    assert run_id == "test-run-id"
    assert logged_params["dataset_version"] == "group_dataset_v1"
    assert logged_params["snapshot_name"] == "ohlcv_full_current"
    assert logged_params["test_manifest_sha256"] == manifest_hash
    assert logged_params["symbol"] == "ACB"
    assert logged_params["timeframe"] == "1d"
    assert logged_params["seed"] == 42
    assert logged_params["target"] == "next_close"
    assert logged_params["feature_list"] == ",".join(FEATURE_LIST)
    assert logged_params["n_estimators"] == 12
    assert logged_params["early_stopping_rounds"] == 7
    assert logged_params["best_iteration"] == 3
    assert "missing" not in logged_params
    assert "unused_parameter" not in logged_params
    assert captured["metrics"] == metrics
    assert captured["model"] is model.model


def test_scaler_prediction_and_summary_are_logged_as_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prediction_path = tmp_path / "prediction.csv"
    summary_path = tmp_path / "summary.csv"
    prediction_path.write_text("prediction\n", encoding="utf-8")
    summary_path.write_text("summary\n", encoding="utf-8")
    logged: list[tuple[Path, str | None]] = []

    class _RunContext(AbstractContextManager[object]):
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *args: object) -> None:
            return None

    def fake_start_run(*, run_id: str) -> _RunContext:
        assert run_id == "run-1"
        return _RunContext()

    def fake_log_artifact(path: str, artifact_path: str | None = None) -> None:
        logged.append((Path(path), artifact_path))

    monkeypatch.setattr(train_xgboost.mlflow, "start_run", fake_start_run)
    monkeypatch.setattr(train_xgboost.mlflow, "log_artifact", fake_log_artifact)
    train_xgboost._log_run_artifacts(
        "run-1", StandardScaler(), prediction_path, summary_path
    )

    assert [(path.name, destination) for path, destination in logged] == [
        (train_xgboost.SCALER_ARTIFACT_NAME, "preprocessing"),
        ("prediction.csv", "predictions"),
        ("summary.csv", "metrics"),
    ]
