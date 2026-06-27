import threading

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .binance_client import (
    COLLECTOR_STATUS,
    auto_collect_from_env,
    collect_klines,
    collect_many_klines,
    env_bool,
)
from .database import get_db
from .models import AggTrade, OrderBookSnapshot, RawBinanceData, SpotKline

app = FastAPI(
    title="Binance Data Collector",
    description="Lay du lieu Binance va luu vao PostgreSQL",
    version="2.0.0",
)


@app.on_event("startup")
def startup():
    # LƯU Ý: KHÔNG gọi Base.metadata.create_all() ở đây.
    # Schema do init.sql + Alembic quản lý.

    if env_bool("AUTO_COLLECT_ON_STARTUP", False):
        thread = threading.Thread(target=auto_collect_from_env, daemon=True)
        thread.start()


@app.get("/")
def home():
    return {
        "message": "Binance FastAPI dang chay",
        "docs": "/docs",
        "collector_status": "/collector/status",
    }


@app.get("/collector/status")
def collector_status():
    return COLLECTOR_STATUS


@app.post("/collect/klines")
def api_collect_klines(
    background_tasks: BackgroundTasks,
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("1m"),
    start: str = Query("2024-01-01T00:00:00"),
    end: str = Query("2024-01-02T00:00:00"),
):
    background_tasks.add_task(collect_klines, symbol, interval, start, end)

    return {
        "message": "Da bat dau lay du lieu klines",
        "symbol": symbol.upper(),
        "interval": interval,
        "start": start,
        "end": end,
    }


@app.post("/collect/all-klines")
def api_collect_all_klines(
    background_tasks: BackgroundTasks,
    symbol_mode: str = Query("USDT"),
    symbol_limit: int = Query(20),
    intervals: str = Query("1m,5m,15m,1h,4h,1d"),
    start: str = Query("2024-01-01T00:00:00"),
    end: str = Query(""),
    chunk: str = Query("month"),
):
    if COLLECTOR_STATUS["running"]:
        raise HTTPException(status_code=400, detail="Collector dang chay roi")

    interval_list = [item.strip() for item in intervals.split(",") if item.strip()]

    background_tasks.add_task(
        collect_many_klines, symbol_mode, symbol_limit, interval_list, start, end, chunk
    )

    return {
        "message": "Da bat dau lay nhieu symbol va nhieu interval",
        "symbol_mode": symbol_mode,
        "symbol_limit": symbol_limit,
        "intervals": interval_list,
        "start": start,
        "end": end,
        "chunk": chunk,
    }


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    kline_count = db.query(func.count(SpotKline.id)).scalar()
    agg_trade_count = db.query(func.count(AggTrade.id)).scalar()
    order_book_snapshot_count = db.query(func.count(OrderBookSnapshot.id)).scalar()
    raw_count = db.query(func.count(RawBinanceData.id)).scalar()

    # market.ohlcv count (schema chuẩn mới)
    market_ohlcv_count = (
        db.execute(text("SELECT count(*) FROM market.ohlcv")).scalar() or 0
    )

    return {
        "spot_klines": kline_count,
        "agg_trades": agg_trade_count,
        "order_book_snapshots": order_book_snapshot_count,
        "raw_binance_data": raw_count,
        "market_ohlcv": market_ohlcv_count,
    }
