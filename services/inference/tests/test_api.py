"""API tests for the inference service (DB, Redis and MLflow are stubbed)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main
from model_loader import ModelLoadError, ModelNotRegisteredError
from shared.config.settings import settings
from shared.db.session import get_db

API_HEADERS = {"X-API-Key": settings.API_KEY_SECRET}


class _FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def first(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _FakeSession:
    """Route raw-SQL queries from main.py to canned rows."""

    def __init__(
        self,
        symbol_row: tuple[Any, ...] | None,
        ohlcv_rows: list[tuple[Any, ...]],
        model_version_row: tuple[Any, ...] | None = None,
    ) -> None:
        self.symbol_row = symbol_row
        self.ohlcv_rows = ohlcv_rows
        self.model_version_row = model_version_row
        self.inserted: list[dict[str, Any]] = []
        self.committed = False

    def execute(self, statement: Any, params: dict[str, Any] | None = None):
        sql = str(statement)
        if "FROM market.symbol" in sql:
            return _FakeResult([self.symbol_row] if self.symbol_row else [])
        if "FROM market.ohlcv" in sql:
            limit = (params or {}).get("limit", len(self.ohlcv_rows))
            newest_first = list(reversed(self.ohlcv_rows))[: int(limit)]
            return _FakeResult(newest_first)
        if "FROM ml.model_version" in sql:
            return _FakeResult(
                [self.model_version_row] if self.model_version_row else []
            )
        if "INSERT INTO ml.prediction" in sql:
            self.inserted.append(dict(params or {}))
            return _FakeResult([])
        raise AssertionError(f"Unexpected SQL in test: {sql}")

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass


def _ohlcv_rows(count: int = 120) -> list[tuple[Any, ...]]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        close = 100.0 + 0.2 * index
        rows.append(
            (
                start + timedelta(days=index),
                close - 0.1,
                close + 0.4,
                close - 0.4,
                close,
                1_000.0,
            )
        )
    return rows


class _StubPredictor:
    def __init__(self, values: list[float]) -> None:
        self.values = values
        self.calls: list[tuple[int, int]] = []

    def predict_steps(self, history: pd.DataFrame, steps: int) -> list[float]:
        self.calls.append((len(history), steps))
        return self.values[:steps]


def _loaded_model(predictor: _StubPredictor) -> SimpleNamespace:
    return SimpleNamespace(
        predictor=predictor,
        registry_name="ACB_1d_xgboost",
        version=3,
        run_id="run-abc",
    )


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main.redis_cache, "client", None)
    monkeypatch.setattr(main.redis_cache, "get", lambda key: None)
    monkeypatch.setattr(main.redis_cache, "set", lambda *args, **kwargs: True)
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def _override_db(session: _FakeSession) -> None:
    main.app.dependency_overrides[get_db] = lambda: session


def test_predict_returns_real_predictor_output(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _FakeSession(symbol_row=(7, "stock"), ohlcv_rows=_ohlcv_rows())
    _override_db(session)
    predictor = _StubPredictor([111.0, 112.0, 113.0])
    monkeypatch.setattr(
        main.model_loader, "load", lambda *args: _loaded_model(predictor)
    )

    response = client.post(
        "/api/v1/predict",
        headers=API_HEADERS,
        json={"ticker_id": "acb", "model_name": "xgboost", "steps": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ticker_id"] == "ACB"
    assert body["model_name"] == "xgboost"
    values = [item["predicted_value"] for item in body["predictions"]]
    assert values == [111.0, 112.0, 113.0]

    # Stock without explicit timeframe -> 1d spacing after the last bar.
    last_bar = _ohlcv_rows()[-1][0]
    target_times = [
        datetime.fromisoformat(item["target_time"]) for item in body["predictions"]
    ]
    assert target_times[0] == last_bar + timedelta(days=1)
    assert target_times[2] - target_times[1] == timedelta(days=1)
    assert predictor.calls == [(120, 3)]


def test_predict_respects_explicit_timeframe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _FakeSession(symbol_row=(9, "crypto"), ohlcv_rows=_ohlcv_rows())
    _override_db(session)
    captured: dict[str, Any] = {}

    def fake_load(ticker: str, timeframe: str, model_name: str) -> SimpleNamespace:
        captured.update(ticker=ticker, timeframe=timeframe, model_name=model_name)
        return _loaded_model(_StubPredictor([1.0]))

    monkeypatch.setattr(main.model_loader, "load", fake_load)

    response = client.post(
        "/api/v1/predict",
        headers=API_HEADERS,
        json={
            "ticker_id": "BTC/USDT",
            "model_name": "random_forest",
            "steps": 1,
            "timeframe": "1d",
        },
    )

    assert response.status_code == 200
    assert captured == {
        "ticker": "BTCUSDT",
        "timeframe": "1d",
        "model_name": "random_forest",
    }


def test_predict_unknown_ticker_is_404(client: TestClient) -> None:
    _override_db(_FakeSession(symbol_row=None, ohlcv_rows=[]))
    response = client.post(
        "/api/v1/predict",
        headers=API_HEADERS,
        json={"ticker_id": "NOPE", "model_name": "xgboost", "steps": 1},
    )
    assert response.status_code == 404


def test_predict_unregistered_model_is_503_without_mock_fallback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _override_db(_FakeSession(symbol_row=(7, "stock"), ohlcv_rows=_ohlcv_rows()))

    def raise_not_registered(*args: Any) -> None:
        raise ModelNotRegisteredError("Model 'ACB_1d_gru' is not registered")

    monkeypatch.setattr(main.model_loader, "load", raise_not_registered)
    response = client.post(
        "/api/v1/predict",
        headers=API_HEADERS,
        json={"ticker_id": "ACB", "model_name": "gru", "steps": 2},
    )
    assert response.status_code == 503
    assert "not registered" in response.json()["detail"]


def test_predict_mlflow_down_is_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _override_db(_FakeSession(symbol_row=(7, "stock"), ohlcv_rows=_ohlcv_rows()))

    def raise_load_error(*args: Any) -> None:
        raise ModelLoadError("Cannot reach MLflow Registry")

    monkeypatch.setattr(main.model_loader, "load", raise_load_error)
    response = client.post(
        "/api/v1/predict",
        headers=API_HEADERS,
        json={"ticker_id": "ACB", "model_name": "arima", "steps": 2},
    )
    assert response.status_code == 503


def test_predict_rejects_lstm_and_accepts_random_forest(client: TestClient) -> None:
    response = client.post(
        "/api/v1/predict",
        headers=API_HEADERS,
        json={"ticker_id": "ACB", "model_name": "lstm", "steps": 1},
    )
    assert response.status_code == 422


def test_predict_cache_hit_skips_model_loading(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _override_db(_FakeSession(symbol_row=(7, "stock"), ohlcv_rows=_ohlcv_rows()))
    cached = {
        "ticker_id": "ACB",
        "model_name": "xgboost",
        "prediction_time": "2026-07-26T00:00:00Z",
        "predictions": [
            {"target_time": "2026-07-27T00:00:00Z", "predicted_value": 99.0}
        ],
    }
    monkeypatch.setattr(main.redis_cache, "get", lambda key: cached)

    def fail_load(*args: Any) -> None:
        raise AssertionError("model_loader.load must not be called on cache hit")

    monkeypatch.setattr(main.model_loader, "load", fail_load)
    response = client.post(
        "/api/v1/predict",
        headers=API_HEADERS,
        json={"ticker_id": "ACB", "model_name": "xgboost", "steps": 1},
    )
    assert response.status_code == 200
    assert response.json()["predictions"][0]["predicted_value"] == 99.0


def test_predict_persists_when_model_version_row_exists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _FakeSession(
        symbol_row=(7, "stock"),
        ohlcv_rows=_ohlcv_rows(),
        model_version_row=(41,),
    )
    _override_db(session)
    monkeypatch.setattr(
        main.model_loader,
        "load",
        lambda *args: _loaded_model(_StubPredictor([111.0, 112.0])),
    )

    response = client.post(
        "/api/v1/predict",
        headers=API_HEADERS,
        json={"ticker_id": "ACB", "model_name": "xgboost", "steps": 2},
    )

    assert response.status_code == 200
    assert session.committed is True
    assert [row["horizon"] for row in session.inserted] == [1, 2]
    assert [row["y_pred"] for row in session.inserted] == [111.0, 112.0]
    assert all(row["model_version_id"] == 41 for row in session.inserted)
    assert all(row["feature_asof_ts"] < row["target_ts"] for row in session.inserted)


def test_invalid_api_key_is_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/predict",
        headers={"X-API-Key": "wrong-key"},
        json={"ticker_id": "ACB", "model_name": "xgboost", "steps": 1},
    )
    assert response.status_code == 401


# ── /api/v1/models ─────────────────────────────────────────────────


class _FakeMlflowClient:
    registered: list[SimpleNamespace] = []
    runs: dict[str, SimpleNamespace] = {}

    def search_registered_models(self) -> list[SimpleNamespace]:
        return self.registered

    def get_run(self, run_id: str) -> SimpleNamespace:
        return self.runs[run_id]


def test_models_lists_registry_content(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    version = SimpleNamespace(version="3", run_id="run-1", current_stage="None")
    _FakeMlflowClient.registered = [
        SimpleNamespace(
            name="ACB_1d_xgboost",
            latest_versions=[version],
            last_updated_timestamp=1_750_000_000_000,
        )
    ]
    _FakeMlflowClient.runs = {
        "run-1": SimpleNamespace(
            data=SimpleNamespace(metrics={"mae": 0.4, "rmse": 0.6, "mape_pct": 1.2})
        )
    }
    monkeypatch.setattr(main, "MlflowClient", _FakeMlflowClient)

    response = client.get("/api/v1/models", headers=API_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body[0]["model_name"] == "ACB_1d_xgboost"
    assert body[0]["version"] == "3"
    assert body[0]["status"] == "active"
    assert body[0]["metrics"] == {"mae": 0.4, "rmse": 0.6, "mape": 1.2}


def test_models_maps_mlflow_outage_to_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mlflow.exceptions import MlflowException

    class _DownClient:
        def search_registered_models(self):
            raise MlflowException("connection refused")

    monkeypatch.setattr(main, "MlflowClient", _DownClient)
    response = client.get("/api/v1/models", headers=API_HEADERS)
    assert response.status_code == 503


# ── /api/v1/explain ────────────────────────────────────────────────


def test_explain_serves_shap_artifact(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    payload = {
        "method": "shap_tree_explainer",
        "features": [
            {"feature": "rsi", "importance": 0.5, "mean_abs_shap": 0.31},
            {"feature": "macd", "importance": 0.2, "mean_abs_shap": 0.11},
        ],
        "generated_at": "2026-07-26T00:00:00+00:00",
    }
    artifact = tmp_path / "feature_importance.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(main.model_loader, "latest_version", lambda name: (3, "run-1"))
    monkeypatch.setattr(
        main.mlflow.artifacts,
        "download_artifacts",
        lambda run_id, artifact_path: str(artifact),
    )

    response = client.get(
        "/api/v1/explain",
        headers=API_HEADERS,
        params={"ticker": "acb", "timeframe": "1d", "model_name": "xgboost"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "ACB"
    assert body["method"] == "shap_tree_explainer"
    assert [f["feature"] for f in body["features"]] == ["rsi", "macd"]
    assert body["features"][0]["mean_abs_shap"] == pytest.approx(0.31)


def test_explain_missing_artifact_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main.model_loader, "latest_version", lambda name: (3, "run-1"))

    def raise_download(*args: Any, **kwargs: Any) -> None:
        raise OSError("artifact not found")

    monkeypatch.setattr(main.mlflow.artifacts, "download_artifacts", raise_download)
    response = client.get(
        "/api/v1/explain", headers=API_HEADERS, params={"ticker": "ACB"}
    )
    assert response.status_code == 404
    assert "explainability artifact" in response.json()["detail"]


def test_explain_unregistered_model_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_not_registered(name: str) -> None:
        raise ModelNotRegisteredError(f"Model '{name}' is not registered")

    monkeypatch.setattr(main.model_loader, "latest_version", raise_not_registered)
    response = client.get(
        "/api/v1/explain", headers=API_HEADERS, params={"ticker": "ACB"}
    )
    assert response.status_code == 404


def test_explain_rejects_bad_timeframe(client: TestClient) -> None:
    response = client.get(
        "/api/v1/explain",
        headers=API_HEADERS,
        params={"ticker": "ACB", "timeframe": "5m"},
    )
    assert response.status_code == 400


def test_predict_numpy_values_serialize(client: TestClient, monkeypatch) -> None:
    """Predictors return numpy floats internally — response must stay JSON-safe."""
    _override_db(_FakeSession(symbol_row=(7, "stock"), ohlcv_rows=_ohlcv_rows()))
    monkeypatch.setattr(
        main.model_loader,
        "load",
        lambda *args: _loaded_model(_StubPredictor([float(np.float64(55.5))])),
    )
    response = client.post(
        "/api/v1/predict",
        headers=API_HEADERS,
        json={"ticker_id": "ACB", "model_name": "xgboost", "steps": 1},
    )
    assert response.status_code == 200
    assert response.json()["predictions"][0]["predicted_value"] == 55.5
