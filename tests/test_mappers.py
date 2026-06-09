import pandas as pd
from decimal import Decimal
from datetime import datetime, timezone
from shared.db.mappers import (
    normalize_timeframe,
    split_crypto_pair,
    map_binance_klines_batch,
    map_vnstock_df_batch,
)


def test_normalize_timeframe() -> None:
    """Kiểm tra chuẩn hóa interval string."""
    assert normalize_timeframe("1h") == "1h"
    assert normalize_timeframe("1H") == "1h"
    assert normalize_timeframe(" 1d ") == "1d"
    assert normalize_timeframe("1D") == "1d"
    assert normalize_timeframe("invalid") is None


def test_split_crypto_pair() -> None:
    """Kiểm tra tách base/quote asset từ symbol."""
    assert split_crypto_pair("BTCUSDT") == ("BTC", "USDT")
    assert split_crypto_pair("ETHBTC") == ("ETH", "BTC")
    assert split_crypto_pair("INVALID") == (None, None)


def test_map_binance_klines_batch() -> None:
    """Kiểm tra map klines batch từ Binance và bộ lọc bản ghi lỗi."""
    # Kline format: [open_time, open, high, low, close, volume, close_time, quote_vol, trades, ...]
    valid_kline = [
        1609459200000,
        "29000.0",
        "30000.0",
        "28000.0",
        "29500.0",
        "100.0",
        1609462799999,
        "2950000.0",
        500,
        "50.0",
        "1475000.0",
        "0",
    ]
    invalid_high_low = [
        1609459200000,
        "29000.0",
        "28000.0",
        "30000.0",
        "29500.0",
        "100.0",
        1609462799999,
        "2950000.0",
        500,
        "50.0",
        "1475000.0",
        "0",
    ]
    invalid_negative = [
        1609459200000,
        "-29000.0",
        "30000.0",
        "28000.0",
        "29500.0",
        "100.0",
        1609462799999,
        "2950000.0",
        500,
        "50.0",
        "1475000.0",
        "0",
    ]

    raw_rows, clean_rows = map_binance_klines_batch(
        symbol_id=1,
        timeframe="1h",
        data=[valid_kline, invalid_high_low, invalid_negative],
    )

    # Raw rows must preserve everything that successfully parsed
    assert len(raw_rows) == 3
    # Clean rows must only contain the valid one (no high < low, no negative prices)
    assert len(clean_rows) == 1
    assert clean_rows[0]["high"] == Decimal("30000.0")
    assert clean_rows[0]["low"] == Decimal("28000.0")


def test_map_vnstock_df_batch() -> None:
    """Kiểm tra map batch DataFrame từ Vnstock và bộ lọc bản ghi lỗi."""
    data = {
        "time": [
            datetime(2021, 1, 1, tzinfo=timezone.utc),
            datetime(2021, 1, 2, tzinfo=timezone.utc),
            datetime(2021, 1, 3, tzinfo=timezone.utc),
        ],
        "open": [100.0, 105.0, -99.0],
        "high": [110.0, 102.0, 100.0],  # Second row has high < low (102 < 103)
        "low": [95.0, 103.0, 95.0],
        "close": [105.0, 104.0, 98.0],
        "volume": [1000.0, 1500.0, 2000.0],
    }
    df = pd.DataFrame(data)

    raw_rows, clean_rows = map_vnstock_df_batch(symbol_id=2, timeframe="1d", df=df)

    # Raw rows must keep all parsed rows
    assert len(raw_rows) == 3
    # Clean rows must filter out high < low (row index 1) and negative open (row index 2)
    assert len(clean_rows) == 1
    assert clean_rows[0]["open"] == Decimal("100.0")
    assert clean_rows[0]["high"] == Decimal("110.0")
    assert clean_rows[0]["low"] == Decimal("95.0")
