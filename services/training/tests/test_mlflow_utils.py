from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import mlflow.sklearn as mlflow_sklearn
import mlflow.xgboost as mlflow_xgboost
import pytest

from services.training import mlflow_utils


class _PredictiveModel:
    def predict(self, values: object) -> object:
        return values


def _patch_run_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> SimpleNamespace:
    run = SimpleNamespace(info=SimpleNamespace(run_id="test-run-id"))
    monkeypatch.setattr(mlflow_utils, "init_mlflow", lambda: None)
    monkeypatch.setattr(mlflow_utils.mlflow, "set_experiment", lambda _: None)
    monkeypatch.setattr(
        mlflow_utils.mlflow,
        "start_run",
        lambda **_: nullcontext(run),
    )
    monkeypatch.setattr(mlflow_utils.mlflow, "log_params", lambda _: None)
    monkeypatch.setattr(mlflow_utils.mlflow, "log_metrics", lambda _: None)
    return run


def test_log_experiment_run_uses_native_xgboost_flavor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_run_dependencies(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_xgboost_log_model(model: Any, **kwargs: Any) -> None:
        captured["model"] = model
        captured.update(kwargs)

    monkeypatch.setattr(
        mlflow_xgboost,
        "log_model",
        fake_xgboost_log_model,
    )
    model = _PredictiveModel()

    run_id = mlflow_utils.log_experiment_run(
        experiment_name="ACB_1d_xgboost",
        run_name="xgboost_ACB_1d",
        params={"seed": 42},
        metrics={"rmse_test": 1.0},
        model=model,
        model_name_in_registry="ACB_1d_xgboost",
    )

    assert run_id == "test-run-id"
    assert captured == {
        "model": model,
        "artifact_path": "model",
        "registered_model_name": "ACB_1d_xgboost",
    }


def test_log_experiment_run_raises_when_model_logging_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_run_dependencies(monkeypatch)
    fallback_called = False

    def fail_xgboost_log_model(model: Any, **kwargs: Any) -> None:
        raise RuntimeError("model logging failed")

    def track_sklearn_fallback(model: Any, **kwargs: Any) -> None:
        nonlocal fallback_called
        fallback_called = True

    monkeypatch.setattr(
        mlflow_xgboost,
        "log_model",
        fail_xgboost_log_model,
    )
    monkeypatch.setattr(
        mlflow_sklearn,
        "log_model",
        track_sklearn_fallback,
    )

    with pytest.raises(RuntimeError, match="model logging failed"):
        mlflow_utils.log_experiment_run(
            experiment_name="ACB_1d_xgboost",
            run_name="xgboost_ACB_1d",
            params={"seed": 42},
            metrics={"rmse_test": 1.0},
            model=_PredictiveModel(),
            model_name_in_registry="ACB_1d_xgboost",
        )

    assert fallback_called is False
