import argparse
import logging
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

# Setup logs
setup_logging()
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill historical OHLCV data for Stock/Crypto"
    )
    parser.add_argument(
        "--symbol", type=str, required=True, help="Ticker symbol, e.g. FPT or BTC/USDT"
    )
    parser.add_argument(
        "--days", type=int, default=30, help="Number of historical days to backfill"
    )
    parser.add_argument(
        "--resolution",
        type=str,
        choices=["1h", "1d"],
        default="1d",
        help="Resolution: 1h or 1d",
    )
    return parser.parse_args()


def run_backfill():
    args = parse_args()
    logger.info(
        f"Starting historical backfill for {args.symbol} ({args.days} days, res={args.resolution})"
    )

    db = SessionLocal()

    asset_type = "crypto" if "/" in args.symbol else "stock"

    try:
        if asset_type == "crypto":
            exchange_id = ensure_exchange(
                db, "BINANCE", "Binance Cryptocurrency Exchange", "crypto", "UTC"
            )
            ticker_str = args.symbol.replace("/", "")
            base, quote = split_crypto_pair(ticker_str)
            if not base or not quote:
                if "/" in args.symbol:
                    base, quote = args.symbol.split("/")
                else:
                    base, quote = args.symbol, "USDT"

            symbol_id = ensure_symbol(
                db, exchange_id, ticker_str, "crypto", "binance", base, quote
            )

            # Log job
            job_id = log_job(
                db,
                "ingest",
                f"backfill_crypto_{ticker_str}",
                "running",
                symbol_id=symbol_id,
                timeframe=args.resolution,
            )
            db.commit()

            try:
                adapter = BinanceAdapter()
                since_time = datetime.now(timezone.utc) - timedelta(days=args.days)
                since_ms = int(since_time.timestamp() * 1000)

                candles = adapter.fetch_historical_ohlcv(
                    symbol=args.symbol,
                    timeframe=args.resolution,
                    since_timestamp_ms=since_ms,
                    limit=1000,
                )

                if candles:
                    rows = []
                    for candle in candles:
                        rows.append(
                            {
                                "symbol_id": symbol_id,
                                "timeframe": args.resolution,
                                "ts": candle.timestamp,
                                "open": Decimal(str(candle.open)),
                                "high": Decimal(str(candle.high)),
                                "low": Decimal(str(candle.low)),
                                "close": Decimal(str(candle.close)),
                                "volume": Decimal(str(candle.volume)),
                            }
                        )

                    raw_rows = [
                        {**r, "source": "binance", "raw_payload": None} for r in rows
                    ]
                    clean_rows = []
                    for r in rows:
                        if (
                            r["high"] >= r["low"]
                            and r["open"] >= 0
                            and r["close"] >= 0
                            and r["volume"] >= 0
                        ):
                            clean_rows.append(r)

                    upsert_ohlcv_raw(db, raw_rows)
                    affected_clean = upsert_ohlcv(db, clean_rows)

                    # Log quality metrics
                    filtered_out = len(rows) - len(clean_rows)
                    record_dq_check(
                        db=db,
                        symbol_id=symbol_id,
                        timeframe=args.resolution,
                        check_name="high_low_check",
                        passed=(filtered_out == 0),
                        ts_start=min(r["ts"] for r in rows),
                        ts_end=max(r["ts"] for r in rows),
                        detail={"total_rows": len(rows), "filtered_rows": filtered_out},
                    )

                    update_job(db, job_id, "success", rows_affected=affected_clean)
                    logger.info(
                        f"Backfill complete! Upserted {affected_clean} records for {args.symbol}"
                    )
                else:
                    update_job(db, job_id, "success", rows_affected=0)
                    logger.warning(f"No candles retrieved for {args.symbol}")

                db.commit()
                adapter.close()

            except Exception as e:
                logger.error(f"Backfill process for {args.symbol} failed: {str(e)}")
                db.rollback()
                update_job(db, job_id, "failed", error_message=str(e))
                db.commit()

        else:  # stock
            exchange_id = ensure_exchange(
                db,
                "HOSE",
                "Sở Giao dịch Chứng khoán TP.HCM",
                "stock",
                "Asia/Ho_Chi_Minh",
            )
            symbol_id = ensure_symbol(db, exchange_id, args.symbol, "stock", "vnstock")

            # Log job
            job_id = log_job(
                db,
                "ingest",
                f"backfill_stock_{args.symbol}",
                "running",
                symbol_id=symbol_id,
                timeframe=args.resolution,
            )
            db.commit()

            try:
                adapter = VNStockAdapter()
                end_date = datetime.now(timezone.utc).date()
                start_date = end_date - timedelta(days=args.days)

                candles = adapter.fetch_historical_ohlcv(
                    symbol=args.symbol,
                    start_date=start_date,
                    end_date=end_date,
                    resolution=args.resolution,
                )

                if candles:
                    rows = []
                    for candle in candles:
                        rows.append(
                            {
                                "symbol_id": symbol_id,
                                "timeframe": args.resolution,
                                "ts": candle.timestamp,
                                "open": Decimal(str(candle.open)),
                                "high": Decimal(str(candle.high)),
                                "low": Decimal(str(candle.low)),
                                "close": Decimal(str(candle.close)),
                                "volume": Decimal(str(candle.volume)),
                            }
                        )

                    raw_rows = [
                        {**r, "source": "vnstock", "raw_payload": None} for r in rows
                    ]
                    clean_rows = []
                    for r in rows:
                        if (
                            r["high"] >= r["low"]
                            and r["open"] >= 0
                            and r["close"] >= 0
                            and r["volume"] >= 0
                        ):
                            clean_rows.append(r)

                    upsert_ohlcv_raw(db, raw_rows)
                    affected_clean = upsert_ohlcv(db, clean_rows)

                    # Log quality metrics
                    filtered_out = len(rows) - len(clean_rows)
                    record_dq_check(
                        db=db,
                        symbol_id=symbol_id,
                        timeframe=args.resolution,
                        check_name="high_low_check",
                        passed=(filtered_out == 0),
                        ts_start=min(r["ts"] for r in rows),
                        ts_end=max(r["ts"] for r in rows),
                        detail={"total_rows": len(rows), "filtered_rows": filtered_out},
                    )

                    update_job(db, job_id, "success", rows_affected=affected_clean)
                    logger.info(
                        f"Backfill complete! Upserted {affected_clean} records for {args.symbol}"
                    )
                else:
                    update_job(db, job_id, "success", rows_affected=0)
                    logger.warning("VNStockAdapter returned 0 historical candles.")

                db.commit()

            except Exception as e:
                logger.error(f"Backfill process failed: {str(e)}")
                db.rollback()
                update_job(db, job_id, "failed", error_message=str(e))
                db.commit()

    finally:
        db.close()


if __name__ == "__main__":
    run_backfill()
