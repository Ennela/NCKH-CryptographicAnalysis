import logging
from datetime import datetime, timedelta, date
from typing import List
from celery_app import celery_app
from sqlalchemy.dialects.postgresql import insert
from shared.db.session import SessionLocal
from shared.db.models import OHLCVPrice, Ticker
from shared.utils.timezone import now_utc
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

        # Make sure tickers exist in db
        for symbol in symbols:
            ticker = db.query(Ticker).filter(Ticker.id == symbol).first()
            if not ticker:
                ticker = Ticker(id=symbol, name=symbol.split("/")[0], asset_type="crypto", exchange="binance")
                db.add(ticker)
                db.commit()

            candles = adapter.fetch_historical_ohlcv(
                symbol=symbol,
                timeframe=resolution,
                since_timestamp_ms=since_ms,
                limit=100
            )

            # Upsert into TimescaleDB
            for candle in candles:
                stmt = insert(OHLCVPrice).values(
                    timestamp=candle.timestamp,
                    ticker_id=candle.ticker_id,
                    resolution=candle.resolution,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume
                )
                
                # Perform UPSERT on conflict
                stmt = stmt.on_conflict_do_update(
                    index_elements=["timestamp", "ticker_id", "resolution"],
                    set_={
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume
                    }
                )
                db.execute(stmt)
                count += 1
            
            db.commit()
            logger.info(f"Upserted {len(candles)} records for {symbol}")

    except Exception as e:
        logger.error(f"Failed to ingest crypto data: {str(e)}")
        db.rollback()
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

        # Make sure tickers exist in db
        for symbol in symbols:
            ticker = db.query(Ticker).filter(Ticker.id == symbol).first()
            if not ticker:
                ticker = Ticker(id=symbol, name=symbol, asset_type="stock", exchange="hose")
                db.add(ticker)
                db.commit()

            candles = adapter.fetch_historical_ohlcv(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                resolution=resolution
            )

            # Upsert into TimescaleDB
            for candle in candles:
                stmt = insert(OHLCVPrice).values(
                    timestamp=candle.timestamp,
                    ticker_id=candle.ticker_id,
                    resolution=candle.resolution,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["timestamp", "ticker_id", "resolution"],
                    set_={
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume
                    }
                )
                db.execute(stmt)
                count += 1
            
            db.commit()
            logger.info(f"Upserted {len(candles)} records for {symbol}")

    except Exception as e:
        logger.error(f"Failed to ingest stock data: {str(e)}")
        db.rollback()
    finally:
        db.close()
        
    return count
