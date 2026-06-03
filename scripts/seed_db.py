import logging
import random
from datetime import datetime, timezone, timedelta
from shared.utils.logging import setup_logging
from shared.db.session import SessionLocal
from shared.db.models import Ticker, OHLCVPrice
from sqlalchemy.dialects.postgresql import insert

setup_logging()
logger = logging.getLogger(__name__)

def seed_database():
    logger.info("Starting database seeding...")
    db = SessionLocal()
    
    # 1. Seed Tickers
    tickers = [
        Ticker(id="FPT", name="Công ty Cổ phần FPT", asset_type="stock", exchange="hose"),
        Ticker(id="VCB", name="Ngân hàng Vietcombank", asset_type="stock", exchange="hose"),
        Ticker(id="MSN", name="Tập đoàn Masan", asset_type="stock", exchange="hose"),
        Ticker(id="BTC/USDT", name="Bitcoin / Tether", asset_type="crypto", exchange="binance"),
        Ticker(id="ETH/USDT", name="Ethereum / Tether", asset_type="crypto", exchange="binance"),
    ]
    
    for t in tickers:
        stmt = insert(Ticker).values(
            id=t.id,
            name=t.name,
            asset_type=t.asset_type,
            exchange=t.exchange,
            is_active=True
        ).on_conflict_do_nothing()
        db.execute(stmt)
    db.commit()
    logger.info("Tickers seeded.")

    # 2. Seed Mock OHLCV Candles (Last 100 days for 1d, last 100 hours for 1h)
    now = datetime.now(timezone.utc)
    candle_count = 0
    
    # Baseline closing prices for mock walk
    baselines = {
        "FPT": 130000.0,
        "VCB": 95000.0,
        "MSN": 75000.0,
        "BTC/USDT": 68000.0,
        "ETH/USDT": 37000.0
    }
    
    for ticker_id, baseline in baselines.items():
        # Let's seed both 1d (and 1h if crypto)
        resolutions = ["1d"]
        if "/" in ticker_id:
            resolutions.append("1h")
            
        for res in resolutions:
            logger.info(f"Seeding mock candles for {ticker_id} (res={res})...")
            step = timedelta(days=1) if res == "1d" else timedelta(hours=1)
            current_price = baseline
            
            for i in range(100, 0, -1):
                timestamp = now - (step * i)
                
                # Mock random walk prices
                change = random.uniform(-0.02, 0.02)
                close_price = current_price * (1 + change)
                open_price = current_price
                high_price = max(open_price, close_price) * (1 + random.uniform(0.001, 0.01))
                low_price = min(open_price, close_price) * (1 - random.uniform(0.001, 0.01))
                volume = random.uniform(10000, 500000) if res == "1d" else random.uniform(500, 20000)
                
                current_price = close_price  # Walk forward
                
                stmt = insert(OHLCVPrice).values(
                    timestamp=timestamp,
                    ticker_id=ticker_id,
                    resolution=res,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume
                )
                
                # UPSERT
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
                candle_count += 1
                
    db.commit()
    db.close()
    logger.info(f"Database seed complete. Total mock candles inserted: {candle_count}")

if __name__ == "__main__":
    seed_database()
