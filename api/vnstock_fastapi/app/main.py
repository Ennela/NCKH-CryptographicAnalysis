import threading

from fastapi import FastAPI, BackgroundTasks, Depends, Query, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import StockOhlcv, StockRawData
from .vnstock_client import (
    collect_ohlcv,
    collect_many_ohlcv,
    auto_collect_from_env,
    COLLECTOR_STATUS,
    STOP_COLLECTOR,
    env_bool
)


app = FastAPI(
    title="VNStock Data Collector",
    description="Lay du lieu co phieu Viet Nam tu Vnstock va luu vao PostgreSQL",
    version="1.0.0"
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

    if env_bool("AUTO_COLLECT_ON_STARTUP", False):
        thread = threading.Thread(
            target=auto_collect_from_env,
            daemon=True
        )
        thread.start()


@app.get("/")
def home():
    return {
        "message": "VNStock FastAPI dang chay",
        "docs": "/docs",
        "collector_status": "/collector/status"
    }


@app.get("/collector/status")
def collector_status():
    return COLLECTOR_STATUS


@app.post("/collect/ohlcv")
def api_collect_ohlcv(
    background_tasks: BackgroundTasks,
    symbol: str = Query("FPT"),
    interval: str = Query("1D"),
    start: str = Query("2024-01-01"),
    end: str = Query("")
):
    background_tasks.add_task(
        collect_ohlcv,
        symbol,
        interval,
        start,
        end
    )

    return {
        "message": "Da bat dau lay du lieu OHLCV",
        "symbol": symbol.upper(),
        "interval": interval,
        "start": start,
        "end": end
    }


@app.post("/collect/all")
def api_collect_all(
    background_tasks: BackgroundTasks,
    symbols: str = Query("FPT,VNM,HPG,VCB,TCB"),
    intervals: str = Query("1D"),
    start: str = Query("2024-01-01"),
    end: str = Query("")
):
    if COLLECTOR_STATUS["running"]:
        raise HTTPException(
            status_code=400,
            detail="Collector dang chay roi"
        )

    symbol_list = [
        item.strip().upper()
        for item in symbols.split(",")
        if item.strip()
    ]

    interval_list = [
        item.strip()
        for item in intervals.split(",")
        if item.strip()
    ]

    background_tasks.add_task(
        collect_many_ohlcv,
        symbol_list,
        interval_list,
        start,
        end
    )

    return {
        "message": "Da bat dau lay nhieu ma co phieu",
        "symbols": symbol_list,
        "intervals": interval_list,
        "start": start,
        "end": end
    }


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    ohlcv_total = db.query(func.count(StockOhlcv.id)).scalar()
    raw_total = db.query(func.count(StockRawData.id)).scalar()

    return {
        "stock_ohlcv": ohlcv_total,
        "stock_raw_data": raw_total
    }

@app.get("/raw-summary")
def raw_summary(db: Session = Depends(get_db)):
    rows = (
        db.query(
            StockRawData.symbol,
            StockRawData.data_type,
            StockRawData.period,
            func.count(StockRawData.id)
        )
        .group_by(
            StockRawData.symbol,
            StockRawData.data_type,
            StockRawData.period
        )
        .order_by(
            StockRawData.symbol,
            StockRawData.data_type,
            StockRawData.period
        )
        .all()
    )

    return [
        {
            "symbol": row[0],
            "data_type": row[1],
            "period": row[2],
            "rows": row[3]
        }
        for row in rows
    ]

@app.get("/symbols")
def symbols(db: Session = Depends(get_db)):
    rows = (
        db.query(StockOhlcv.symbol)
        .distinct()
        .order_by(StockOhlcv.symbol)
        .all()
    )

    return {
        "symbols": [row[0] for row in rows]
    }


@app.get("/summary")
def summary(db: Session = Depends(get_db)):
    rows = (
        db.query(
            StockOhlcv.symbol,
            StockOhlcv.interval,
            func.count(StockOhlcv.id),
            func.min(StockOhlcv.candle_time),
            func.max(StockOhlcv.candle_time)
        )
        .group_by(
            StockOhlcv.symbol,
            StockOhlcv.interval
        )
        .order_by(
            StockOhlcv.symbol,
            StockOhlcv.interval
        )
        .all()
    )

    return [
        {
            "symbol": row[0],
            "interval": row[1],
            "rows": row[2],
            "from": row[3],
            "to": row[4]
        }
        for row in rows
    ]

@app.post("/collector/start")
def start_collector():
    if COLLECTOR_STATUS["running"]:
        raise HTTPException(
            status_code=400,
            detail="Collector dang chay roi"
        )

    STOP_COLLECTOR.clear()

    thread = threading.Thread(
        target=auto_collect_from_env,
        daemon=True
    )

    thread.start()

    return {
        "message": "Da bat dau collector"
    }


@app.post("/collector/stop")
def stop_collector():
    STOP_COLLECTOR.set()

    COLLECTOR_STATUS["message"] = "Dang dung theo yeu cau nguoi dung"

    return {
        "message": "Da gui lenh dung collector. Chuong trinh se dung sau khi request hien tai ket thuc."
    }