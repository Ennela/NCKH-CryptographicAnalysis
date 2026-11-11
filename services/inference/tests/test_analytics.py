"""Tests for the data-analytics helpers and endpoints (DB is stubbed)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main
from analytics import compute_indicators, expected_bar_count, profile_quality
from shared.config.settings import settings
from shared.db.session import get_db

API_HEADERS = {"X-API-Key": settings.API_KEY_SECRET}
START = datetime(2025, 1, 6, tzinfo=timezone.utc)  # a Monday


def _frame(count: int, step: timedelta = timedelta(days=1)) -> pd.DataFrame:
    """Chronological OHLCV frame with a gentle up-trend."""
    rows = []
    for index in range(count):
        close = 100.0 + 0.5 * index + (1.0 if index % 2 else -1.0)
        rows.append(
            {
                "ts": pd.Timestamp(START + step * index),
                "open": close - 0.2,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000.0 + index,
            }
        )
    return pd.DataFrame(rows)


# ── Pure helpers ──────────────────────────────────────────────────────────────


def test_indicators_hide_warmup_and_are_causal() -> None:
    frame = _frame(120)
    full = compute_indicators(frame)
    assert full["sma_20"].iloc[:19].isna().all()
    assert full["sma_50"].iloc[:49].isna().all()
    assert full["rsi_14"].iloc[:14].isna().all()
    assert full["macd"].iloc[:26].isna().all()
    assert full["sma_20"].iloc[19] == pytest.approx(frame["close"].iloc[:20].mean())

    # Appending future bars must not change any past indicator value.
    prefix = compute_indicators(frame.iloc[:80])
    for column in ("sma_20", "sma_50", "rsi_14", "macd", "macd_signal"):
        np.testing.assert_allclose(
            prefix[column].to_numpy(), full[column].iloc[:80].to_numpy(), equal_nan=True
        )


def test_macd_hist_is_line_minus_signal() -> None:
    result = compute_indicators(_frame(80)).dropna()
    np.testing.assert_allclose(
        result["macd_hist"], result["macd"] - result["macd_signal"]
    )


def test_expected_bars_by_calendar() -> None:
    monday, next_friday = pd.Timestamp(START), pd.Timestamp(START + timedelta(days=11))
    assert expected_bar_count(monday, next_friday, "stock", "1d") == 10
    assert expected_bar_count(monday, next_friday, "crypto", "1d") == 12
    assert (
        expected_bar_count(monday, monday + pd.Timedelta(hours=5), "crypto", "1h") == 6
    )


def test_quality_profile_counts_gaps_and_anomalies() -> None:
    frame = _frame(30)  # daily bars incl. weekends → stock calendar has fewer
    crypto = profile_quality(frame, "crypto", "1d")
    assert crypto.bars == 30
    assert crypto.missing_bars == 0
    assert crypto.completeness_pct == 100.0

    gapped = frame.drop(index=[5, 6, 7]).reset_index(drop=True)
    gapped.loc[3, "volume"] = 0.0
    gapped.loc[4, "high"] = gapped.loc[4, "close"] - 5.0  # high below the body
    gapped.loc[10, "close"] = gapped.loc[10, "close"] * 3  # price spike
    profile = profile_quality(gapped, "crypto", "1d")
    assert profile.missing_bars == 3
    assert profile.zero_volume_bars == 1
    assert profile.invalid_ohlc_bars >= 1
    assert profile.return_outliers >= 1


def test_quality_profile_empty_frame() -> None:
    profile = profile_quality(_frame(0), "stock", "1d")
    assert profile.bars == 0 and profile.first_ts is None


# ── Endpoints ─────────────────────────────────────────────────────────────────


class _Row(dict):
    """Minimal stand-in for a SQLAlchemy Row (attribute + _mapping access)."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    @property
    def _mapping(self) -> dict[str, Any]:
        return dict(self)


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Any]:
        return self._rows


class _AnalyticsSession:
    """Route the analytics SQL to canned rows."""

    def __init__(self, ohlcv: pd.DataFrame) -> None:
        self.ohlcv = ohlcv

    def _ohlcv_rows(self, limit: int) -> list[tuple[Any, ...]]:
        rows = list(self.ohlcv.itertuples(index=False, name=None))
        return list(reversed(rows))[:limit]

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
        sql = str(statement)
        params = params or {}
        if "WITH base AS" in sql:
            return _Result([_stats_row()])
        if "FROM ops.data_quality_check" in sql:
            return _Result(
                [
                    _Row(
                        ticker="ACB",
                        checked_at=START,
                        passed=True,
                        detail={"duplicates_removed": 2, "missing_filled": 1},
                    )
                ]
            )
        if "SELECT DISTINCT s.id" in sql:
            return _Result([_Row(id=1, ticker="ACB", asset_class="stock")])
        if "FROM ops.job_log" in sql:
            return _Result([_job_row()])
        if "FROM market.symbol" in sql:
            return _Result([(1, "stock")] if params.get("ticker") == "ACB" else [])
        if "FROM market.ohlcv" in sql:
            return _Result(self._ohlcv_rows(int(params["limit"])))
        raise AssertionError(f"Unexpected SQL in test: {sql}")


def _stats_row() -> _Row:
    return _Row(
        symbol_id=1,
        ticker="ACB",
        asset_class="stock",
        bars=500,
        first_ts=START,
        last_ts=START + timedelta(days=700),
        lowest_low=18.5,
        highest_high=29.9,
        mean_close=24.0,
        std_close=2.1,
        first_close=20.0,
        last_close=25.0,
        mean_volume=5_000_000.0,
        max_volume=20_000_000.0,
        return_std=0.015,
    )


def _job_row() -> _Row:
    return _Row(
        job_type="clean",
        job_name="clean_and_store_1_1d",
        status="success",
        ticker="ACB",
        timeframe="1d",
        started_at=START,
        finished_at=START + timedelta(seconds=2),
        duration_ms=2000,
        rows_affected=5,
        error_message=None,
    )


@pytest.fixture()
def client():
    main.app.dependency_overrides[get_db] = lambda: _AnalyticsSession(_frame(200))
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def test_stats_endpoint_derives_change_and_volatility(client: TestClient) -> None:
    response = client.get("/api/v1/stats?timeframe=1d", headers=API_HEADERS)
    assert response.status_code == 200
    (row,) = response.json()
    assert row["ticker"] == "ACB"
    assert row["change_pct"] == pytest.approx(25.0)
    assert row["return_std_pct"] == pytest.approx(1.5)
    # Latest RSI/MACD equal the analysis chart's values on the same history.
    expected = compute_indicators(_frame(200)).iloc[-1]
    assert row["rsi_14"] == pytest.approx(expected["rsi_14"])
    assert row["macd"] == pytest.approx(expected["macd"])
    assert row["macd_signal"] == pytest.approx(expected["macd_signal"])


def test_indicators_endpoint_returns_warm_window(client: TestClient) -> None:
    response = client.get(
        "/api/v1/indicators?ticker=acb&timeframe=1d&limit=100", headers=API_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "ACB"
    assert len(body["points"]) == 100
    # 60 warm-up bars were loaded before the window, so SMA 50 is ready.
    assert body["points"][0]["sma_50"] is not None
    assert body["points"][0]["ts"] < body["points"][-1]["ts"]


def test_indicators_unknown_ticker_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/indicators?ticker=ZZZ", headers=API_HEADERS)
    assert response.status_code == 404


def test_data_quality_endpoint_merges_pipeline_report(client: TestClient) -> None:
    response = client.get("/api/v1/data-quality?timeframe=1d", headers=API_HEADERS)
    assert response.status_code == 200
    (report,) = response.json()
    assert report["ticker"] == "ACB"
    assert report["bars"] == 200
    assert report["last_pipeline_check"]["detail"]["duplicates_removed"] == 2


def test_jobs_endpoint_maps_job_log(client: TestClient) -> None:
    response = client.get("/api/v1/jobs?limit=5", headers=API_HEADERS)
    assert response.status_code == 200
    (job,) = response.json()
    assert job["status"] == "success"
    assert job["ticker"] == "ACB"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/stats",
        "/api/v1/data-quality",
        "/api/v1/jobs",
        "/api/v1/indicators?ticker=ACB",
    ],
)
def test_analytics_endpoints_require_api_key(client: TestClient, path: str) -> None:
    response = client.get(path, headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_analytics_rejects_bad_timeframe(client: TestClient) -> None:
    response = client.get("/api/v1/stats?timeframe=5m", headers=API_HEADERS)
    assert response.status_code == 400
