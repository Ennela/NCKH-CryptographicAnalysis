import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from tqdm import tqdm
from vnstock import Company, Finance, Listing, Market, Quote, Trading

from shared.db.mappers import map_vnstock_df_batch, normalize_timeframe
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

# ── Legacy imports (giữ cho company/finance/intraday/price_board) ────────
from .database import SessionLocal as LegacySessionLocal
from .models import StockOhlcv, StockRawData

logger = logging.getLogger(__name__)


COLLECTOR_STATUS = {
    "running": False,
    "message": "Chua chay",
    "current_symbol": None,
    "current_interval": None,
    "symbol_done": 0,
    "symbol_total": 0,
    "total_seen": 0,
    "total_inserted": 0,
    "errors": [],
}

STOP_COLLECTOR = threading.Event()
REQUEST_LOCK = threading.Lock()
LAST_REQUEST_TIME = 0.0


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ["1", "true", "yes", "y", "on"]


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def env_text(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def env_int(name: str, default: int = 0) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def get_today_text() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def safe_decimal(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return Decimal(str(value))


def clean_json_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df.columns = [str(col).strip().lower() for col in df.columns]

    rename_map = {}

    if "time" not in df.columns:
        for candidate in ["date", "trading_date", "datetime", "timestamp"]:
            if candidate in df.columns:
                rename_map[candidate] = "time"
                break

    if "open" not in df.columns:
        for candidate in ["open_price", "o"]:
            if candidate in df.columns:
                rename_map[candidate] = "open"
                break

    if "high" not in df.columns:
        for candidate in ["high_price", "h"]:
            if candidate in df.columns:
                rename_map[candidate] = "high"
                break

    if "low" not in df.columns:
        for candidate in ["low_price", "l"]:
            if candidate in df.columns:
                rename_map[candidate] = "low"
                break

    if "close" not in df.columns:
        for candidate in ["close_price", "c"]:
            if candidate in df.columns:
                rename_map[candidate] = "close"
                break

    if "volume" not in df.columns:
        for candidate in ["vol", "matched_volume"]:
            if candidate in df.columns:
                rename_map[candidate] = "volume"
                break

    df = df.rename(columns=rename_map)

    required_columns = ["time", "open", "high", "low", "close", "volume"]

    for col in required_columns:
        if col not in df.columns:
            df[col] = None

    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])

    return df


def fetch_ohlcv(symbol: str, interval: str, start: str, end: str):
    symbol = symbol.upper().strip()

    if not end:
        end = get_today_text()

    max_retry = get_auto_max_retry()
    last_error = None

    for attempt in range(max_retry):
        if STOP_COLLECTOR.is_set():
            return pd.DataFrame()

        try:
            wait_before_request()
            market = Market()
            df = market.equity(symbol).ohlcv(start=start, end=end, interval=interval)
            df = normalize_dataframe(df)
            return df

        except Exception as e:
            last_error = e
            error_text = str(e).lower()
            if (
                "rate" in error_text
                or "limit" in error_text
                or "too many" in error_text
            ):
                wait_seconds = 60
            else:
                wait_seconds = 15
            tqdm.write(
                f"[WAIT] {symbol} {interval}: loi request, "
                f"cho {wait_seconds}s roi thu lai. Lan {attempt + 1}/{max_retry}"
            )
            if wait_or_stop(wait_seconds):
                return pd.DataFrame()

    raise last_error


# ── DEPRECATED: insert_ohlcv_rows — thay bằng upsert_ohlcv_raw/ohlcv ──
def insert_ohlcv_rows(db, symbol: str, interval: str, df: pd.DataFrame):
    """DEPRECATED — Dùng ``upsert_ohlcv_raw()`` + ``upsert_ohlcv()``."""
    if df.empty:
        return 0

    rows = []
    for _, row in df.iterrows():
        candle_time = row["time"]
        if isinstance(candle_time, pd.Timestamp):
            candle_time = candle_time.to_pydatetime()
        if candle_time.tzinfo is not None:
            candle_time = candle_time.replace(tzinfo=None)
        raw_data = {
            str(key): clean_json_value(value) for key, value in row.to_dict().items()
        }
        rows.append(
            {
                "symbol": symbol,
                "interval": interval,
                "candle_time": candle_time,
                "open_price": safe_decimal(row.get("open")),
                "high_price": safe_decimal(row.get("high")),
                "low_price": safe_decimal(row.get("low")),
                "close_price": safe_decimal(row.get("close")),
                "volume": safe_decimal(row.get("volume")),
                "raw_data": raw_data,
            }
        )

    stmt = insert(StockOhlcv).values(rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["symbol", "interval", "candle_time"]
    )
    result = db.execute(stmt)
    if result.rowcount is None or result.rowcount < 0:
        return 0
    return result.rowcount


def _run_dq_checks(
    db,
    symbol_id: int,
    timeframe: str,
    df: pd.DataFrame,
) -> None:
    """Chạy data quality checks cơ bản trên DataFrame OHLCV."""
    if df is None or df.empty:
        return

    ts_start = df["time"].min()
    ts_end = df["time"].max()

    if isinstance(ts_start, pd.Timestamp):
        ts_start = ts_start.to_pydatetime()
    if isinstance(ts_end, pd.Timestamp):
        ts_end = ts_end.to_pydatetime()
    if ts_start.tzinfo is None:
        ts_start = ts_start.replace(tzinfo=timezone.utc)
    if ts_end.tzinfo is None:
        ts_end = ts_end.replace(tzinfo=timezone.utc)

    # Đảm bảo range hợp lệ
    ts_end = ts_end + timedelta(seconds=1)

    high_low_violations = 0
    negative_values = 0
    null_prices = 0

    for _, row in df.iterrows():
        h = safe_decimal(row.get("high"))
        l_ = safe_decimal(row.get("low"))
        o = safe_decimal(row.get("open"))
        c = safe_decimal(row.get("close"))

        if h is None or l_ is None or o is None or c is None:
            null_prices += 1
            continue
        if h < l_:
            high_low_violations += 1
        if o < 0 or c < 0:
            negative_values += 1

    total_issues = high_low_violations + negative_values + null_prices
    passed = total_issues == 0

    record_dq_check(
        db=db,
        symbol_id=symbol_id,
        timeframe=timeframe,
        check_name="vnstock_ohlcv_batch_check",
        passed=passed,
        ts_start=ts_start,
        ts_end=ts_end,
        detail={
            "total_candles": len(df),
            "high_low_violations": high_low_violations,
            "negative_values": negative_values,
            "null_prices": null_prices,
        },
    )


def collect_ohlcv(symbol: str, interval: str, start: str, end: str = ""):
    if STOP_COLLECTOR.is_set():
        return {"symbol": symbol, "interval": interval, "seen": 0, "inserted": 0}

    symbol = symbol.upper().strip()
    interval = interval.strip()

    tf = normalize_timeframe(interval)
    write_to_market = tf is not None

    if not write_to_market:
        logger.warning(
            "Interval '%s' không khớp market.timeframe enum — skip market write",
            interval,
        )

    db = SessionLocal()
    job_id: str | None = None
    job_start_time = time.monotonic()

    try:
        symbol_id: int | None = None

        if write_to_market:
            exchange_id = ensure_exchange(
                db,
                "HOSE",
                "Sở Giao dịch Chứng khoán TP.HCM",
                "stock",
                "Asia/Ho_Chi_Minh",
            )
            symbol_id = ensure_symbol(
                db,
                exchange_id,
                symbol,
                "stock",
                "vnstock",
            )
            db.commit()

            # Resume point
            last_ts = get_last_ohlcv_ts(db, symbol_id, tf)
            if last_ts is not None:
                if tf == "1d":
                    start = last_ts.strftime("%Y-%m-%d")
                else:
                    start = last_ts.strftime("%Y-%m-%d")

            job_id = log_job(
                db,
                job_type="ingest",
                job_name=f"vnstock_ohlcv_{symbol}_{interval}",
                status="running",
                symbol_id=symbol_id,
                timeframe=tf,
                context={"start": start, "end": end},
            )
            db.commit()

        df = fetch_ohlcv(symbol=symbol, interval=interval, start=start, end=end)

        inserted = 0

        if write_to_market and symbol_id is not None and not df.empty:
            raw_rows, clean_rows = map_vnstock_df_batch(symbol_id, tf, df)
            upsert_ohlcv_raw(db, raw_rows)
            inserted = upsert_ohlcv(db, clean_rows)
            _run_dq_checks(db, symbol_id, tf, df)

        db.commit()

        COLLECTOR_STATUS["total_seen"] += len(df)
        COLLECTOR_STATUS["total_inserted"] += inserted

        if job_id is not None:
            duration_ms = int((time.monotonic() - job_start_time) * 1000)
            update_job(db, job_id, "success", inserted, duration_ms)
            db.commit()

        return {
            "symbol": symbol,
            "interval": interval,
            "seen": len(df),
            "inserted": inserted,
        }

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


def collect_many_ohlcv(
    symbols: list[str], intervals: list[str], start: str, end: str = ""
):
    COLLECTOR_STATUS["running"] = True
    COLLECTOR_STATUS["message"] = "Dang lay du lieu co phieu"
    COLLECTOR_STATUS["symbol_done"] = 0
    COLLECTOR_STATUS["symbol_total"] = len(symbols)
    COLLECTOR_STATUS["total_seen"] = 0
    COLLECTOR_STATUS["total_inserted"] = 0
    COLLECTOR_STATUS["errors"] = []

    try:
        with tqdm(total=len(symbols), desc="Tong tien trinh", unit="ma") as total_bar:
            for symbol in symbols:
                symbol = symbol.upper().strip()
                COLLECTOR_STATUS["current_symbol"] = symbol

                for interval in intervals:
                    interval = interval.strip()
                    COLLECTOR_STATUS["current_interval"] = interval
                    COLLECTOR_STATUS["message"] = f"Dang lay {symbol} {interval}"

                    try:
                        result = collect_ohlcv(
                            symbol=symbol, interval=interval, start=start, end=end
                        )
                        tqdm.write(
                            f"{symbol} {interval}: "
                            f"seen={result['seen']} inserted={result['inserted']}"
                        )

                    except Exception as e:
                        error_text = f"{symbol} {interval}: {str(e)}"
                        COLLECTOR_STATUS["errors"].append(error_text)
                        tqdm.write(f"[ERROR] {error_text}")

                    time.sleep(env_float("AUTO_SLEEP_SECONDS", 1))

                COLLECTOR_STATUS["symbol_done"] += 1
                total_bar.update(1)

        COLLECTOR_STATUS["message"] = "đã lấy xong dữ liệu cổ phiếu"
        tqdm.write("đã lấy xong dữ liệu cổ phiếu")

    finally:
        COLLECTOR_STATUS["running"] = False
        COLLECTOR_STATUS["current_symbol"] = None
        COLLECTOR_STATUS["current_interval"] = None


def auto_collect_from_env():
    STOP_COLLECTOR.clear()

    run_forever = env_bool("AUTO_RUN_FOREVER", True)
    cycle_sleep_seconds = env_float("AUTO_CYCLE_SLEEP_SECONDS", 900)

    while not STOP_COLLECTOR.is_set():
        symbols = get_symbols_from_env()

        intervals_text = os.getenv("AUTO_INTERVALS", "1D")
        start = os.getenv("AUTO_START_DATE", "2024-01-01")
        end = os.getenv("AUTO_END_DATE", "")
        intervals = [item.strip() for item in intervals_text.split(",") if item.strip()]

        collect_ohlcv_enabled = env_bool("AUTO_COLLECT_OHLCV", True)
        collect_company_enabled = env_bool("AUTO_COLLECT_COMPANY", False)
        collect_finance_enabled = env_bool("AUTO_COLLECT_FINANCE", False)
        collect_price_board_enabled = env_bool("AUTO_COLLECT_PRICE_BOARD", False)
        collect_intraday_enabled = env_bool("AUTO_COLLECT_INTRADAY", False)

        COLLECTOR_STATUS["running"] = True
        COLLECTOR_STATUS["message"] = "Dang lay du lieu co phieu lien tuc"
        COLLECTOR_STATUS["symbol_done"] = 0
        COLLECTOR_STATUS["symbol_total"] = len(symbols)
        COLLECTOR_STATUS["total_seen"] = 0
        COLLECTOR_STATUS["total_inserted"] = 0
        COLLECTOR_STATUS["errors"] = []

        try:
            tqdm.write(f"So ma can lay: {len(symbols)}")
            tqdm.write(f"Danh sach interval: {', '.join(intervals)}")

            if collect_price_board_enabled and not STOP_COLLECTOR.is_set():
                collect_price_board_data(symbols)

            with tqdm(
                total=len(symbols), desc="Tong tien trinh", unit="ma"
            ) as total_bar:
                for symbol in symbols:
                    if STOP_COLLECTOR.is_set():
                        break

                    symbol = symbol.upper().strip()
                    COLLECTOR_STATUS["current_symbol"] = symbol
                    COLLECTOR_STATUS["message"] = f"Dang lay {symbol}"

                    if collect_ohlcv_enabled:
                        for interval in intervals:
                            if STOP_COLLECTOR.is_set():
                                break
                            try:
                                result = collect_ohlcv(
                                    symbol=symbol,
                                    interval=interval,
                                    start=start,
                                    end=end,
                                )
                                tqdm.write(
                                    f"{symbol} {interval}: "
                                    f"seen={result['seen']} inserted={result['inserted']}"
                                )
                            except Exception as e:
                                error_text = f"{symbol} {interval}: {str(e)}"
                                COLLECTOR_STATUS["errors"].append(error_text)
                                tqdm.write(f"[ERROR] {error_text}")

                    if collect_company_enabled and not STOP_COLLECTOR.is_set():
                        collect_company_data(symbol)
                    if collect_finance_enabled and not STOP_COLLECTOR.is_set():
                        collect_finance_data(symbol)
                    if collect_intraday_enabled and not STOP_COLLECTOR.is_set():
                        collect_intraday_data(symbol)

                    COLLECTOR_STATUS["symbol_done"] += 1
                    total_bar.update(1)

            if STOP_COLLECTOR.is_set():
                COLLECTOR_STATUS["message"] = "Da dung theo yeu cau nguoi dung"
                tqdm.write("Da dung theo yeu cau nguoi dung")
                break

            COLLECTOR_STATUS["message"] = (
                "Da hoan thanh mot vong, dang cho vong tiep theo"
            )
            tqdm.write(
                f"Da hoan thanh mot vong. Cho {cycle_sleep_seconds} giay de lay tiep..."
            )

            if not run_forever:
                break
            if wait_or_stop(cycle_sleep_seconds):
                break

        finally:
            pass

    COLLECTOR_STATUS["running"] = False
    COLLECTOR_STATUS["current_symbol"] = None
    COLLECTOR_STATUS["current_interval"] = None

    if STOP_COLLECTOR.is_set():
        COLLECTOR_STATUS["message"] = "Da dung"
    else:
        COLLECTOR_STATUS["message"] = "Da ket thuc collector"


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Non-OHLCV data collectors — KHÔNG đổi, vẫn dùng legacy SessionLocal   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def dataframe_to_payload(df):
    if df is None:
        return {"rows": [], "row_count": 0}
    if isinstance(df, pd.DataFrame):
        temp = df.copy()
        for col in temp.columns:
            temp[col] = temp[col].apply(clean_json_value)
        return {
            "columns": [str(col) for col in temp.columns],
            "rows": temp.to_dict(orient="records"),
            "row_count": len(temp),
        }
    if isinstance(df, dict):
        return {
            "data": {str(k): clean_json_value(v) for k, v in df.items()},
            "row_count": 1,
        }
    if isinstance(df, list):
        return {"rows": df, "row_count": len(df)}
    return {"data": str(df), "row_count": 1}


def save_raw_data(
    db, symbol: str | None, data_type: str, period: str | None, payload: dict
):
    stmt = insert(StockRawData).values(
        {
            "symbol": symbol,
            "data_type": data_type,
            "period": period,
            "payload": payload,
            "collected_date": date.today(),
        }
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "data_type", "period", "collected_date"],
        set_={"payload": payload, "created_at": func.now()},
    )
    db.execute(stmt)


def extract_symbol_list(data):
    if data is None:
        return []
    if isinstance(data, list):
        return [str(item).upper().strip() for item in data if str(item).strip()]
    if isinstance(data, pd.DataFrame):
        cols = [str(col).lower() for col in data.columns]
        for candidate in ["symbol", "ticker", "code"]:
            if candidate in cols:
                real_col = data.columns[cols.index(candidate)]
                return sorted(
                    [
                        str(item).upper().strip()
                        for item in data[real_col].dropna().tolist()
                        if str(item).strip()
                    ]
                )
    return []


def get_symbols_from_env():
    symbol_source = env_text("AUTO_SYMBOL_SOURCE", "CUSTOM").upper()
    symbol_limit = env_int("AUTO_SYMBOL_LIMIT", 0)
    symbols_text = env_text("AUTO_SYMBOLS", "FPT,VNM,HPG,VCB,TCB")
    fallback_symbols = [
        item.strip().upper() for item in symbols_text.split(",") if item.strip()
    ]

    if symbol_source == "CUSTOM":
        symbols = fallback_symbols
    else:
        try:
            listing = Listing(source="VCI")
            if symbol_source == "ALL":
                data = listing.all_symbols()
            else:
                data = listing.symbols_by_group(symbol_source)
            symbols = extract_symbol_list(data)
            if not symbols:
                print(
                    "Khong lay duoc danh sach symbol tu Vnstock, dung AUTO_SYMBOLS thay the"
                )
                symbols = fallback_symbols
        except Exception as e:
            print(f"Loi lay danh sach symbol tu Vnstock: {e}")
            print("Dung AUTO_SYMBOLS thay the")
            symbols = fallback_symbols

    if symbol_limit > 0:
        symbols = symbols[:symbol_limit]
    return symbols


def collect_company_data(symbol: str):
    symbol = symbol.upper().strip()
    data_types = [
        "overview",
        "profile",
        "shareholders",
        "officers",
        "subsidiaries",
        "dividends",
        "insider_deals",
        "events",
        "news",
    ]
    db = LegacySessionLocal()
    try:
        company = Company(symbol=symbol, source="TCBS")
        for data_type in data_types:
            try:
                func_obj = getattr(company, data_type)
                df = func_obj()
                payload = dataframe_to_payload(df)
                save_raw_data(
                    db=db,
                    symbol=symbol,
                    data_type=data_type,
                    period=None,
                    payload=payload,
                )
                db.commit()
                tqdm.write(f"{symbol} {data_type}: saved")
            except Exception as e:
                db.rollback()
                tqdm.write(f"[SKIP] {symbol} {data_type}: {e}")
    finally:
        db.close()


def collect_finance_data(symbol: str):
    symbol = symbol.upper().strip()
    periods_text = env_text("FINANCE_PERIODS", "year,quarter")
    periods = [item.strip() for item in periods_text.split(",") if item.strip()]
    data_types = ["income_statement", "balance_sheet", "cash_flow", "ratio"]

    db = LegacySessionLocal()
    try:
        finance = Finance(symbol=symbol, source="VCI")
        for period in periods:
            for data_type in data_types:
                try:
                    func_obj = getattr(finance, data_type)
                    if data_type == "ratio":
                        df = func_obj(period=period, lang="vi")
                    else:
                        df = func_obj(period=period)
                    payload = dataframe_to_payload(df)
                    save_raw_data(
                        db=db,
                        symbol=symbol,
                        data_type=data_type,
                        period=period,
                        payload=payload,
                    )
                    db.commit()
                    tqdm.write(f"{symbol} {data_type} {period}: saved")
                except Exception as e:
                    db.rollback()
                    tqdm.write(f"[SKIP] {symbol} {data_type} {period}: {e}")
    finally:
        db.close()


def collect_price_board_data(symbols: list[str]):
    if not symbols:
        return
    db = LegacySessionLocal()
    try:
        trading = Trading(source="VCI")
        df = trading.price_board(symbols)
        payload = dataframe_to_payload(df)
        save_raw_data(
            db=db, symbol=None, data_type="price_board", period=None, payload=payload
        )
        db.commit()
        tqdm.write("price_board: saved")
    except Exception as e:
        db.rollback()
        tqdm.write(f"[SKIP] price_board: {e}")
    finally:
        db.close()


def collect_intraday_data(symbol: str):
    symbol = symbol.upper().strip()
    db = LegacySessionLocal()
    try:
        quote = Quote(symbol=symbol, source="VCI")
        df = quote.intraday(symbol=symbol, page_size=10000, show_log=False)
        payload = dataframe_to_payload(df)
        save_raw_data(
            db=db, symbol=symbol, data_type="intraday", period=None, payload=payload
        )
        db.commit()
        tqdm.write(f"{symbol} intraday: saved")
    except Exception as e:
        db.rollback()
        tqdm.write(f"[SKIP] {symbol} intraday: {e}")
    finally:
        db.close()


def wait_before_request():
    global LAST_REQUEST_TIME
    sleep_seconds = env_float("AUTO_SLEEP_SECONDS", 8)
    with REQUEST_LOCK:
        now = time.monotonic()
        elapsed = now - LAST_REQUEST_TIME
        need_wait = sleep_seconds - elapsed
        if need_wait > 0:
            time.sleep(need_wait)
        LAST_REQUEST_TIME = time.monotonic()


def wait_or_stop(seconds: float):
    return STOP_COLLECTOR.wait(seconds)


def get_auto_max_retry():
    value = os.getenv("AUTO_MAX_RETRY", "5")
    try:
        return int(value)
    except Exception:
        return 5


# ── DEPRECATED: get_resume_start_date — thay bằng get_last_ohlcv_ts ─────
def get_resume_start_date(db, symbol: str, interval: str, default_start: str):
    """DEPRECATED — Dùng ``get_last_ohlcv_ts()`` từ market_repo."""
    last_time = (
        db.query(func.max(StockOhlcv.candle_time))
        .filter(StockOhlcv.symbol == symbol, StockOhlcv.interval == interval)
        .scalar()
    )
    if last_time is None:
        return default_start
    if interval == "1D":
        return last_time.strftime("%Y-%m-%d")
    return last_time.strftime("%Y-%m-%d")
