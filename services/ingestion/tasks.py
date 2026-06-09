import logging
from datetime import timedelta
from typing import List
from decimal import Decimal
from celery_app import celery_app
from shared.db.session import SessionLocal
from shared.utils.timezone import now_utc
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
from adapters.binance_adapter import BinanceAdapter
from adapters.vnstock_adapter import VNStockAdapter

logger = logging.getLogger(__name__)


@celery_app.task
def ingest_crypto_task(symbols: List[str], resolution: str = "1h") -> int:
    """
    Celery task to fetch latest cryptocurrency prices from Binance and upsert to database.
    """
    logger.info(f"Starting crypto ingestion task for {symbols} ({resolution})")
    adapter = BinanceAdapter()
    db = SessionLocal()
    count = 0

    try:
        # Determine since time (e.g. last 24 hours for hourly, last 30 days for daily)
        since_delta = timedelta(days=1) if resolution == "1h" else timedelta(days=30)
        since_time = now_utc() - since_delta
        since_ms = int(since_time.timestamp() * 1000)

        # Ensure exchange exists
        exchange_id = ensure_exchange(
            db, "BINANCE", "Binance Cryptocurrency Exchange", "crypto", "UTC"
        )

        # Make sure tickers exist in db
        for symbol in symbols:
            # Normalize symbol format for DB: remove slash (e.g. 'BTC/USDT' -> 'BTCUSDT')
            ticker_str = symbol.replace("/", "")
            base, quote = split_crypto_pair(ticker_str)
            if not base or not quote:
                if "/" in symbol:
                    base, quote = symbol.split("/")
                else:
                    base, quote = symbol, "USDT"

            symbol_id = ensure_symbol(
                db, exchange_id, ticker_str, "crypto", "binance", base, quote
            )

            # Log job start
            job_id = log_job(
                db,
                "ingest",
                f"crypto_ingest_{ticker_str}",
                "running",
                symbol_id=symbol_id,
                timeframe=resolution,
            )
            db.commit()

            try:
                candles = adapter.fetch_historical_ohlcv(
                    symbol=symbol,  # CCXT adapter expects original symbol (e.g. 'BTC/USDT')
                    timeframe=resolution,
                    since_timestamp_ms=since_ms,
                    limit=100,
                )

                if candles:
                    rows = []
                    for candle in candles:
                        rows.append(
                            {
                                "symbol_id": symbol_id,
                                "timeframe": resolution,
                                "ts": candle.timestamp,
                                "open": Decimal(str(candle.open)),
                                "high": Decimal(str(candle.high)),
                                "low": Decimal(str(candle.low)),
                                "close": Decimal(str(candle.close)),
                                "volume": Decimal(str(candle.volume)),
                            }
                        )

                    # Map and validate
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
                    count += affected_clean

                    # Record Data Quality Check
                    filtered_out = len(rows) - len(clean_rows)
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

                    update_job(db, job_id, "success", rows_affected=affected_clean)
                else:
                    update_job(db, job_id, "success", rows_affected=0)

                db.commit()
                logger.info(f"Upserted records for {symbol}")

            except Exception as e:
                logger.error(f"Failed to ingest crypto data for {symbol}: {str(e)}")
                db.rollback()
                update_job(db, job_id, "failed", error_message=str(e))
                db.commit()

    except Exception as e:
        logger.error(f"Failed to setup crypto ingestion: {str(e)}")
    finally:
        adapter.close()
        db.close()

    return count


@celery_app.task
def ingest_stocks_task(symbols: List[str], resolution: str = "1d") -> int:
    """
    Celery task to fetch latest Vietnamese stock prices from vnstock and upsert to database.
    """
    logger.info(f"Starting stock ingestion task for {symbols} ({resolution})")
    adapter = VNStockAdapter()
    db = SessionLocal()
    count = 0

    try:
        # Stock market data is usually pulled for the last few days to handle weekends/holidays
        end_date = now_utc().date()
        start_date = end_date - timedelta(days=7)

        # Ensure exchange exists
        exchange_id = ensure_exchange(
            db, "HOSE", "Sở Giao dịch Chứng khoán TP.HCM", "stock", "Asia/Ho_Chi_Minh"
        )

        # Make sure tickers exist in db
        for symbol in symbols:
            symbol_id = ensure_symbol(db, exchange_id, symbol, "stock", "vnstock")

            # Log job start
            job_id = log_job(
                db,
                "ingest",
                f"stock_ingest_{symbol}",
                "running",
                symbol_id=symbol_id,
                timeframe=resolution,
            )
            db.commit()

            try:
                candles = adapter.fetch_historical_ohlcv(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    resolution=resolution,
                )

                if candles:
                    rows = []
                    for candle in candles:
                        rows.append(
                            {
                                "symbol_id": symbol_id,
                                "timeframe": resolution,
                                "ts": candle.timestamp,
                                "open": Decimal(str(candle.open)),
                                "high": Decimal(str(candle.high)),
                                "low": Decimal(str(candle.low)),
                                "close": Decimal(str(candle.close)),
                                "volume": Decimal(str(candle.volume)),
                            }
                        )

                    # Map and validate
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
                    count += affected_clean

                    # Record Data Quality Check
                    filtered_out = len(rows) - len(clean_rows)
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

                    update_job(db, job_id, "success", rows_affected=affected_clean)
                else:
                    update_job(db, job_id, "success", rows_affected=0)

                db.commit()
                logger.info(f"Upserted records for {symbol}")

            except Exception as e:
                logger.error(f"Failed to ingest stock data for {symbol}: {str(e)}")
                db.rollback()
                update_job(db, job_id, "failed", error_message=str(e))
                db.commit()

    except Exception as e:
        logger.error(f"Failed to setup stock ingestion: {str(e)}")
    finally:
        db.close()

    return count
