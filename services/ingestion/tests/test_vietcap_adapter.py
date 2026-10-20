"""Parsing of the Vietcap adapter (network is mocked)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from services.ingestion.adapters.vietcap_adapter import VietcapAdapter

# 2026-07-07 and 2026-07-08 00:00 UTC, as Vietcap stamps daily bars.
T1, T2 = 1783382400, 1783468800
BODY = [
    {
        "symbol": "FPT",
        "o": [66000, 66500],
        "h": [67000, 66600],
        "l": [65800, 65400],
        "c": [66546.12, 65546.11],
        "v": [4574767, 6762590],
        "t": [str(T1), str(T2)],
    }
]


def _adapter_returning(
    body: object = None, error: Exception | None = None
) -> VietcapAdapter:
    adapter = VietcapAdapter()
    adapter._client = MagicMock()
    if error is not None:
        adapter._client.post.side_effect = error
    else:
        adapter._client.post.return_value.json.return_value = body
    return adapter


def test_prices_are_thousand_vnd_and_days_are_utc_midnight() -> None:
    candles = _adapter_returning(BODY).fetch_historical_ohlcv(
        "fpt", date(2026, 7, 7), date(2026, 7, 8)
    )

    assert [c.timestamp for c in candles] == [
        datetime(2026, 7, 7, tzinfo=timezone.utc),
        datetime(2026, 7, 8, tzinfo=timezone.utc),
    ]
    assert candles[1].close == pytest.approx(65.54611)
    assert candles[1].volume == 6762590
    assert candles[0].ticker_id == "FPT"


def test_days_outside_the_range_are_dropped() -> None:
    candles = _adapter_returning(BODY).fetch_historical_ohlcv(
        "FPT", date(2026, 7, 8), date(2026, 7, 8)
    )
    assert [c.timestamp.date() for c in candles] == [date(2026, 7, 8)]


@pytest.mark.parametrize(
    "adapter",
    [
        _adapter_returning(error=httpx.ConnectError("blocked")),
        _adapter_returning([]),
        _adapter_returning({"unexpected": "format"}),
    ],
)
def test_failures_return_no_candles(adapter: VietcapAdapter) -> None:
    assert (
        adapter.fetch_historical_ohlcv("FPT", date(2026, 7, 1), date(2026, 7, 8)) == []
    )


def test_only_daily_resolution() -> None:
    with pytest.raises(ValueError):
        _adapter_returning(BODY).fetch_historical_ohlcv(
            "FPT", date(2026, 7, 1), date(2026, 7, 8), resolution="1h"
        )
