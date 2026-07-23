"""
Retry VN Stocks backfill — Chạy lại phần cổ phiếu VN với encoding fix.

Lần chạy trước vnstock bị crash do Unicode encoding (cp1252) trên Windows.
Script này set encoding UTF-8 trước khi chạy.

Chạy:
    cd d:\\sources\\repos\\NCKH
    set PYTHONPATH=.
    set PYTHONIOENCODING=utf-8
    python -m scripts.backfill_vnstock
"""

import io
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# Fix Windows cp1252 encoding issues with vnstock emoji output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from shared.db.session import SessionLocal  # noqa: E402
from shared.db.repositories.market_repo import (  # noqa: E402
    ensure_exchange,
    ensure_symbol,
    upsert_ohlcv_raw,
    upsert_ohlcv,
    log_job,
    update_job,
    record_dq_check,
)
from services.ingestion.adapters.vnstock_adapter import VNStockAdapter  # noqa: E402

# Setup logging with UTF-8 handler
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(
            io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        )
    ],
)

DAYS = 730  # 2 năm

STOCK_SYMBOLS: list[str] = [
    "FPT",  # Công nghệ
    "VCB",  # Ngân hàng
    "MSN",  # Tiêu dùng (Masan)
    "VNM",  # Sữa (Vinamilk)
    "HPG",  # Thép (Hòa Phát)
    "TCB",  # Ngân hàng (Techcombank)
    "MBB",  # Ngân hàng (MB)
    "VIC",  # Bất động sản (Vingroup)
    "VHM",  # Bất động sản (Vinhomes)
    "SSI",  # Chứng khoán
    "GAS",  # Năng lượng (PV Gas)
    "PLX",  # Dầu khí (Petrolimex)
    "SAB",  # Bia (Sabeco)
    "MWG",  # Bán lẻ (Thế Giới Di Động)
    "ACB",  # Ngân hàng (Á Châu)
]


def backfill_stock(db, adapter: VNStockAdapter, symbol: str, days: int) -> dict:
    """Backfill 1 VN stock symbol. Returns summary dict."""
    resolution = "1d"
    exchange_id = ensure_exchange(
        db, "HOSE", "So Giao dich Chung khoan TP.HCM", "stock", "Asia/Ho_Chi_Minh"
    )
    symbol_id = ensure_symbol(db, exchange_id, symbol, "stock", "vnstock")

    job_id = log_job(
        db,
        "ingest",
        f"backfill_stock_{symbol}_{resolution}",
        "running",
        symbol_id=symbol_id,
        timeframe=resolution,
    )
    db.commit()

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    candles = adapter.fetch_historical_ohlcv(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        resolution=resolution,
    )

    if not candles:
        update_job(db, job_id, "success", rows_affected=0)
        db.commit()
        return {"symbol": symbol, "rows": 0, "status": "empty"}

    rows = []
    for c in candles:
        rows.append(
            {
                "symbol_id": symbol_id,
                "timeframe": resolution,
                "ts": c.timestamp,
                "open": Decimal(str(c.open)),
                "high": Decimal(str(c.high)),
                "low": Decimal(str(c.low)),
                "close": Decimal(str(c.close)),
                "volume": Decimal(str(c.volume)),
            }
        )

    raw_rows = [{**r, "source": "vnstock", "raw_payload": None} for r in rows]
    upsert_ohlcv_raw(db, raw_rows)
    affected = upsert_ohlcv(db, rows)

    filtered_out = len(rows) - affected
    record_dq_check(
        db=db,
        symbol_id=symbol_id,
        timeframe=resolution,
        check_name="high_low_check",
        passed=(filtered_out == 0),
        ts_start=min(r["ts"] for r in rows),
        ts_end=max(r["ts"] for r in rows),
        detail={"total_rows": len(rows), "filtered_rows": filtered_out},
    )

    update_job(db, job_id, "success", rows_affected=affected)
    db.commit()
    return {"symbol": symbol, "rows": affected, "status": "ok"}


def main() -> None:
    logger.info("=" * 60)
    logger.info("VN STOCKS BACKFILL — %d ngay, %d symbols", DAYS, len(STOCK_SYMBOLS))
    logger.info("=" * 60)

    results: list[dict] = []
    db = SessionLocal()

    try:
        adapter = VNStockAdapter()

        for i, symbol in enumerate(STOCK_SYMBOLS, 1):
            logger.info(
                "[%d/%d] Crawling %s (1d) — %d days...",
                i,
                len(STOCK_SYMBOLS),
                symbol,
                DAYS,
            )
            try:
                result = backfill_stock(db, adapter, symbol, DAYS)
                results.append(result)
                logger.info(
                    "  OK: %s -> %d rows [%s]", symbol, result["rows"], result["status"]
                )
            except Exception as e:
                logger.error("  FAILED: %s -> %s", symbol, e)
                db.rollback()
                results.append({"symbol": symbol, "rows": 0, "status": f"error: {e}"})

            # Rate limit between vnstock API calls
            time.sleep(2)
    finally:
        db.close()

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("VN STOCKS BACKFILL SUMMARY")
    logger.info("=" * 60)

    total = 0
    ok = 0
    for r in results:
        icon = (
            "OK"
            if r["status"] == "ok"
            else "EMPTY"
            if r["status"] == "empty"
            else "ERR"
        )
        logger.info("  [%s] %s -> %d rows", icon, r["symbol"], r["rows"])
        total += r["rows"]
        if r["status"] == "ok":
            ok += 1

    logger.info("")
    logger.info("Total: %d rows | Success: %d/%d", total, ok, len(results))
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
