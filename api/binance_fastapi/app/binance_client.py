import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from tqdm import tqdm

from shared.db.mappers import (
    map_binance_klines_batch,
    normalize_timeframe,
    split_crypto_pair,
)
from shared.db.repositories.market_repo import (
    ensure_exchange,
    ensure_symbol,
    get_last_ohlcv_ts,
    log_job,
    record_dq_check,
    update_job,
    upsert_ohlcv,
    upsert_ohlcv_raw,
)

# ── Shared DB — ghi OHLCV vào market.* ──────────────────────────────────
from shared.db.session import SyncSessionLocal as SessionLocal

# ── Legacy imports (giữ cho order book / agg trades / backward compat) ──
from .models import RawBinanceData, SpotKline

logger = logging.getLogger(__name__)

BASE_URL = "https://data-api.binance.vision"


COLLECTOR_STATUS = {
    "running": False,
    "message": "Chua chay",
    "current_symbol": None,
    "current_interval": None,
    "current_progress": 0,
    "current_total": 0,
    "symbol_done": 0,
    "symbol_total": 0,
    "total_seen": 0,
    "total_inserted": 0,
    "errors": [],
}


INTERVAL_MS = {
    "1s": 1000,
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "2h": 2 * 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "6h": 6 * 60 * 60_000,
    "8h": 8 * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "3d": 3 * 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
}


def interval_to_ms(interval: str) -> int:
    if interval not in INTERVAL_MS:
        raise ValueError(f"Interval khong ho tro: {interval}")

    return INTERVAL_MS[interval]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in ["1", "true", "yes", "y", "on"]


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None or value.strip() == "":
        return default

    return int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)

    if value is None or value.strip() == "":
        return default

    return float(value)


def to_ms(value):
    if value is None or str(value).strip() == "":
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    if isinstance(value, int):
        return value

    text_val = str(value).strip()

    if text_val.isdigit():
        return int(text_val)

    dt = datetime.fromisoformat(text_val.replace("Z", "+00:00"))

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return int(dt.timestamp() * 1000)


def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def request_json(endpoint: str, params: dict | None = None, retry: int = 3):
    last_error = None

    for attempt in range(retry):
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.get(BASE_URL + endpoint, params=params)
                response.raise_for_status()
                return response.json()

        except Exception as e:
            last_error = e
            time.sleep(1 + attempt)

    raise last_error


# ── DEPRECATED: save_raw — thay bằng ohlcv_raw với raw_payload ──────────
def save_raw(db, endpoint: str, params: dict, payload):
    """DEPRECATED — Dữ liệu thô giờ lưu qua ``market.ohlcv_raw.raw_payload``."""
    if not env_bool("AUTO_SAVE_RAW", False):
        return

    raw = RawBinanceData(endpoint=endpoint, params=params, payload=payload)
    db.add(raw)


def get_trading_symbols(symbol_mode: str = "USDT", symbol_limit: int = 20):
    data = request_json("/api/v3/exchangeInfo", {"symbolStatus": "TRADING"})

    symbols = []

    for item in data.get("symbols", []):
        symbol = item.get("symbol")
        status = item.get("status")
        quote_asset = item.get("quoteAsset")
        is_spot = item.get("isSpotTradingAllowed", False)

        if status != "TRADING":
            continue

        if not is_spot:
            continue

        if symbol_mode.upper() == "ALL":
            symbols.append(symbol)

        elif quote_asset == symbol_mode.upper():
            symbols.append(symbol)

    symbols = sorted(set(symbols))

    if symbol_limit > 0:
        symbols = symbols[:symbol_limit]

    return symbols


# ── DEPRECATED: get_last_open_time — thay bằng get_last_ohlcv_ts ────────
def get_last_open_time(db, symbol: str, interval: str):
    """DEPRECATED — Dùng ``get_last_ohlcv_ts()`` từ market_repo."""
    from sqlalchemy import func

    return (
        db.query(func.max(SpotKline.open_time))
        .filter(SpotKline.symbol == symbol, SpotKline.interval == interval)
        .scalar()
    )


# ── DEPRECATED: insert_kline_rows — thay bằng upsert_ohlcv_raw/ohlcv ──
def insert_kline_rows(db, symbol: str, interval: str, data: list):
    """DEPRECATED — Dùng ``upsert_ohlcv_raw()`` + ``upsert_ohlcv()``."""
    if not data:
        return 0

    from sqlalchemy.dialects.postgresql import insert

    rows = []

    for item in data:
        rows.append(
            {
                "symbol": symbol,
                "interval": interval,
                "open_time": int(item[0]),
                "open_price": Decimal(item[1]),
                "high_price": Decimal(item[2]),
                "low_price": Decimal(item[3]),
                "close_price": Decimal(item[4]),
                "volume": Decimal(item[5]),
                "close_time": int(item[6]),
                "quote_asset_volume": Decimal(item[7]),
                "number_of_trades": int(item[8]),
                "taker_buy_base_asset_volume": Decimal(item[9]),
                "taker_buy_quote_asset_volume": Decimal(item[10]),
                "ignore_value": str(item[11]),
            }
        )

    stmt = insert(SpotKline).values(rows)

    stmt = stmt.on_conflict_do_nothing(
        index_elements=["symbol", "interval", "open_time"]
    )

    result = db.execute(stmt)

    if result.rowcount is None or result.rowcount < 0:
        return 0

    return result.rowcount


def estimate_request_count(start_ms: int, end_ms: int, interval: str) -> int:
    if start_ms >= end_ms:
        return 0

    interval_ms = interval_to_ms(interval)

    total_candles = math.ceil((end_ms - start_ms) / interval_ms)

    return max(1, math.ceil(total_candles / 1000))


def _get_resume_start_ms(
    db,
    symbol_id: int,
    timeframe: str,
    interval: str,
    original_start_ms: int,
) -> int:
    """Tính start_ms thực tế dựa trên dữ liệu đã có trong market.ohlcv.

    Args:
        db: Sync session.
        symbol_id: FK market.symbol.id.
        timeframe: Normalized timeframe.
        interval: Original interval string (để tính interval_ms).
        original_start_ms: Start ms ban đầu.

    Returns:
        Start ms đã điều chỉnh.
    """
    last_ts = get_last_ohlcv_ts(db, symbol_id, timeframe)
    if last_ts is not None:
        last_ms = int(last_ts.timestamp() * 1000)
        return max(original_start_ms, last_ms + interval_to_ms(interval))
    return original_start_ms


def estimate_symbol_requests(
    symbol: str,
    intervals: list[str],
    start_ms: int,
    end_ms: int,
) -> int:
    db = SessionLocal()

    total = 0

    try:
        # Cần exchange_id + symbol_id cho resume check
        exchange_id = ensure_exchange(
            db,
            "BINANCE",
            "Binance Cryptocurrency Exchange",
            "crypto",
            "UTC",
        )
        base, quote = split_crypto_pair(symbol)
        symbol_id = ensure_symbol(
            db,
            exchange_id,
            symbol,
            "crypto",
            "binance",
            base,
            quote,
        )
        db.commit()

        for interval in intervals:
            tf = normalize_timeframe(interval)
            if tf is None:
                continue

            effective_start = _get_resume_start_ms(
                db,
                symbol_id,
                tf,
                interval,
                start_ms,
            )
            total += estimate_request_count(effective_start, end_ms, interval)

    finally:
        db.close()

    return max(total, 1)


def _run_dq_checks(
    db,
    symbol_id: int,
    timeframe: str,
    data: list,
    ts_start_ms: int,
    ts_end_ms: int,
) -> None:
    """Chạy data quality checks cơ bản sau khi fetch batch.

    Kiểm tra:
    - high < low
    - Giá/volume âm
    - Bản ghi trùng timestamp
    """
    ts_start = datetime.fromtimestamp(ts_start_ms / 1000, tz=timezone.utc)
    ts_end = datetime.fromtimestamp(ts_end_ms / 1000, tz=timezone.utc)

    high_low_violations = 0
    negative_values = 0
    timestamps = set()
    duplicate_count = 0

    for kline in data:
        try:
            h = Decimal(str(kline[2]))
            l_ = Decimal(str(kline[3]))
            o = Decimal(str(kline[1]))
            c = Decimal(str(kline[4]))
            v = Decimal(str(kline[5]))

            if h < l_:
                high_low_violations += 1
            if o < 0 or c < 0 or v < 0:
                negative_values += 1

            ts = int(kline[0])
            if ts in timestamps:
                duplicate_count += 1
            timestamps.add(ts)
        except Exception:
            pass

    total_issues = high_low_violations + negative_values + duplicate_count
    passed = total_issues == 0

    record_dq_check(
        db=db,
        symbol_id=symbol_id,
        timeframe=timeframe,
        check_name="binance_kline_batch_check",
        passed=passed,
        ts_start=ts_start,
        ts_end=ts_end,
        detail={
            "total_candles": len(data),
            "high_low_violations": high_low_violations,
            "negative_values": negative_values,
            "duplicate_timestamps": duplicate_count,
        },
    )


def collect_klines(symbol: str, interval: str, start: str, end: str, progress_bar=None):
    symbol = symbol.upper()

    start_ms = to_ms(start)
    end_ms = to_ms(end)

    # Normalize timeframe — nếu không khớp enum, vẫn fetch nhưng skip market.* write
    tf = normalize_timeframe(interval)
    write_to_market = tf is not None

    if not write_to_market:
        logger.warning(
            "Interval '%s' không khớp market.timeframe enum — "
            "ghi vào legacy spot_klines only",
            interval,
        )

    total_seen = 0
    total_inserted = 0

    db = SessionLocal()

    job_id: str | None = None
    job_start_time = time.monotonic()

    try:
        symbol_id: int | None = None

        if write_to_market:
            # Ensure exchange + symbol
            exchange_id = ensure_exchange(
                db,
                "BINANCE",
                "Binance Cryptocurrency Exchange",
                "crypto",
                "UTC",
            )
            base, quote = split_crypto_pair(symbol)
            symbol_id = ensure_symbol(
                db,
                exchange_id,
                symbol,
                "crypto",
                "binance",
                base,
                quote,
            )
            db.commit()

            # Resume point từ market.ohlcv
            start_ms = _get_resume_start_ms(
                db,
                symbol_id,
                tf,
                interval,
                start_ms,
            )

            # Log job start
            job_id = log_job(
                db,
                job_type="ingest",
                job_name=f"binance_klines_{symbol}_{interval}",
                status="running",
                symbol_id=symbol_id,
                timeframe=tf,
                context={"start": start, "end": end},
            )
            db.commit()

        while start_ms < end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 1000,
            }

            data = request_json("/api/v3/klines", params)

            if not data:
                break

            if write_to_market and symbol_id is not None:
                # ── Ghi vào market.ohlcv_raw + market.ohlcv ──────────
                raw_rows, clean_rows = map_binance_klines_batch(
                    symbol_id,
                    tf,
                    data,
                )
                upsert_ohlcv_raw(db, raw_rows)
                inserted = upsert_ohlcv(db, clean_rows)

                # DQ checks
                _run_dq_checks(
                    db,
                    symbol_id,
                    tf,
                    data,
                    int(data[0][0]),
                    int(data[-1][6]),
                )
            else:
                inserted = 0

            db.commit()

            total_seen += len(data)
            total_inserted += inserted

            COLLECTOR_STATUS["total_seen"] += len(data)
            COLLECTOR_STATUS["total_inserted"] += inserted
            COLLECTOR_STATUS["current_interval"] = interval

            last_close_time = int(data[-1][6])

            if progress_bar is not None:
                progress_bar.update(1)
                COLLECTOR_STATUS["current_progress"] = progress_bar.n
                COLLECTOR_STATUS["current_total"] = progress_bar.total

                progress_bar.set_postfix_str(
                    f"{interval} | rows={total_seen}"
                    f" | last={ms_to_iso(last_close_time)[:10]}"
                )

            if last_close_time <= start_ms:
                break

            start_ms = last_close_time + 1

            time.sleep(env_float("AUTO_SLEEP_SECONDS", 0.2))

        # ── Job success ──────────────────────────────────────────────
        if job_id is not None:
            duration_ms = int((time.monotonic() - job_start_time) * 1000)
            update_job(db, job_id, "success", total_inserted, duration_ms)
            db.commit()

    except Exception as e:
        db.rollback()

        if job_id is not None:
            try:
                duration_ms = int((time.monotonic() - job_start_time) * 1000)
                update_job(
                    db,
                    job_id,
                    "failed",
                    error_message=str(e)[:500],
                    duration_ms=duration_ms,
                )
                db.commit()
            except Exception:
                logger.exception("Không thể cập nhật job_log failed")

        raise e

    finally:
        db.close()

    return {
        "symbol": symbol,
        "interval": interval,
        "total_seen": total_seen,
        "total_inserted": total_inserted,
    }


def add_month(dt: datetime):
    year = dt.year
    month = dt.month + 1

    if month == 13:
        year += 1
        month = 1

    return dt.replace(
        year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def split_time_ranges(start_ms: int, end_ms: int, chunk: str):
    current = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)

    while current < end_dt:
        if chunk == "day":
            next_dt = current.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)

        else:
            month_start = current.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            next_dt = add_month(month_start)

        if next_dt > end_dt:
            next_dt = end_dt

        yield (int(current.timestamp() * 1000), int(next_dt.timestamp() * 1000))

        current = next_dt


def collect_many_klines(
    symbol_mode: str = "USDT",
    symbol_limit: int = 20,
    intervals: list[str] | None = None,
    start: str = "2024-01-01T00:00:00",
    end: str | None = None,
    chunk: str = "month",
):
    if intervals is None:
        intervals = ["1m", "5m", "15m", "1h", "4h", "1d"]

    start_ms = to_ms(start)
    end_ms = to_ms(end)

    COLLECTOR_STATUS["running"] = True
    COLLECTOR_STATUS["message"] = "Dang lay danh sach symbol"
    COLLECTOR_STATUS["errors"] = []
    COLLECTOR_STATUS["total_seen"] = 0
    COLLECTOR_STATUS["total_inserted"] = 0
    COLLECTOR_STATUS["symbol_done"] = 0

    symbols = get_trading_symbols(symbol_mode, symbol_limit)

    COLLECTOR_STATUS["symbol_total"] = len(symbols)
    COLLECTOR_STATUS["message"] = f"Bat dau lay {len(symbols)} symbols"

    tqdm.write(f"So symbol can lay: {len(symbols)}")
    tqdm.write(f"Intervals: {', '.join(intervals)}")

    try:
        with tqdm(
            total=len(symbols), desc="Tong tien trinh", unit="coin", position=0
        ) as total_bar:
            for symbol in symbols:
                COLLECTOR_STATUS["current_symbol"] = symbol
                COLLECTOR_STATUS["current_interval"] = None

                symbol_total_steps = estimate_symbol_requests(
                    symbol=symbol, intervals=intervals, start_ms=start_ms, end_ms=end_ms
                )

                with tqdm(
                    total=symbol_total_steps,
                    desc=symbol,
                    unit="req",
                    position=1,
                    leave=False,
                ) as coin_bar:
                    for interval in intervals:
                        for range_start_ms, range_end_ms in split_time_ranges(
                            start_ms, end_ms, chunk
                        ):
                            range_start = ms_to_iso(range_start_ms)
                            range_end = ms_to_iso(range_end_ms)

                            COLLECTOR_STATUS["message"] = (
                                f"Dang lay {symbol} {interval} "
                                f"{range_start} -> {range_end}"
                            )

                            try:
                                collect_klines(
                                    symbol=symbol,
                                    interval=interval,
                                    start=range_start,
                                    end=range_end,
                                    progress_bar=coin_bar,
                                )

                            except Exception as e:
                                error_text = f"{symbol} {interval}: {str(e)}"
                                COLLECTOR_STATUS["errors"].append(error_text)
                                tqdm.write(f"[ERROR] {error_text}")

                                if len(COLLECTOR_STATUS["errors"]) >= 20:
                                    raise RuntimeError("Qua nhieu loi, dung collector")

                    if coin_bar.n < coin_bar.total:
                        coin_bar.update(coin_bar.total - coin_bar.n)

                COLLECTOR_STATUS["symbol_done"] += 1
                total_bar.update(1)
                tqdm.write(f"{symbol}: hoan thanh")

        COLLECTOR_STATUS["message"] = "đã lấy xong dữ liệu"
        tqdm.write("đã lấy xong dữ liệu")

    except Exception as e:
        COLLECTOR_STATUS["message"] = f"Loi: {str(e)}"
        tqdm.write(f"[ERROR] {str(e)}")

    finally:
        COLLECTOR_STATUS["running"] = False
        COLLECTOR_STATUS["current_symbol"] = None
        COLLECTOR_STATUS["current_interval"] = None


def auto_collect_from_env():
    while True:
        symbol_mode = os.getenv("AUTO_SYMBOL_MODE", "USDT")
        symbol_limit = env_int("AUTO_SYMBOL_LIMIT", 20)

        intervals_text = os.getenv("AUTO_INTERVALS", "1m,5m,15m,1h,4h,1d")

        intervals = [item.strip() for item in intervals_text.split(",") if item.strip()]

        start = os.getenv("AUTO_START_DATE", "2024-01-01T00:00:00")
        end = os.getenv("AUTO_END_DATE", "")

        chunk = os.getenv("AUTO_CHUNK", "month").strip().lower()

        collect_many_klines(
            symbol_mode=symbol_mode,
            symbol_limit=symbol_limit,
            intervals=intervals,
            start=start,
            end=end,
            chunk=chunk,
        )

        repeat_minutes = env_int("AUTO_REPEAT_MINUTES", 0)

        if repeat_minutes <= 0:
            break

        tqdm.write(f"Cho {repeat_minutes} phut de cap nhat tiep...")
        time.sleep(repeat_minutes * 60)
