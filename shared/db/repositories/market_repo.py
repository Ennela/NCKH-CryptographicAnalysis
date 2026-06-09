"""
Market Repository — SYNC, raw SQL cho các bảng hypertable.

Cung cấp hàm idempotent để ghi dữ liệu vào:
- ``market.exchange``  (ensure)
- ``market.symbol``    (ensure)
- ``market.ohlcv_raw`` (upsert batch)
- ``market.ohlcv``     (upsert batch, có validation)
- ``ops.job_log``      (insert + update)
- ``ops.data_quality_check`` (insert)

Tất cả hàm nhận ``db: Session`` (sync) làm tham số đầu tiên.
Caller chịu trách nhiệm ``commit()`` / ``rollback()`` / ``close()``.

LƯU Ý: Module này KHÔNG gọi ``create_all()``.
Schema chỉ do ``infra/postgres/init.sql`` + Alembic migrations quản lý.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  In-memory caches — tránh query lặp cho dữ liệu ít thay đổi           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

_exchange_cache: dict[str, int] = {}
_symbol_cache: dict[tuple[int, str], int] = {}


def clear_caches() -> None:
    """Xóa cache — dùng trong test hoặc khi cần reload."""
    _exchange_cache.clear()
    _symbol_cache.clear()


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  ensure_exchange / ensure_symbol — Idempotent lookup-or-create          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def ensure_exchange(
    db: Session,
    code: str,
    name: str,
    asset_class: str,
    tz: str = "UTC",
) -> int:
    """Đảm bảo exchange tồn tại, trả ``id``. Idempotent + cached.

    Args:
        db: Sync SQLAlchemy session.
        code: Mã sàn (VD: ``HOSE``, ``BINANCE``).
        name: Tên đầy đủ.
        asset_class: ``'stock'`` hoặc ``'crypto'``.
        tz: Timezone string (VD: ``'Asia/Ho_Chi_Minh'``).

    Returns:
        ``exchange.id`` (int).
    """
    if code in _exchange_cache:
        return _exchange_cache[code]

    # INSERT ... ON CONFLICT DO NOTHING rồi SELECT
    db.execute(
        text("""
            INSERT INTO market.exchange (code, name, asset_class, timezone)
            VALUES (:code, :name, :asset_class, :tz)
            ON CONFLICT (code) DO NOTHING
        """),
        {"code": code, "name": name, "asset_class": asset_class, "tz": tz},
    )
    db.flush()

    row = db.execute(
        text("SELECT id FROM market.exchange WHERE code = :code"),
        {"code": code},
    ).fetchone()

    if row is None:
        raise RuntimeError(f"Không tìm thấy exchange code={code} sau INSERT")

    exchange_id: int = row[0]
    _exchange_cache[code] = exchange_id
    return exchange_id


def ensure_symbol(
    db: Session,
    exchange_id: int,
    ticker: str,
    asset_class: str,
    source: str,
    base_asset: Optional[str] = None,
    quote_asset: Optional[str] = None,
) -> int:
    """Đảm bảo symbol tồn tại, trả ``id``. Idempotent + cached.

    Args:
        db: Sync SQLAlchemy session.
        exchange_id: FK tới ``market.exchange.id``.
        ticker: Mã ticker (VD: ``FPT``, ``BTCUSDT``).
        asset_class: ``'stock'`` hoặc ``'crypto'``.
        source: ``'vnstock'``, ``'binance'``, hoặc ``'manual'``.
        base_asset: (crypto) VD: ``BTC``.
        quote_asset: (crypto) VD: ``USDT``.

    Returns:
        ``symbol.id`` (int).
    """
    cache_key = (exchange_id, ticker)
    if cache_key in _symbol_cache:
        return _symbol_cache[cache_key]

    db.execute(
        text("""
            INSERT INTO market.symbol
                (exchange_id, ticker, asset_class,
                 source, base_asset, quote_asset)
            VALUES
                (:exchange_id, :ticker, :asset_class,
                 :source, :base_asset, :quote_asset)
            ON CONFLICT (exchange_id, ticker) DO NOTHING
        """),
        {
            "exchange_id": exchange_id,
            "ticker": ticker,
            "asset_class": asset_class,
            "source": source,
            "base_asset": base_asset,
            "quote_asset": quote_asset,
        },
    )
    db.flush()

    row = db.execute(
        text("""
            SELECT id FROM market.symbol
            WHERE exchange_id = :exchange_id AND ticker = :ticker
        """),
        {"exchange_id": exchange_id, "ticker": ticker},
    ).fetchone()

    if row is None:
        raise RuntimeError(
            f"Không tìm thấy symbol ticker={ticker} "
            f"exchange_id={exchange_id} sau INSERT"
        )

    symbol_id: int = row[0]
    _symbol_cache[cache_key] = symbol_id
    return symbol_id


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  upsert_ohlcv_raw / upsert_ohlcv — Batch idempotent upsert             ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def upsert_ohlcv_raw(db: Session, rows: list[dict[str, Any]]) -> int:
    """Batch upsert vào ``market.ohlcv_raw``. Idempotent theo UNIQUE constraint.

    Mỗi dict trong ``rows`` cần keys:
        ``symbol_id``, ``timeframe``, ``ts``, ``open``, ``high``, ``low``,
        ``close``, ``volume``, ``source``, ``raw_payload`` (optional).

    Returns:
        Số rows affected (inserted hoặc updated).
    """
    if not rows:
        return 0

    stmt = text("""
        INSERT INTO market.ohlcv_raw
            (symbol_id, timeframe, ts, open, high,
             low, close, volume, source, raw_payload)
        VALUES
            (:symbol_id, :timeframe, :ts, :open,
             :high, :low, :close, :volume,
             :source, :raw_payload)
        ON CONFLICT (symbol_id, timeframe, ts, source)
        DO UPDATE SET
            open        = EXCLUDED.open,
            high        = EXCLUDED.high,
            low         = EXCLUDED.low,
            close       = EXCLUDED.close,
            volume      = EXCLUDED.volume,
            raw_payload = EXCLUDED.raw_payload,
            ingested_at = NOW()
    """)

    # Đảm bảo raw_payload là None nếu không có
    for row in rows:
        row.setdefault("raw_payload", None)

    result = db.execute(stmt, rows)
    return result.rowcount if result.rowcount and result.rowcount > 0 else 0


def _validate_ohlcv_row(row: dict[str, Any]) -> Optional[str]:
    """Kiểm tra chất lượng 1 bản ghi OHLCV trước khi insert.

    Returns:
        ``None`` nếu hợp lệ, chuỗi mô tả lỗi nếu không.
    """
    try:
        o = Decimal(str(row["open"]))
        h = Decimal(str(row["high"]))
        l_ = Decimal(str(row["low"]))  # noqa: E741
        c = Decimal(str(row["close"]))
        v = Decimal(str(row["volume"]))
    except Exception as exc:
        return f"Không parse được giá/volume: {exc}"

    if h < l_:
        return f"high ({h}) < low ({l_})"
    if o < 0:
        return f"open ({o}) < 0"
    if c < 0:
        return f"close ({c}) < 0"
    if v < 0:
        return f"volume ({v}) < 0"

    return None


def upsert_ohlcv(db: Session, rows: list[dict[str, Any]]) -> int:
    """Batch upsert vào ``market.ohlcv`` (dữ liệu sạch). Validation trước khi insert.

    Tự động loại bản ghi ``high < low`` hoặc giá/volume âm. Bản ghi bị loại
    được log ở level WARNING.

    Mỗi dict trong ``rows`` cần keys:
        ``symbol_id``, ``timeframe``, ``ts``, ``open``, ``high``, ``low``,
        ``close``, ``volume``.
    Keys tùy chọn: ``vwap``, ``trade_count``.

    Returns:
        Số rows thực sự upserted.
    """
    if not rows:
        return 0

    valid_rows: list[dict[str, Any]] = []
    rejected_count = 0

    for row in rows:
        error = _validate_ohlcv_row(row)
        if error is not None:
            rejected_count += 1
            logger.warning(
                "Loại bản ghi OHLCV: symbol_id=%s, ts=%s — %s",
                row.get("symbol_id"),
                row.get("ts"),
                error,
            )
            continue
        valid_rows.append(row)

    if rejected_count > 0:
        logger.info(
            "upsert_ohlcv: loại %d/%d bản ghi không hợp lệ",
            rejected_count,
            len(rows),
        )

    if not valid_rows:
        return 0

    stmt = text("""
        INSERT INTO market.ohlcv
            (symbol_id, timeframe, ts, open, high,
             low, close, volume, vwap, trade_count)
        VALUES
            (:symbol_id, :timeframe, :ts, :open,
             :high, :low, :close, :volume,
             :vwap, :trade_count)
        ON CONFLICT (symbol_id, timeframe, ts)
        DO UPDATE SET
            open        = EXCLUDED.open,
            high        = EXCLUDED.high,
            low         = EXCLUDED.low,
            close       = EXCLUDED.close,
            volume      = EXCLUDED.volume,
            vwap        = EXCLUDED.vwap,
            trade_count = EXCLUDED.trade_count,
            updated_at  = NOW()
    """)

    # Đảm bảo optional fields có giá trị mặc định
    for row in valid_rows:
        row.setdefault("vwap", None)
        row.setdefault("trade_count", None)

    result = db.execute(stmt, valid_rows)
    return result.rowcount if result.rowcount and result.rowcount > 0 else 0


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  get_last_ohlcv_ts — Resume point cho incremental ingestion             ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def get_last_ohlcv_ts(
    db: Session,
    symbol_id: int,
    timeframe: str,
) -> Optional[datetime]:
    """Trả ``MAX(ts)`` từ ``market.ohlcv`` cho symbol + timeframe.

    Returns:
        ``datetime`` (UTC) hoặc ``None`` nếu chưa có dữ liệu.
    """
    row = db.execute(
        text("""
            SELECT MAX(ts) FROM market.ohlcv
            WHERE symbol_id = :symbol_id AND timeframe = :timeframe
        """),
        {"symbol_id": symbol_id, "timeframe": timeframe},
    ).fetchone()

    if row is None or row[0] is None:
        return None
    return row[0]


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  ops.job_log — Ghi log tác vụ ingest                                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def log_job(
    db: Session,
    job_type: str,
    job_name: str,
    status: str = "running",
    symbol_id: Optional[int] = None,
    timeframe: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
) -> str:
    """Tạo record trong ``ops.job_log``, trả ``job_id`` (UUID string).

    Args:
        db: Sync session.
        job_type: Enum value — ``'ingest'``, ``'clean'``, etc.
        job_name: Tên mô tả (VD: ``'binance_klines_BTCUSDT_1h'``).
        status: ``'running'`` (mặc định) hoặc ``'pending'``.
        symbol_id: FK tới ``market.symbol`` (optional).
        timeframe: Enum value (optional).
        context: JSONB metadata bổ sung (optional).

    Returns:
        UUID string của job vừa tạo.
    """
    job_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO ops.job_log
                (id, job_type, job_name, status,
                 symbol_id, timeframe,
                 started_at, context)
            VALUES
                (:id, :job_type, :job_name, :status,
                 :symbol_id, :timeframe, NOW(),
                 :context)
        """),
        {
            "id": job_id,
            "job_type": job_type,
            "job_name": job_name,
            "status": status,
            "symbol_id": symbol_id,
            "timeframe": timeframe,
            "context": _json_or_empty(context),
        },
    )
    db.flush()
    return job_id


def update_job(
    db: Session,
    job_id: str,
    status: str,
    rows_affected: Optional[int] = None,
    duration_ms: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    """Cập nhật ``ops.job_log`` khi job hoàn thành hoặc thất bại.

    Args:
        db: Sync session.
        job_id: UUID string từ ``log_job()``.
        status: ``'success'`` hoặc ``'failed'``.
        rows_affected: Số bản ghi đã xử lý (optional).
        duration_ms: Thời gian chạy (ms) (optional).
        error_message: Thông báo lỗi nếu ``status='failed'`` (optional).
    """
    db.execute(
        text("""
            UPDATE ops.job_log
            SET status        = :status,
                finished_at   = NOW(),
                rows_affected = :rows_affected,
                duration_ms   = :duration_ms,
                error_message = :error_message
            WHERE id = :id
        """),
        {
            "id": job_id,
            "status": status,
            "rows_affected": rows_affected,
            "duration_ms": duration_ms,
            "error_message": error_message,
        },
    )


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  ops.data_quality_check — Ghi kết quả kiểm tra chất lượng              ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def record_dq_check(
    db: Session,
    symbol_id: int,
    timeframe: str,
    check_name: str,
    passed: bool,
    ts_start: datetime,
    ts_end: datetime,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """Ghi 1 kết quả kiểm tra chất lượng vào ``ops.data_quality_check``.

    Args:
        db: Sync session.
        symbol_id: FK tới ``market.symbol``.
        timeframe: Enum value.
        check_name: Tên kiểm tra (VD: ``'high_low_check'``).
        passed: ``True`` nếu pass.
        ts_start: Mốc bắt đầu phạm vi kiểm tra.
        ts_end: Mốc kết thúc phạm vi kiểm tra.
        detail: JSONB chi tiết (optional).
    """
    db.execute(
        text("""
            INSERT INTO ops.data_quality_check
                (symbol_id, timeframe, check_name, ts_range, passed, detail)
            VALUES
                (:symbol_id, :timeframe, :check_name,
                 tstzrange(:ts_start, :ts_end, '[)'),
                 :passed, :detail)
        """),
        {
            "symbol_id": symbol_id,
            "timeframe": timeframe,
            "check_name": check_name,
            "ts_start": ts_start,
            "ts_end": ts_end,
            "passed": passed,
            "detail": _json_or_empty(detail),
        },
    )


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Helpers                                                                ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def _json_or_empty(value: Optional[dict[str, Any]]) -> str:
    """Chuyển dict → JSON string, trả ``'{}'`` nếu ``None``.

    Dùng cho các tham số JSONB trong ``text()`` queries.
    """
    import json

    if value is None:
        return "{}"
    return json.dumps(value, default=str)
