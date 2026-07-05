"""
Tests cho cleaning pipeline (services/ingestion/app/cleaning.py).

Chạy::

    cd d:\\sources\\repos\\NCKH
    set PYTHONPATH=.
    pytest services/ingestion/tests/test_cleaning.py -v

Test cases:
- Loại bản ghi trùng (dedup).
- Forward-fill missing sessions (stock daily, có giới hạn).
- Crypto KHÔNG fill missing.
- Phát hiện outlier rõ ràng bằng IQR.
- Pipeline tổng hợp (clean_ohlcv).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import pytest

from services.ingestion.app.cleaning import (
    CleaningConfig,
    CleaningReport,
    clean_ohlcv,
    deduplicate,
    detect_outliers,
    fill_missing_sessions,
    normalize_timezone,
)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Fixtures & Helpers                                                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


@pytest.fixture
def config() -> CleaningConfig:
    """Config cố định cho test — không đọc .env."""
    return CleaningConfig(
        CLEANING_FFILL_LIMIT=2,
        CLEANING_IQR_MULTIPLIER=1.5,
    )


def _make_row(
    symbol_id: int = 1,
    timeframe: str = "1d",
    ts: datetime | None = None,
    close: float = 100.0,
    volume: float = 1000.0,
    source: str = "binance",
) -> dict:
    """Tạo 1 bản ghi OHLCV giả lập."""
    if ts is None:
        ts = datetime(2024, 1, 15, tzinfo=timezone.utc)
    return {
        "symbol_id": symbol_id,
        "timeframe": timeframe,
        "ts": ts,
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": volume,
        "source": source,
    }


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Chuyển list[dict] → DataFrame, ép kiểu chuẩn."""
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Test: normalize_timezone                                               ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


class TestNormalizeTimezone:
    """Chuẩn hóa timezone → UTC."""

    def test_binance_already_utc(self) -> None:
        """Binance: giữ nguyên, chỉ đảm bảo tz-aware."""
        ts = datetime(2024, 6, 15, 10, 0)  # naive
        df = _make_df([_make_row(ts=ts, source="binance")])
        result = normalize_timezone(df, source="binance", timeframe="1h")
        assert result["ts"].dt.tz is not None  # now tz-aware

    def test_vnstock_daily_keeps_date(self) -> None:
        """VNStock daily: ngày giao dịch VN giữ nguyên (không trừ 7h)."""
        ts = datetime(2024, 6, 15, 0, 0, tzinfo=timezone.utc)
        df = _make_df([_make_row(ts=ts, source="vnstock")])
        result = normalize_timezone(df, source="vnstock", timeframe="1d")
        # Ngày phải vẫn là 15, không bị lùi về 14
        assert result["ts"].iloc[0].day == 15

    def test_vnstock_subdaily_subtracts_7h(self) -> None:
        """VNStock sub-daily: trừ 7h vì giờ VN bị gán nhầm UTC."""
        ts_vn = datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc)  # 14:00 VN
        df = _make_df([_make_row(ts=ts_vn, source="vnstock")])
        result = normalize_timezone(df, source="vnstock", timeframe="1h")
        # 14:00 VN → 07:00 UTC
        assert result["ts"].iloc[0].hour == 7


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Test: deduplicate                                                      ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


class TestDeduplicate:
    """Loại bản ghi trùng theo (symbol_id, timeframe, ts)."""

    def test_removes_duplicate_rows(self) -> None:
        """2 bản ghi cùng (sym=1, tf=1d, ts=Jan15) → giữ 1."""
        ts = datetime(2024, 1, 15, tzinfo=timezone.utc)
        rows = [
            _make_row(ts=ts, close=100),
            _make_row(ts=ts, close=101),  # trùng key
            _make_row(ts=ts + timedelta(days=1), close=102),
        ]
        df = _make_df(rows)
        result, removed = deduplicate(df)

        assert removed == 1
        assert len(result) == 2

    def test_no_duplicates_no_change(self) -> None:
        """Dữ liệu không trùng → không mất hàng nào."""
        rows = [
            _make_row(ts=datetime(2024, 1, 15, tzinfo=timezone.utc)),
            _make_row(ts=datetime(2024, 1, 16, tzinfo=timezone.utc)),
            _make_row(ts=datetime(2024, 1, 17, tzinfo=timezone.utc)),
        ]
        df = _make_df(rows)
        result, removed = deduplicate(df)

        assert removed == 0
        assert len(result) == 3

    def test_keeps_latest_ingested(self) -> None:
        """Nếu có ingested_at, giữ bản ghi mới nhất."""
        ts = datetime(2024, 1, 15, tzinfo=timezone.utc)
        rows = [
            {**_make_row(ts=ts, close=100), "ingested_at": datetime(2024, 1, 20, tzinfo=timezone.utc)},
            {**_make_row(ts=ts, close=200), "ingested_at": datetime(2024, 1, 21, tzinfo=timezone.utc)},
        ]
        df = _make_df(rows)
        result, removed = deduplicate(df)

        assert removed == 1
        assert len(result) == 1
        # Giữ bản ghi có ingested_at mới hơn (close=200)
        assert float(result.iloc[0]["close"]) == 200.0


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Test: fill_missing_sessions                                            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


class TestFillMissingSessions:
    """Forward-fill missing sessions cho stock daily."""

    def test_stock_fills_one_missing_business_day(self) -> None:
        """Thiếu 1 ngày giữa Mon–Wed → fill Tue bằng close của Mon."""
        rows = [
            # Mon 2024-01-15
            _make_row(ts=datetime(2024, 1, 15, tzinfo=timezone.utc), close=100, volume=5000),
            # Wed 2024-01-17 (Tue 16 thiếu)
            _make_row(ts=datetime(2024, 1, 17, tzinfo=timezone.utc), close=102, volume=6000),
        ]
        df = _make_df(rows)
        result, filled = fill_missing_sessions(df, "stock", "1d", ffill_limit=2)

        assert filled == 1
        assert len(result) == 3
        # Bản ghi fill Tue: close = Mon's close (100), volume = 0
        tue_row = result[result["ts"].dt.day == 16].iloc[0]
        assert float(tue_row["close"]) == 100.0
        assert float(tue_row["volume"]) == 0.0  # không giao dịch thật

    def test_stock_respects_ffill_limit(self) -> None:
        """Gap > limit → chỉ fill đúng limit phiên, bỏ phần còn lại."""
        rows = [
            # Mon 2024-01-15
            _make_row(ts=datetime(2024, 1, 15, tzinfo=timezone.utc), close=100),
            # Mon 2024-01-22 (gap: Tue16, Wed17, Thu18, Fri19 = 4 ngày > limit=2)
            _make_row(ts=datetime(2024, 1, 22, tzinfo=timezone.utc), close=105),
        ]
        df = _make_df(rows)
        result, filled = fill_missing_sessions(df, "stock", "1d", ffill_limit=2)

        # Chỉ fill Tue16 + Wed17 (2 ngày), Thu18 + Fri19 bị drop
        assert filled == 2
        assert len(result) == 4  # original 2 + filled 2

    def test_stock_no_fill_across_weekend(self) -> None:
        """Weekend (Sat-Sun) không phải business day → không tạo row."""
        rows = [
            # Fri 2024-01-19
            _make_row(ts=datetime(2024, 1, 19, tzinfo=timezone.utc), close=100),
            # Mon 2024-01-22
            _make_row(ts=datetime(2024, 1, 22, tzinfo=timezone.utc), close=102),
        ]
        df = _make_df(rows)
        result, filled = fill_missing_sessions(df, "stock", "1d", ffill_limit=2)

        # Fri → Mon: weekend tự nhiên, không có gap
        assert filled == 0
        assert len(result) == 2

    def test_crypto_no_fill(self) -> None:
        """Crypto: KHÔNG forward-fill (24/7, missing = lỗi thật)."""
        rows = [
            _make_row(ts=datetime(2024, 1, 15, 0, tzinfo=timezone.utc), close=100),
            # Gap: 01:00 thiếu
            _make_row(ts=datetime(2024, 1, 15, 2, tzinfo=timezone.utc), close=102),
        ]
        df = _make_df(rows)
        result, filled = fill_missing_sessions(df, "crypto", "1h", ffill_limit=3)

        assert filled == 0
        assert len(result) == 2

    def test_stock_hourly_no_fill(self) -> None:
        """Stock hourly (nếu có): chỉ fill daily, không fill hourly."""
        rows = [
            _make_row(ts=datetime(2024, 1, 15, 9, tzinfo=timezone.utc), timeframe="1h"),
            _make_row(ts=datetime(2024, 1, 15, 11, tzinfo=timezone.utc), timeframe="1h"),
        ]
        df = _make_df(rows)
        result, filled = fill_missing_sessions(df, "stock", "1h", ffill_limit=3)

        assert filled == 0


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Test: detect_outliers                                                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


class TestDetectOutliers:
    """Phát hiện outlier bằng IQR."""

    def test_flags_clear_close_outlier(self) -> None:
        """Close bất thường (gấp 10x) → is_outlier = True."""
        rows = [
            _make_row(
                ts=datetime(2024, 1, i + 1, tzinfo=timezone.utc),
                close=100 + i * 0.5,
                volume=1000,
            )
            for i in range(20)
        ]
        # Thêm outlier: close = 999 (vs bình thường ~ 100–110)
        rows.append(
            _make_row(
                ts=datetime(2024, 1, 21, tzinfo=timezone.utc),
                close=999,
                volume=1000,
            )
        )
        df = _make_df(rows)
        result, count = detect_outliers(df, iqr_multiplier=1.5)

        assert count >= 1
        outlier_rows = result[result["close"].astype(float) == 999.0]
        assert len(outlier_rows) == 1
        assert outlier_rows.iloc[0]["is_outlier"] == True  # noqa: E712 (numpy bool)

    def test_flags_volume_outlier(self) -> None:
        """Volume bất thường (gấp 100x) → is_outlier = True."""
        rows = [
            _make_row(
                ts=datetime(2024, 1, i + 1, tzinfo=timezone.utc),
                close=100,
                volume=1000,
            )
            for i in range(20)
        ]
        # Thêm outlier volume
        rows.append(
            _make_row(
                ts=datetime(2024, 1, 21, tzinfo=timezone.utc),
                close=100,
                volume=999_999,
            )
        )
        df = _make_df(rows)
        result, count = detect_outliers(df, iqr_multiplier=1.5)

        assert count >= 1

    def test_no_outliers_in_uniform_data(self) -> None:
        """Dữ liệu đều: không có outlier."""
        rows = [
            _make_row(
                ts=datetime(2024, 1, i + 1, tzinfo=timezone.utc),
                close=100 + i * 0.1,
                volume=1000,
            )
            for i in range(20)
        ]
        df = _make_df(rows)
        result, count = detect_outliers(df, iqr_multiplier=1.5)

        assert count == 0
        assert result["is_outlier"].sum() == 0

    def test_skips_small_groups(self) -> None:
        """Nhóm < min_group_size → bỏ qua (IQR vô nghĩa)."""
        rows = [
            _make_row(ts=datetime(2024, 1, i + 1, tzinfo=timezone.utc), close=100)
            for i in range(3)
        ]
        # Thêm giá trị cực đoan nhưng nhóm chỉ có 4 rows
        rows.append(
            _make_row(ts=datetime(2024, 1, 5, tzinfo=timezone.utc), close=999)
        )
        df = _make_df(rows)
        result, count = detect_outliers(df, iqr_multiplier=1.5, min_group_size=10)

        assert count == 0  # nhóm quá nhỏ → bỏ qua


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Test: clean_ohlcv (pipeline tổng hợp)                                 ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


class TestCleanOhlcv:
    """Pipeline tổng hợp: timezone + dedup + fill + outlier."""

    def test_crypto_pipeline_dedup_and_outlier(self, config: CleaningConfig) -> None:
        """Crypto: dedup + outlier detection, không fill."""
        rows = [
            _make_row(ts=datetime(2024, 1, i + 1, tzinfo=timezone.utc), close=100 + i)
            for i in range(15)
        ]
        # Thêm duplicate
        rows.append(_make_row(ts=datetime(2024, 1, 1, tzinfo=timezone.utc), close=999))
        df = _make_df(rows)
        result, report = clean_ohlcv(df, "crypto", config)

        assert report.input_rows == 16
        assert report.duplicates_removed == 1
        assert report.missing_filled == 0  # crypto: no fill
        assert report.output_rows == 15
        assert "is_outlier" in result.columns

    def test_stock_pipeline_full(self, config: CleaningConfig) -> None:
        """Stock: dedup + fill missing + outlier detection."""
        rows = [
            # Mon 2024-01-15
            _make_row(ts=datetime(2024, 1, 15, tzinfo=timezone.utc), close=100, source="vnstock"),
            # Skip Tue 16
            # Wed 2024-01-17
            _make_row(ts=datetime(2024, 1, 17, tzinfo=timezone.utc), close=102, source="vnstock"),
        ]
        # Thêm đủ rows để outlier detection hoạt động
        for i in range(18, 31):
            day = datetime(2024, 1, i, tzinfo=timezone.utc)
            # Chỉ thêm ngày business day (bỏ weekend)
            if day.weekday() < 5:
                rows.append(
                    _make_row(ts=day, close=100 + (i - 15) * 0.5, source="vnstock")
                )

        df = _make_df(rows)
        result, report = clean_ohlcv(df, "stock", config)

        assert report.input_rows == len(df)
        assert report.duplicates_removed == 0
        assert report.missing_filled == 1  # Tue 16 filled
        assert report.output_rows > report.input_rows  # thêm row do fill
        assert "is_outlier" in result.columns

    def test_empty_dataframe(self, config: CleaningConfig) -> None:
        """DataFrame rỗng → report rỗng, không crash."""
        df = pd.DataFrame()
        result, report = clean_ohlcv(df, "crypto", config)

        assert report.input_rows == 0
        assert report.output_rows == 0
        assert report.duplicates_removed == 0

    def test_report_to_dict(self, config: CleaningConfig) -> None:
        """CleaningReport.to_dict() trả format đúng cho JSONB."""
        report = CleaningReport(
            input_rows=100,
            output_rows=98,
            duplicates_removed=2,
            missing_filled=5,
            outliers_flagged=3,
        )
        d = report.to_dict()

        assert isinstance(d, dict)
        assert d["input_rows"] == 100
        assert d["outliers_flagged"] == 3
        assert len(d) == 5
