import logging
from datetime import datetime
from typing import List
import ccxt
from shared.schemas.ohlcv import OHLCVCreate
from shared.utils.timezone import to_utc

logger = logging.getLogger(__name__)


class BinanceAdapter:
    """
    Adapter to fetch historical market data for Cryptocurrencies from Binance using CCXT.
    """

    def __init__(self, api_key: str = None, api_secret: str = None):
        # Public endpoints do not require API keys, but authenticated ones do.
        self.exchange = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            }
        )

    def fetch_historical_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since_timestamp_ms: int = None,
        limit: int = 100,
    ) -> List[OHLCVCreate]:
        """
        Fetch OHLCV candles from Binance.
        `symbol` format: 'BTC/USDT'
        `timeframe` format: '1h' or '1d'
        `since_timestamp_ms` format: unix timestamp in milliseconds
        """
        logger.info(
            f"Fetching Binance CCXT data for {symbol} (timeframe={timeframe}, limit={limit})"
        )

        try:
            # CCXT call: fetch_ohlcv returns list of lists:
            # [ [timestamp_ms, open, high, low, close, volume], ... ]
            raw_candles = self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=since_timestamp_ms,
                limit=limit,
            )

            ohlcv_list = []
            for candle in raw_candles:
                ts = datetime.fromtimestamp(candle[0] / 1000.0)
                ohlcv_list.append(
                    OHLCVCreate(
                        timestamp=to_utc(ts),
                        ticker_id=symbol,
                        resolution=timeframe,
                        open=float(candle[1]),
                        high=float(candle[2]),
                        low=float(candle[3]),
                        close=float(candle[4]),
                        volume=float(candle[5]),
                    )
                )
            return ohlcv_list

        except Exception as e:
            logger.error(f"Error fetching Binance data for {symbol}: {str(e)}")
            # TODO: Add robust error logging / alerting (e.g. Sentry)
            return []

    def close(self):
        """Close exchange connection."""
        if hasattr(self.exchange, "close"):
            try:
                self.exchange.close()
            except Exception:
                pass
