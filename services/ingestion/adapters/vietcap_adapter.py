"""Daily OHLCV for Vietnamese stocks from Vietcap's public chart endpoint.

Replaces the vnstock package (quarantined on PyPI since 2026-09) for the daily
stock collector. vnstock's "VCI" source used this same endpoint; calling it
directly with httpx needs no extra dependency.

Prices are dividend/split ADJUSTED as of the request date, in VND. They are
divided by 1000 to keep the unit of the existing data (thousand VND). Because
the adjustment changes after every corporate action, a whole history must be
refetched (scripts/backfill_vnstock.py), not only appended to.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import List

import httpx

from shared.schemas.ohlcv import OHLCVCreate

logger = logging.getLogger(__name__)

VIETCAP_CHART_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
# The endpoint rejects requests without a browser-like origin.
_HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn",
    "User-Agent": "Mozilla/5.0",
}
PRICE_DIVISOR = 1000.0  # VND -> thousand VND (unit of market.ohlcv for stocks)


class VietcapAdapter:
    """Fetch daily candles for HOSE tickers (e.g. FPT, VCB) from Vietcap."""

    available = True  # same interface as VNStockAdapter; no optional import

    def __init__(self, timeout: float = 20.0) -> None:
        self._client = httpx.Client(timeout=timeout, headers=_HEADERS)

    def close(self) -> None:
        self._client.close()

    def fetch_historical_ohlcv(
        self, symbol: str, start_date: date, end_date: date, resolution: str = "1d"
    ) -> List[OHLCVCreate]:
        """Return candles with start_date <= day <= end_date, oldest first.

        Network or format errors are logged and give an empty list, so the
        caller records a failed/empty job instead of writing partial data.
        """
        if resolution != "1d":
            raise ValueError("VietcapAdapter only supports resolution '1d'")

        end_exclusive = datetime.combine(
            end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
        )
        # countBack counts trading sessions; calendar days is an upper bound.
        payload = {
            "timeFrame": "ONE_DAY",
            "symbols": [symbol.upper()],
            "to": int(end_exclusive.timestamp()),
            "countBack": (end_date - start_date).days + 1,
        }
        try:
            response = self._client.post(VIETCAP_CHART_URL, json=payload)
            response.raise_for_status()
            return _parse(response.json(), symbol.upper(), start_date, end_date)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            logger.error("Vietcap fetch failed for %s: %s", symbol, e)
            return []


def _parse(
    body: list, symbol: str, start_date: date, end_date: date
) -> List[OHLCVCreate]:
    """Turn Vietcap's column arrays (t/o/h/l/c/v) into OHLCVCreate rows."""
    if not body:
        logger.warning("Vietcap returned no data for %s", symbol)
        return []
    series = body[0]
    candles: List[OHLCVCreate] = []
    for t, o, h, low, c, v in zip(
        series["t"], series["o"], series["h"], series["l"], series["c"], series["v"]
    ):
        # Daily bars are stamped at 00:00 UTC of the trading day.
        ts = datetime.fromtimestamp(int(t), tz=timezone.utc)
        if not start_date <= ts.date() <= end_date:
            continue
        candles.append(
            OHLCVCreate(
                timestamp=ts,
                ticker_id=symbol,
                resolution="1d",
                open=o / PRICE_DIVISOR,
                high=h / PRICE_DIVISOR,
                low=low / PRICE_DIVISOR,
                close=c / PRICE_DIVISOR,
                volume=float(v),
            )
        )
    logger.info("Parsed %d Vietcap candles for %s", len(candles), symbol)
    return candles
