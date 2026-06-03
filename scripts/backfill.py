import argparse
import logging
import sys
from datetime import datetime, timedelta, date
from shared.utils.logging import setup_logging
from shared.db.session import SessionLocal
from shared.db.models import OHLCVPrice, Ticker
from services.ingestion.adapters.binance_adapter import BinanceAdapter
from services.ingestion.adapters.vnstock_adapter import VNStockAdapter
from sqlalchemy.dialects.postgresql import insert

# Setup logs
setup_logging()
logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(description="Backfill historical OHLCV data for Stock/Crypto")
    parser.add_argument("--symbol", type=str, required=True, help="Ticker symbol, e.g. FPT or BTC/USDT")
    parser.add_argument("--days", type=int, default=30, help="Number of historical days to backfill")
    parser.add_argument("--resolution", type=str, choices=["1h", "1d"], default="1d", help="Resolution: 1h or 1d")
    return parser.parse_args()

def run_backfill():
    args = parse_args()
    logger.info(f"Starting historical backfill for {args.symbol} ({args.days} days, res={args.resolution})")
    
    db = SessionLocal()
    ticker = db.query(Ticker).filter(Ticker.id == args.symbol).first()
    
    if not ticker:
        # Auto-create ticker
        asset_type = "crypto" if "/" in args.symbol else "stock"
        exchange = "binance" if asset_type == "crypto" else "hose"
        ticker = Ticker(id=args.symbol, name=args.symbol, asset_type=asset_type, exchange=exchange)
        db.add(ticker)
        db.commit()
        logger.info(f"Automatically created Ticker entry for '{args.symbol}'")

    count = 0
    try:
        if ticker.asset_type == "crypto":
            adapter = BinanceAdapter()
            since_time = datetime.utcnow() - timedelta(days=args.days)
            since_ms = int(since_time.timestamp() * 1000)
            
            candles = adapter.fetch_historical_ohlcv(
                symbol=args.symbol,
                timeframe=args.resolution,
                since_timestamp_ms=since_ms,
                limit=1000
            )
            
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
            adapter.close()
            
        else: # stock
            adapter = VNStockAdapter()
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=args.days)
            
            candles = adapter.fetch_historical_ohlcv(
                symbol=args.symbol,
                start_date=start_date,
                end_date=end_date,
                resolution=args.resolution
            )
            
            # Since VNStock adapter is mocked, we will log a warning but show standard insertion boilerplate
            if not candles:
                logger.warning("VNStockAdapter returned 0 historical candles. (Adapter currently mocked).")
                # TODO: Dev 2 should implement real crawler in services/ingestion/adapters/vnstock_adapter.py
            
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

        logger.info(f"Backfill complete! Upserted {count} records for {args.symbol}")
        
    except Exception as e:
        logger.error(f"Backfill process failed: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_backfill()
