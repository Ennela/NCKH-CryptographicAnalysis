"""
Tests cho pipeline processing (services/ingestion/app/pipeline.py).

Yêu cầu: DB test đã được khởi tạo và chạy thông qua cấu hình pytest (conftest.py).

Chạy:
    cd d:\\sources\\repos\\NCKH
    set PYTHONPATH=.
    pytest services/ingestion/tests/test_pipeline.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from services.ingestion.app.pipeline import run_clean_and_store
from shared.db.repositories.market_repo import (
    clear_caches,
    ensure_exchange,
    ensure_symbol,
    upsert_ohlcv_raw,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_caches()
    yield
    clear_caches()


def _insert_raw_candle(
    db,
    symbol_id: int,
    ts: datetime,
    close: float = 100.0,
    volume: float = 1000.0,
) -> None:
    """Helper chèn nhanh 1 candle thô vào market.ohlcv_raw."""
    upsert_ohlcv_raw(
        db,
        [{
            "symbol_id": symbol_id,
            "timeframe": "1d",
            "ts": ts,
            "open": Decimal(str(close * 0.99)),
            "high": Decimal(str(close * 1.01)),
            "low": Decimal(str(close * 0.98)),
            "close": Decimal(str(close)),
            "volume": Decimal(str(volume)),
            "source": "vnstock",
            "raw_payload": None,
        }],
    )


class TestPipelineCleanAndStore:
    """Đánh giá toàn bộ pipeline run_clean_and_store."""

    def test_run_success_with_new_data(self, db) -> None:
        """Đọc raw → clean → upsert clean → dq check thành công."""
        # 1. Setup exchange & symbol
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Test Exchange", "stock", "Asia/Ho_Chi_Minh")
        ticker = f"SYM_{uuid.uuid4().hex[:6]}"
        sid = ensure_symbol(db, eid, ticker, "stock", "vnstock")
        db.flush()

        # 2. Insert raw candles (Jan 15, Jan 17 - tạo gap ngày Jan 16)
        ts_mon = datetime(2024, 1, 15, tzinfo=timezone.utc)
        ts_wed = datetime(2024, 1, 17, tzinfo=timezone.utc)

        _insert_raw_candle(db, sid, ts_mon, close=100.0, volume=5000.0)
        _insert_raw_candle(db, sid, ts_wed, close=102.0, volume=6000.0)
        db.flush()

        # 3. Chạy pipeline
        report = run_clean_and_store(db, sid, "1d")

        # 4. Kiểm định kết quả report
        assert report["input_rows"] == 2
        # Cổ phiếu VN daily: có forward-fill cho thứ Ba 16 → output = 3
        assert report["output_rows"] == 3
        assert report["missing_filled"] == 1
        assert report["duplicates_removed"] == 0

        # 5. Kiểm định dữ liệu trong market.ohlcv
        candles = db.execute(
            text(
                "SELECT ts, close, volume FROM market.ohlcv "
                "WHERE symbol_id = :sid ORDER BY ts ASC"
            ),
            {"sid": sid},
        ).fetchall()

        assert len(candles) == 3
        # Mon
        assert candles[0][0] == ts_mon
        assert float(candles[0][1]) == 100.0
        # Tue (filled)
        assert candles[1][0] == ts_mon + timedelta(days=1)
        assert float(candles[1][1]) == 100.0  # fill từ Mon
        assert float(candles[1][2]) == 0.0  # volume = 0
        # Wed
        assert candles[2][0] == ts_wed

        # 6. Kiểm định data quality checks
        dq_check = db.execute(
            text(
                "SELECT check_name, passed, detail FROM ops.data_quality_check "
                "WHERE symbol_id = :sid AND check_name = 'cleaning_pipeline'"
            ),
            {"sid": sid},
        ).fetchone()

        assert dq_check is not None
        assert dq_check[1] is True  # passed (không có outlier)
        assert dq_check[2]["missing_filled"] == 1

    def test_run_twice_incremental(self, db) -> None:
        """Chạy pipeline lần 2 chỉ xử lý các raw candles mới chèn."""
        # 1. Setup
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Test Exchange", "stock", "Asia/Ho_Chi_Minh")
        ticker = f"SYM_{uuid.uuid4().hex[:6]}"
        sid = ensure_symbol(db, eid, ticker, "stock", "vnstock")

        # 2. Insert batch 1
        ts1 = datetime(2024, 1, 15, tzinfo=timezone.utc)
        _insert_raw_candle(db, sid, ts1, close=100.0)
        db.flush()

        # Run pipeline batch 1
        report1 = run_clean_and_store(db, sid, "1d")
        assert report1["input_rows"] == 1

        # 3. Insert batch 2 (sau mốc thời gian batch 1)
        ts2 = datetime(2024, 1, 16, tzinfo=timezone.utc)
        _insert_raw_candle(db, sid, ts2, close=101.0)
        db.flush()

        # Run pipeline batch 2
        report2 = run_clean_and_store(db, sid, "1d")
        # Batch 2 chỉ đọc raw candle mới (ts2 > ts1)
        assert report2["input_rows"] == 1
        assert report2["output_rows"] == 1

    def test_run_empty_no_new_data(self, db) -> None:
        """Không có raw mới → trả về summary rỗng."""
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Test Exchange", "stock", "Asia/Ho_Chi_Minh")
        ticker = f"SYM_{uuid.uuid4().hex[:6]}"
        sid = ensure_symbol(db, eid, ticker, "stock", "vnstock")

        report = run_clean_and_store(db, sid, "1d")
        assert report["input_rows"] == 0
        assert report["status"] == "no_new_data"

    def test_transaction_rollback_on_failure(self, db) -> None:
        """Nếu quy trình xảy ra lỗi (e.g. invalid symbol) -> rollback hoàn toàn."""
        # Chạy pipeline với symbol không tồn tại
        with pytest.raises(ValueError) as excinfo:
            run_clean_and_store(db, 99999, "1d")

        assert "Không tìm thấy symbol" in str(excinfo.value)
