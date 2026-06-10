import logging
from datetime import date, datetime, timezone
from typing import List
from shared.schemas.ohlcv import OHLCVCreate

logger = logging.getLogger(__name__)


class VNStockAdapter:
    """
    Adapter to fetch historical market data for Vietnamese stocks using vnstock library.
    """

    def __init__(self):
        try:
            from vnstock import Vnstock
            self._vnstock = Vnstock
            logger.info("vnstock library initialized successfully")
        except ImportError:
            logger.error("vnstock library not installed. Run: pip install vnstock")
            self._vnstock = None

    def fetch_historical_ohlcv(
        self, symbol: str, start_date: date, end_date: date, resolution: str = "1d"
    ) -> List[OHLCVCreate]:
        """
        Fetch OHLCV candles for a Vietnamese stock ticker.

        Args:
            symbol: Stock ticker, e.g. 'FPT', 'VCB', 'MSN'
            start_date: Start date for historical data
            end_date: End date for historical data
            resolution: '1d' for daily data (vnstock only supports daily)

        Returns:
            List of OHLCVCreate objects
        """
        logger.info(
            f"Fetching vnstock data for {symbol} from {start_date} to {end_date} (res={resolution})"
        )

        if self._vnstock is None:
            logger.error("vnstock not available, returning empty list")
            return []

        try:
            # Initialize vnstock for the given symbol
            stock = self._vnstock().stock(symbol=symbol, source="VCI")

            # Fetch historical price data
            df = stock.quote.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1D",
            )

            if df is None or df.empty:
                logger.warning(f"No data returned from vnstock for {symbol}")
                return []

            logger.info(f"Retrieved {len(df)} rows from vnstock for {symbol}")

            ohlcv_list = []
            for _, row in df.iterrows():
                # Parse the timestamp from the 'time' column
                ts_raw = row.get("time") or row.get("date") or row.get("TradingDate")
                if ts_raw is None:
                    continue

                if isinstance(ts_raw, str):
                    ts = datetime.strptime(ts_raw, "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                elif isinstance(ts_raw, date):
                    ts = datetime(
                        ts_raw.year, ts_raw.month, ts_raw.day, tzinfo=timezone.utc
                    )
                else:
                    ts = ts_raw
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)

                # vnstock column names may vary; try common patterns
                open_val = _get_col(row, ["open", "Open"])
                high_val = _get_col(row, ["high", "High"])
                low_val = _get_col(row, ["low", "Low"])
                close_val = _get_col(row, ["close", "Close"])
                volume_val = _get_col(row, ["volume", "Volume"])

                if any(
                    v is None for v in [open_val, high_val, low_val, close_val, volume_val]
                ):
                    logger.warning(f"Skipping row with missing OHLCV data: {row.to_dict()}")
                    continue

                ohlcv_list.append(
                    OHLCVCreate(
                        timestamp=ts,
                        ticker_id=symbol.upper(),
                        resolution=resolution,
                        open=float(open_val),
                        high=float(high_val),
                        low=float(low_val),
                        close=float(close_val),
                        volume=float(volume_val),
                    )
                )

            logger.info(f"Parsed {len(ohlcv_list)} OHLCV candles for {symbol}")
            return ohlcv_list

        except Exception as e:
            logger.error(f"Error fetching vnstock data for {symbol}: {str(e)}")
            return []


def _get_col(row, candidates: list):
    """Try multiple column name candidates and return the first match."""
    for col in candidates:
        if col in row.index:
            return row[col]
    return None
