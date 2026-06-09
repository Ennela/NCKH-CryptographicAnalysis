"""
Tests cho shared.db.repositories.market_repo — idempotent, schema đúng.

Yêu cầu: DB test đã apply ``infra/postgres/init.sql`` (có market/ml/ops schema).
Dùng pattern BEGIN + ROLLBACK để không ảnh hưởng dữ liệu thật.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from shared.db.repositories.market_repo import (
    clear_caches,
    ensure_exchange,
    ensure_symbol,
    log_job,
    record_dq_check,
    update_job,
    upsert_ohlcv,
    upsert_ohlcv_raw,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_repo_caches():
    """Xóa cache trước mỗi test để đảm bảo isolation."""
    clear_caches()
    yield
    clear_caches()


# ═══════════════════════════════════════════════════════════════════════════
# ensure_exchange
# ═══════════════════════════════════════════════════════════════════════════


class TestEnsureExchange:
    """ensure_exchange: idempotent, trả cùng id."""

    def test_creates_and_returns_id(self, db):
        code = f"TEST_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Test Exchange", "crypto", "UTC")
        assert isinstance(eid, int)
        assert eid > 0

    def test_idempotent(self, db):
        code = f"TEST_{uuid.uuid4().hex[:6]}"
        id1 = ensure_exchange(db, code, "Test Exchange", "crypto", "UTC")
        clear_caches()
        id2 = ensure_exchange(db, code, "Test Exchange", "crypto", "UTC")
        assert id1 == id2

    def test_cached(self, db):
        code = f"TEST_{uuid.uuid4().hex[:6]}"
        id1 = ensure_exchange(db, code, "Test Exchange", "crypto", "UTC")
        id2 = ensure_exchange(db, code, "Test Exchange", "crypto", "UTC")
        assert id1 == id2


# ═══════════════════════════════════════════════════════════════════════════
# ensure_symbol
# ═══════════════════════════════════════════════════════════════════════════


class TestEnsureSymbol:
    """ensure_symbol: idempotent, trả cùng id."""

    def test_creates_and_returns_id(self, db):
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Exch", "crypto", "UTC")
        ticker = f"SYM{uuid.uuid4().hex[:4]}"
        sid = ensure_symbol(db, eid, ticker, "crypto", "binance", "BTC", "USDT")
        assert isinstance(sid, int)
        assert sid > 0

    def test_idempotent(self, db):
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Exch", "crypto", "UTC")
        ticker = f"SYM{uuid.uuid4().hex[:4]}"
        id1 = ensure_symbol(db, eid, ticker, "crypto", "binance")
        clear_caches()
        id2 = ensure_symbol(db, eid, ticker, "crypto", "binance")
        assert id1 == id2


# ═══════════════════════════════════════════════════════════════════════════
# upsert_ohlcv_raw
# ═══════════════════════════════════════════════════════════════════════════


class TestUpsertOhlcvRaw:
    """upsert_ohlcv_raw: idempotent, batch."""

    def _make_row(self, symbol_id: int, ts_offset_hours: int = 0) -> dict:
        return {
            "symbol_id": symbol_id,
            "timeframe": "1h",
            "ts": datetime(2024, 1, 1, tzinfo=timezone.utc)
            + timedelta(hours=ts_offset_hours),
            "open": Decimal("100.0"),
            "high": Decimal("110.0"),
            "low": Decimal("90.0"),
            "close": Decimal("105.0"),
            "volume": Decimal("1000.0"),
            "source": "binance",
            "raw_payload": '{"test": true}',
        }

    def test_inserts_rows(self, db):
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Exch", "crypto", "UTC")
        ticker = f"SYM{uuid.uuid4().hex[:4]}"
        sid = ensure_symbol(db, eid, ticker, "crypto", "binance")

        rows = [self._make_row(sid, i) for i in range(3)]
        affected = upsert_ohlcv_raw(db, rows)
        assert affected == 3

    def test_idempotent(self, db):
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Exch", "crypto", "UTC")
        ticker = f"SYM{uuid.uuid4().hex[:4]}"
        sid = ensure_symbol(db, eid, ticker, "crypto", "binance")

        rows = [self._make_row(sid)]
        upsert_ohlcv_raw(db, rows)
        # Upsert lần 2 — không tạo trùng
        upsert_ohlcv_raw(db, rows)
        db.flush()

        count = db.execute(
            text(
                "SELECT count(*) FROM market.ohlcv_raw "
                "WHERE symbol_id = :sid AND timeframe = '1h'"
            ),
            {"sid": sid},
        ).scalar()
        assert count == 1


# ═══════════════════════════════════════════════════════════════════════════
# upsert_ohlcv
# ═══════════════════════════════════════════════════════════════════════════


class TestUpsertOhlcv:
    """upsert_ohlcv: validation + idempotent."""

    def _make_row(
        self,
        symbol_id: int,
        high: Decimal = Decimal("110"),
        low: Decimal = Decimal("90"),
    ) -> dict:
        return {
            "symbol_id": symbol_id,
            "timeframe": "1d",
            "ts": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "open": Decimal("100"),
            "high": high,
            "low": low,
            "close": Decimal("105"),
            "volume": Decimal("1000"),
        }

    def test_inserts_valid_row(self, db):
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Exch", "stock", "Asia/Ho_Chi_Minh")
        ticker = f"SYM{uuid.uuid4().hex[:4]}"
        sid = ensure_symbol(db, eid, ticker, "stock", "vnstock")

        affected = upsert_ohlcv(db, [self._make_row(sid)])
        assert affected == 1

    def test_idempotent(self, db):
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Exch", "stock", "Asia/Ho_Chi_Minh")
        ticker = f"SYM{uuid.uuid4().hex[:4]}"
        sid = ensure_symbol(db, eid, ticker, "stock", "vnstock")

        row = self._make_row(sid)
        upsert_ohlcv(db, [row])
        upsert_ohlcv(db, [row])
        db.flush()

        count = db.execute(
            text(
                "SELECT count(*) FROM market.ohlcv "
                "WHERE symbol_id = :sid AND timeframe = '1d'"
            ),
            {"sid": sid},
        ).scalar()
        assert count == 1

    def test_rejects_high_less_than_low(self, db):
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Exch", "stock", "Asia/Ho_Chi_Minh")
        ticker = f"SYM{uuid.uuid4().hex[:4]}"
        sid = ensure_symbol(db, eid, ticker, "stock", "vnstock")

        row = self._make_row(sid, high=Decimal("80"), low=Decimal("100"))
        affected = upsert_ohlcv(db, [row])
        assert affected == 0

    def test_writes_to_market_schema(self, db):
        """Verify dữ liệu nằm ở market.ohlcv, KHÔNG ở public."""
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Exch", "crypto", "UTC")
        ticker = f"SYM{uuid.uuid4().hex[:4]}"
        sid = ensure_symbol(db, eid, ticker, "crypto", "binance")

        upsert_ohlcv(db, [self._make_row(sid)])
        db.flush()

        market_count = db.execute(
            text("SELECT count(*) FROM market.ohlcv WHERE symbol_id = :sid"),
            {"sid": sid},
        ).scalar()
        assert market_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# log_job / update_job
# ═══════════════════════════════════════════════════════════════════════════


class TestJobLog:
    """ops.job_log: insert + update."""

    def test_log_and_update_success(self, db):
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Exch", "crypto", "UTC")
        ticker = f"SYM{uuid.uuid4().hex[:4]}"
        sid = ensure_symbol(db, eid, ticker, "crypto", "binance")

        job_id = log_job(
            db,
            "ingest",
            "test_job",
            "running",
            symbol_id=sid,
            timeframe="1h",
        )
        assert isinstance(job_id, str)

        update_job(db, job_id, "success", rows_affected=42, duration_ms=100)
        db.flush()

        row = db.execute(
            text("SELECT status, rows_affected FROM ops.job_log WHERE id = :id"),
            {"id": job_id},
        ).fetchone()
        assert row is not None
        assert row[0] == "success"
        assert row[1] == 42

    def test_log_and_update_failed(self, db):
        job_id = log_job(db, "ingest", "fail_job", "running")
        update_job(db, job_id, "failed", error_message="test error")
        db.flush()

        row = db.execute(
            text("SELECT status, error_message FROM ops.job_log WHERE id = :id"),
            {"id": job_id},
        ).fetchone()
        assert row[0] == "failed"
        assert "test error" in row[1]


# ═══════════════════════════════════════════════════════════════════════════
# record_dq_check
# ═══════════════════════════════════════════════════════════════════════════


class TestDqCheck:
    """ops.data_quality_check: insert."""

    def test_inserts_record(self, db):
        code = f"EX_{uuid.uuid4().hex[:6]}"
        eid = ensure_exchange(db, code, "Exch", "crypto", "UTC")
        ticker = f"SYM{uuid.uuid4().hex[:4]}"
        sid = ensure_symbol(db, eid, ticker, "crypto", "binance")

        record_dq_check(
            db=db,
            symbol_id=sid,
            timeframe="1h",
            check_name="test_check",
            passed=True,
            ts_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            ts_end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            detail={"test": True},
        )
        db.flush()

        count = db.execute(
            text(
                "SELECT count(*) FROM ops.data_quality_check "
                "WHERE symbol_id = :sid AND check_name = 'test_check'"
            ),
            {"sid": sid},
        ).scalar()
        assert count == 1
