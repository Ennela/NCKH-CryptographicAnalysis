import os
import time
import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import httpx
from tqdm import tqdm
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from .database import SessionLocal
from .models import SpotKline, RawBinanceData


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

    text = str(value).strip()

    if text.isdigit():
        return int(text)

    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))

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


def save_raw(db, endpoint: str, params: dict, payload):
    if not env_bool("AUTO_SAVE_RAW", False):
        return

    raw = RawBinanceData(
        endpoint=endpoint,
        params=params,
        payload=payload
    )
    db.add(raw)


def get_trading_symbols(symbol_mode: str = "USDT", symbol_limit: int = 20):
    data = request_json(
        "/api/v3/exchangeInfo",
        {
            "symbolStatus": "TRADING"
        }
    )

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


def get_last_open_time(db, symbol: str, interval: str):
    return (
        db.query(func.max(SpotKline.open_time))
        .filter(
            SpotKline.symbol == symbol,
            SpotKline.interval == interval
        )
        .scalar()
    )


def insert_kline_rows(db, symbol: str, interval: str, data: list):
    if not data:
        return 0

    rows = []

    for item in data:
        rows.append({
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
            "ignore_value": str(item[11])
        })

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


def estimate_symbol_requests(symbol: str, intervals: list[str], start_ms: int, end_ms: int) -> int:
    db = SessionLocal()

    total = 0

    try:
        for interval in intervals:
            effective_start = start_ms

            last_open_time = get_last_open_time(db, symbol, interval)

            if last_open_time is not None:
                effective_start = max(
                    effective_start,
                    last_open_time + interval_to_ms(interval)
                )

            total += estimate_request_count(
                effective_start,
                end_ms,
                interval
            )

    finally:
        db.close()

    return max(total, 1)


def collect_klines(
    symbol: str,
    interval: str,
    start: str,
    end: str,
    progress_bar=None
):
    symbol = symbol.upper()

    start_ms = to_ms(start)
    end_ms = to_ms(end)

    interval_ms = interval_to_ms(interval)

    total_seen = 0
    total_inserted = 0

    db = SessionLocal()

    try:
        last_open_time = get_last_open_time(db, symbol, interval)

        if last_open_time is not None:
            start_ms = max(start_ms, last_open_time + interval_ms)

        while start_ms < end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 1000
            }

            data = request_json("/api/v3/klines", params)

            if not data:
                break

            save_raw(db, "/api/v3/klines", params, data)

            inserted = insert_kline_rows(db, symbol, interval, data)
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
                    f"{interval} | rows={total_seen} | last={ms_to_iso(last_close_time)[:10]}"
                )

            if last_close_time <= start_ms:
                break

            start_ms = last_close_time + 1

            time.sleep(env_float("AUTO_SLEEP_SECONDS", 0.2))

    except Exception as e:
        db.rollback()
        raise e

    finally:
        db.close()

    return {
        "symbol": symbol,
        "interval": interval,
        "total_seen": total_seen,
        "total_inserted": total_inserted
    }


def add_month(dt: datetime):
    year = dt.year
    month = dt.month + 1

    if month == 13:
        year += 1
        month = 1

    return dt.replace(
        year=year,
        month=month,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )


def split_time_ranges(start_ms: int, end_ms: int, chunk: str):
    current = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)

    while current < end_dt:
        if chunk == "day":
            next_dt = current.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            ) + timedelta(days=1)

        else:
            month_start = current.replace(
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )
            next_dt = add_month(month_start)

        if next_dt > end_dt:
            next_dt = end_dt

        yield (
            int(current.timestamp() * 1000),
            int(next_dt.timestamp() * 1000)
        )

        current = next_dt


def collect_many_klines(
    symbol_mode: str = "USDT",
    symbol_limit: int = 20,
    intervals: list[str] | None = None,
    start: str = "2024-01-01T00:00:00",
    end: str | None = None,
    chunk: str = "month"
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
            total=len(symbols),
            desc="Tong tien trinh",
            unit="coin",
            position=0
        ) as total_bar:

            for symbol in symbols:
                COLLECTOR_STATUS["current_symbol"] = symbol
                COLLECTOR_STATUS["current_interval"] = None

                symbol_total_steps = estimate_symbol_requests(
                    symbol=symbol,
                    intervals=intervals,
                    start_ms=start_ms,
                    end_ms=end_ms
                )

                with tqdm(
                    total=symbol_total_steps,
                    desc=symbol,
                    unit="req",
                    position=1,
                    leave=False
                ) as coin_bar:

                    for interval in intervals:
                        for range_start_ms, range_end_ms in split_time_ranges(
                            start_ms,
                            end_ms,
                            chunk
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
                                    progress_bar=coin_bar
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

        intervals_text = os.getenv(
            "AUTO_INTERVALS",
            "1m,5m,15m,1h,4h,1d"
        )

        intervals = [
            item.strip()
            for item in intervals_text.split(",")
            if item.strip()
        ]

        start = os.getenv("AUTO_START_DATE", "2024-01-01T00:00:00")
        end = os.getenv("AUTO_END_DATE", "")

        chunk = os.getenv("AUTO_CHUNK", "month").strip().lower()

        collect_many_klines(
            symbol_mode=symbol_mode,
            symbol_limit=symbol_limit,
            intervals=intervals,
            start=start,
            end=end,
            chunk=chunk
        )

        repeat_minutes = env_int("AUTO_REPEAT_MINUTES", 0)

        if repeat_minutes <= 0:
            break

        tqdm.write(f"Cho {repeat_minutes} phut de cap nhat tiep...")
        time.sleep(repeat_minutes * 60)