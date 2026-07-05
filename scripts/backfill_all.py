"""
Batch Backfill Script — Crawl 2 năm dữ liệu OHLCV cho tất cả symbols.

Chạy:
    cd d:\\sources\\repos\\NCKH
    set PYTHONPATH=.
    python -m scripts.backfill_all

Symbols + Resolution:
    - Crypto (Binance CCXT): 1d + 1h
    - Cổ phiếu VN (vnstock):  1d only
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from shared.utils.logging import setup_logging
from shared.db.session import SessionLocal
from shared.db.mappers import split_crypto_pair
from shared.db.repositories.market_repo import (
    ensure_exchange,
    ensure_symbol,
    upsert_ohlcv_raw,
    upsert_ohlcv,
    log_job,
    update_job,
    record_dq_check,
)
from services.ingestion.adapters.binance_adapter import BinanceAdapter
from services.ingestion.adapters.vnstock_adapter import VNStockAdapter

setup_logging()
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
# Cấu hình — Symbols & Parameters
# ══════════════════════════════════════════════════════════════════════════

DAYS = 730  # 2 năm

# Crypto symbols — top 10 theo market cap, giao dịch 24/7
CRYPTO_SYMBOLS: list[str] = [
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "DOGE/USDT",
    "DOT/USDT",
    "AVAX/USDT",
    "LINK/USDT",
]
CRYPTO_RESOLUTIONS: list[str] = ["1d", "1h"]

# Cổ phiếu VN — đa ngành: ngân hàng, công nghệ, bất động sản, tiêu dùng, năng lượng
STOCK_SYMBOLS: list[str] = [
    "FPT",   # Công nghệ
    "VCB",   # Ngân hàng
    "MSN",   # Tiêu dùng (Masan)
    "VNM",   # Sữa (Vinamilk)
    "HPG",   # Thép (Hòa Phát)
    "TCB",   # Ngân hàng (Techcombank)
    "MBB",   # Ngân hàng (MB)
    "VIC",   # Bất động sản (Vingroup)
    "VHM",   # Bất động sản (Vinhomes)
    "SSI",   # Chứng khoán
    "GAS",   # Năng lượng (PV Gas)
    "PLX",   # Dầu khí (Petrolimex)
    "SAB",   # Bia (Sabeco)
    "MWG",   # Bán lẻ (Thế Giới Di Động)
    "ACB",   # Ngân hàng (Á Châu)
]
STOCK_RESOLUTIONS: list[str] = ["1d"]  # vnstock chỉ hỗ trợ daily


# ══════════════════════════════════════════════════════════════════════════
# Helper: crawl 1 crypto symbol
# ══════════════════════════════════════════════════════════════════════════


def backfill_crypto(
    db,
    adapter: BinanceAdapter,
    symbol: str,
    resolution: str,
    days: int,
) -> dict:
    """Backfill 1 crypto symbol. Returns summary dict."""
    ticker_str = symbol.replace("/", "")
    base, quote = split_crypto_pair(ticker_str)
    if not base or not quote:
        if "/" in symbol:
            base, quote = symbol.split("/")
        else:
            base, quote = symbol, "USDT"

    exchange_id = ensure_exchange(
        db, "BINANCE", "Binance Cryptocurrency Exchange", "crypto", "UTC"
    )
    symbol_id = ensure_symbol(
        db, exchange_id, ticker_str, "crypto", "binance", base, quote
    )

    job_id = log_job(
        db, "ingest", f"backfill_crypto_{ticker_str}_{resolution}",
        "running", symbol_id=symbol_id, timeframe=resolution,
    )
    db.commit()

    since_time = datetime.now(timezone.utc) - timedelta(days=days)
    cursor_ms = int(since_time.timestamp() * 1000)

    # Pagination loop
    candles = []
    batch_num = 0
    while True:
        batch_num += 1
        batch = adapter.fetch_historical_ohlcv(
            symbol=symbol,
            timeframe=resolution,
            since_timestamp_ms=cursor_ms,
            limit=1000,
        )
        if not batch:
            break
        candles.extend(batch)
        logger.info(
            f"  [{symbol} {resolution}] Batch {batch_num}: "
            f"+{len(batch)} candles (total: {len(candles)})"
        )
        last_ts_ms = int(batch[-1].timestamp.timestamp() * 1000)
        cursor_ms = last_ts_ms + 1
        if len(batch) < 1000:
            break
        time.sleep(0.5)

    if not candles:
        update_job(db, job_id, "success", rows_affected=0)
        db.commit()
        return {"symbol": symbol, "resolution": resolution, "rows": 0, "status": "empty"}

    rows = []
    for c in candles:
        rows.append({
            "symbol_id": symbol_id,
            "timeframe": resolution,
            "ts": c.timestamp,
            "open": Decimal(str(c.open)),
            "high": Decimal(str(c.high)),
            "low": Decimal(str(c.low)),
            "close": Decimal(str(c.close)),
            "volume": Decimal(str(c.volume)),
        })

    raw_rows = [{**r, "source": "binance", "raw_payload": None} for r in rows]
    upsert_ohlcv_raw(db, raw_rows)
    affected = upsert_ohlcv(db, rows)

    # Data quality
    filtered_out = len(rows) - affected
    record_dq_check(
        db=db, symbol_id=symbol_id, timeframe=resolution,
        check_name="high_low_check", passed=(filtered_out == 0),
        ts_start=min(r["ts"] for r in rows),
        ts_end=max(r["ts"] for r in rows),
        detail={"total_rows": len(rows), "filtered_rows": filtered_out},
    )

    update_job(db, job_id, "success", rows_affected=affected)
    db.commit()
    return {"symbol": symbol, "resolution": resolution, "rows": affected, "status": "ok"}


# ══════════════════════════════════════════════════════════════════════════
# Helper: crawl 1 stock symbol
# ══════════════════════════════════════════════════════════════════════════


def backfill_stock(
    db,
    adapter: VNStockAdapter,
    symbol: str,
    resolution: str,
    days: int,
) -> dict:
    """Backfill 1 VN stock symbol. Returns summary dict."""
    exchange_id = ensure_exchange(
        db, "HOSE", "Sở Giao dịch Chứng khoán TP.HCM", "stock", "Asia/Ho_Chi_Minh"
    )
    symbol_id = ensure_symbol(db, exchange_id, symbol, "stock", "vnstock")

    job_id = log_job(
        db, "ingest", f"backfill_stock_{symbol}_{resolution}",
        "running", symbol_id=symbol_id, timeframe=resolution,
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
        return {"symbol": symbol, "resolution": resolution, "rows": 0, "status": "empty"}

    rows = []
    for c in candles:
        rows.append({
            "symbol_id": symbol_id,
            "timeframe": resolution,
            "ts": c.timestamp,
            "open": Decimal(str(c.open)),
            "high": Decimal(str(c.high)),
            "low": Decimal(str(c.low)),
            "close": Decimal(str(c.close)),
            "volume": Decimal(str(c.volume)),
        })

    raw_rows = [{**r, "source": "vnstock", "raw_payload": None} for r in rows]
    upsert_ohlcv_raw(db, raw_rows)
    affected = upsert_ohlcv(db, rows)

    # Data quality
    filtered_out = len(rows) - affected
    record_dq_check(
        db=db, symbol_id=symbol_id, timeframe=resolution,
        check_name="high_low_check", passed=(filtered_out == 0),
        ts_start=min(r["ts"] for r in rows),
        ts_end=max(r["ts"] for r in rows),
        detail={"total_rows": len(rows), "filtered_rows": filtered_out},
    )

    update_job(db, job_id, "success", rows_affected=affected)
    db.commit()
    return {"symbol": symbol, "resolution": resolution, "rows": affected, "status": "ok"}


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════


def main() -> None:
    logger.info("=" * 70)
    logger.info("BACKFILL ALL — Crawl %d ngày dữ liệu OHLCV", DAYS)
    logger.info("=" * 70)

    results: list[dict] = []
    db = SessionLocal()

    try:
        # ── Crypto ────────────────────────────────────────────────────
        logger.info("\n>>> CRYPTO — %d symbols × %d resolutions",
                    len(CRYPTO_SYMBOLS), len(CRYPTO_RESOLUTIONS))

        adapter_binance = BinanceAdapter()
        for symbol in CRYPTO_SYMBOLS:
            for resolution in CRYPTO_RESOLUTIONS:
                logger.info(f"\n{'─'*50}")
                logger.info(f"Crawling {symbol} ({resolution}) — {DAYS} days...")
                try:
                    result = backfill_crypto(
                        db, adapter_binance, symbol, resolution, DAYS
                    )
                    results.append(result)
                    logger.info(
                        f"✓ {symbol} ({resolution}): {result['rows']} rows"
                    )
                except Exception as e:
                    logger.error(f"✗ {symbol} ({resolution}) FAILED: {e}")
                    db.rollback()
                    results.append({
                        "symbol": symbol, "resolution": resolution,
                        "rows": 0, "status": f"error: {e}",
                    })
                # Sleep giữa các symbol/resolution để tránh rate limit
                time.sleep(1)

        adapter_binance.close()

        # ── VN Stocks ─────────────────────────────────────────────────
        logger.info("\n>>> VN STOCKS — %d symbols × %d resolutions",
                    len(STOCK_SYMBOLS), len(STOCK_RESOLUTIONS))

        adapter_vnstock = VNStockAdapter()
        for symbol in STOCK_SYMBOLS:
            for resolution in STOCK_RESOLUTIONS:
                logger.info(f"\n{'─'*50}")
                logger.info(f"Crawling {symbol} ({resolution}) — {DAYS} days...")
                try:
                    result = backfill_stock(
                        db, adapter_vnstock, symbol, resolution, DAYS
                    )
                    results.append(result)
                    logger.info(
                        f"✓ {symbol} ({resolution}): {result['rows']} rows"
                    )
                except Exception as e:
                    logger.error(f"✗ {symbol} ({resolution}) FAILED: {e}")
                    db.rollback()
                    results.append({
                        "symbol": symbol, "resolution": resolution,
                        "rows": 0, "status": f"error: {e}",
                    })
                # Rate limit cho vnstock API
                time.sleep(2)

    finally:
        db.close()

    # ── Summary ───────────────────────────────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("BACKFILL SUMMARY")
    logger.info("=" * 70)

    total_rows = 0
    ok_count = 0
    fail_count = 0
    for r in results:
        status_icon = "✓" if r["status"] == "ok" else "⚠" if r["status"] == "empty" else "✗"
        logger.info(
            f"  {status_icon} {r['symbol']:>12s} ({r['resolution']}) "
            f"→ {r['rows']:>6d} rows  [{r['status']}]"
        )
        total_rows += r["rows"]
        if r["status"] == "ok":
            ok_count += 1
        elif r["status"] != "empty":
            fail_count += 1

    logger.info(f"\nTotal: {total_rows} rows inserted/updated")
    logger.info(f"Success: {ok_count} | Empty: {len(results) - ok_count - fail_count} | Failed: {fail_count}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
