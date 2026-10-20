"""
Tests cho Celery tasks (services/ingestion/tasks.py).

Mock `run_clean_and_store` để kiểm định logic ghi nhận job_log ở 3 trường hợp:
- Thành công (success)
- Lỗi dữ liệu/logic (failed)
- Lỗi kết nối DB tạm thời (retry)

Sử dụng mock `SessionLocal` trỏ về fixture `db` để chạy trên cùng 1 connection
tránh deadlock/relation locks trong môi trường test postgres.

Chạy:
    cd d:\\sources\\repos\\NCKH
    set PYTHONPATH=.
    pytest services/ingestion/tests/test_tasks.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from services.ingestion.tasks import clean_and_store_task, ingest_stocks_task
from shared.schemas.ohlcv import OHLCVCreate
from shared.db.repositories.market_repo import (
    clear_caches,
    ensure_exchange,
    ensure_symbol,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_caches()
    yield
    clear_caches()


@pytest.fixture(autouse=True)
def mock_session_local(db):
    """Mock SessionLocal trong services.ingestion.tasks để trả về fixture `db`.

    Tránh việc Celery task khởi tạo 1 connection/transaction mới độc lập gây
    deadlock với transaction hiện tại của pytest.
    """
    with patch("services.ingestion.tasks.SessionLocal", return_value=db):
        yield


class TestCleanAndStoreTask:
    """Đánh giá clean_and_store_task Celery."""

    @patch("services.ingestion.tasks.run_clean_and_store")
    def test_task_success_logs_correctly(
        self,
        mock_run_clean,
        db,
    ) -> None:
        """Task chạy thành công: ghi status='running' → status='success'."""
        # 1. Setup exchange, symbol và mock pipeline
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Test Exchange", "crypto", "UTC")
        ticker = f"SYM_{uuid.uuid4().hex[:6]}"
        sid = ensure_symbol(db, eid, ticker, "crypto", "binance")
        db.flush()

        mock_run_clean.return_value = {
            "input_rows": 10,
            "output_rows": 9,
            "duplicates_removed": 1,
            "missing_filled": 0,
            "outliers_flagged": 0,
        }

        # 2. Mock Celery request ID
        clean_and_store_task.request.id = "mock-celery-task-id-123"

        # 3. Gọi task đồng bộ
        result = clean_and_store_task(sid, "1h")

        # 4. Kiểm tra pipeline được gọi
        mock_run_clean.assert_called_once()
        assert result["output_rows"] == 9

        # 5. Kiểm định ghi nhận job_log trong DB
        job = db.execute(
            text(
                "SELECT job_type, status, celery_task_id, rows_affected, error_message "
                "FROM ops.job_log WHERE symbol_id = :sid"
            ),
            {"sid": sid},
        ).fetchone()

        assert job is not None
        assert job[0] == "clean"
        assert job[1] == "success"
        assert job[2] == "mock-celery-task-id-123"  # celery_task_id mapped
        assert job[3] == 9  # rows_affected mapped
        assert job[4] is None

    @patch("services.ingestion.tasks.run_clean_and_store")
    def test_task_failure_logs_correctly(
        self,
        mock_run_clean,
        db,
    ) -> None:
        """Task xảy ra lỗi logic: ghi status='failed' và lưu error message."""
        # 1. Setup symbol & mock pipeline raise exception
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Test Exchange", "crypto", "UTC")
        ticker = f"SYM_{uuid.uuid4().hex[:6]}"
        sid = ensure_symbol(db, eid, ticker, "crypto", "binance")
        db.flush()

        mock_run_clean.side_effect = ValueError("Logic cleaning failed test exception")
        clean_and_store_task.request.id = "mock-celery-task-id-999"

        # 2. Gọi task, kỳ vọng raise error
        with pytest.raises(ValueError):
            clean_and_store_task(sid, "1h")

        # 3. Kiểm định job_log ghi nhận trạng thái thất bại
        job = db.execute(
            text(
                "SELECT status, celery_task_id, error_message FROM ops.job_log "
                "WHERE symbol_id = :sid"
            ),
            {"sid": sid},
        ).fetchone()

        assert job is not None
        assert job[0] == "failed"
        assert job[1] == "mock-celery-task-id-999"
        assert "Logic cleaning failed test exception" in job[2]

    @patch("services.ingestion.tasks.run_clean_and_store")
    @patch("celery.app.task.Task.retry")
    def test_task_retry_on_operational_error(
        self,
        mock_retry,
        mock_run_clean,
        db,
    ) -> None:
        """Lỗi operational (DB temporary lock/timeout) → kích hoạt retry."""
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Test Exchange", "crypto", "UTC")
        ticker = f"SYM_{uuid.uuid4().hex[:6]}"
        sid = ensure_symbol(db, eid, ticker, "crypto", "binance")
        db.flush()

        # Giả lập lỗi DB OperationalError
        mock_run_clean.side_effect = OperationalError(
            "SELECT", {}, "Database connection temporary timeout"
        )
        clean_and_store_task.request.id = "mock-celery-task-id-retry"

        # Mock self.retry để tránh infinite loops
        mock_retry.side_effect = Exception("Retry triggered successfully")

        # Chạy task
        with pytest.raises(Exception) as excinfo:
            clean_and_store_task(sid, "1h")

        assert "Retry triggered successfully" in str(excinfo.value)
        mock_retry.assert_called_once()


class TestIngestStocksTask:
    """ingest_stocks_task với nguồn Vietcap (mạng được mock)."""

    @staticmethod
    def _job(db, ticker: str):
        return db.execute(
            text(
                "SELECT j.status, j.rows_affected, j.error_message "
                "FROM ops.job_log j JOIN market.symbol s ON s.id = j.symbol_id "
                "WHERE s.ticker = :ticker ORDER BY j.started_at DESC LIMIT 1"
            ),
            {"ticker": ticker},
        ).fetchone()

    @patch("services.ingestion.tasks.VietcapAdapter")
    def test_no_data_marks_job_failed(self, mock_adapter_cls, db) -> None:
        """Vietcap không trả dữ liệu → job 'failed' kèm lý do, không phải 'success'."""
        mock_adapter_cls.return_value.fetch_historical_ohlcv.return_value = []
        ticker = f"T{uuid.uuid4().hex[:6].upper()}"

        assert ingest_stocks_task([ticker], "1d") == 0

        job = self._job(db, ticker)
        assert job[0] == "failed"
        assert job[1] == 0
        assert "Vietcap" in job[2]

    @patch("services.ingestion.tasks.VietcapAdapter")
    def test_new_adjustment_refetches_whole_history(self, mock_adapter_cls, db) -> None:
        """Giá ngày trùng lệch > 0,5 % → lấy lại từ ngày đầu tiên đã lưu."""
        ticker = f"T{uuid.uuid4().hex[:6].upper()}"
        eid = ensure_exchange(db, "HOSE", "HOSE", "stock", "Asia/Ho_Chi_Minh")
        sid = ensure_symbol(db, eid, ticker, "stock", "vnstock")
        first, overlap = (
            datetime(2026, 7, 1, tzinfo=timezone.utc),
            datetime(2026, 10, 1, tzinfo=timezone.utc),
        )
        for ts in (first, overlap):
            db.execute(
                text(
                    "INSERT INTO market.ohlcv (symbol_id, timeframe, ts, open, high, low, close, volume) "
                    "VALUES (:sid, '1d', :ts, 100, 100, 100, 100, 1)"
                ),
                {"sid": sid, "ts": ts},
            )
        db.flush()

        def candle(ts: datetime, price: float) -> OHLCVCreate:
            return OHLCVCreate(
                timestamp=ts,
                ticker_id=ticker,
                resolution="1d",
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1,
            )

        adapter = mock_adapter_cls.return_value
        adapter.fetch_historical_ohlcv.side_effect = [
            [candle(overlap, 90.0)],  # recent window, re-adjusted by 10 %
            [candle(first, 90.0), candle(overlap, 90.0)],  # whole history
        ]

        ingest_stocks_task([ticker], "1d")

        assert adapter.fetch_historical_ohlcv.call_count == 2
        assert (
            adapter.fetch_historical_ohlcv.call_args.kwargs["start_date"]
            == first.date()
        )
        closes = (
            db.execute(
                text(
                    "SELECT close FROM market.ohlcv WHERE symbol_id = :sid ORDER BY ts"
                ),
                {"sid": sid},
            )
            .scalars()
            .all()
        )
        assert [float(c) for c in closes] == [90.0, 90.0]
        assert self._job(db, ticker)[0] == "success"
