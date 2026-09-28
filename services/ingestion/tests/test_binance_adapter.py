"""Timestamp handling of the Binance adapter (network is mocked)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.ingestion.adapters.binance_adapter import BinanceAdapter


def _adapter_with(candles: list[list[float]]) -> BinanceAdapter:
    adapter = BinanceAdapter.__new__(BinanceAdapter)
    adapter.exchange = MagicMock()
    adapter.exchange.fetch_ohlcv.return_value = candles
    return adapter


def test_candle_open_time_is_utc_regardless_of_host_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 2024-06-30 00:00:00 UTC — the open of a Binance daily candle.
    open_ms = 1_719_705_600_000
    if hasattr(time, "tzset"):
        # Simulate a Vietnamese host (UTC+7), where the old naive
        # fromtimestamp() produced 07:00 instead of 00:00.
        monkeypatch.setenv("TZ", "Asia/Ho_Chi_Minh")
        time.tzset()
    try:
        candles = _adapter_with(
            [[open_ms, 1.0, 2.0, 0.5, 1.5, 10.0]]
        ).fetch_historical_ohlcv("BTC/USDT", timeframe="1d")
    finally:
        if hasattr(time, "tzset"):
            monkeypatch.delenv("TZ", raising=False)
            time.tzset()

    assert candles[0].timestamp == datetime(2024, 6, 30, tzinfo=timezone.utc)
    assert candles[0].timestamp.utcoffset().total_seconds() == 0
