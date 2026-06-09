"""
Payload Mappers — Chuẩn hóa dữ liệu từ nguồn (Binance, Vnstock) sang schema chung.

Mỗi hàm ``map_*`` chuyển đổi payload nguồn thành dict khớp cột của
``market.ohlcv_raw`` và ``market.ohlcv``.

Quy ước:
- Mọi timestamp (``ts``) lưu dạng ``datetime`` UTC (timezone-aware).
- ``source`` là enum literal: ``'binance'`` | ``'vnstock'``.
- ``timeframe`` là enum literal khớp ``market.timeframe``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Timeframe normalization                                                ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# Enum values theo init.sql: '1m','5m','15m','1h','4h','1d','1w'
_VALID_TIMEFRAMES: frozenset[str] = frozenset(
    {"1m", "5m", "15m", "1h", "4h", "1d", "1w"}
)

# Map các biến thể phổ biến → canonical
_TIMEFRAME_ALIASES: dict[str, str] = {
    "1D": "1d",
    "1W": "1w",
    "1H": "1h",
    "4H": "4h",
    "1M": "1m",
    "5M": "5m",
    "15M": "15m",
}


def normalize_timeframe(raw_interval: str) -> Optional[str]:
    """Chuẩn hóa interval string → ``market.timeframe`` enum value.

    Args:
        raw_interval: Interval gốc từ nguồn (VD: ``'1D'``, ``'1m'``, ``'4h'``).

    Returns:
        Enum value chuẩn (lowercase) hoặc ``None`` nếu không khớp.
    """
    cleaned = raw_interval.strip()

    # Đã chuẩn rồi?
    if cleaned in _VALID_TIMEFRAMES:
        return cleaned

    # Thử alias
    canonical = _TIMEFRAME_ALIASES.get(cleaned)
    if canonical is not None:
        return canonical

    # Thử lowercase
    lower = cleaned.lower()
    if lower in _VALID_TIMEFRAMES:
        return lower

    logger.warning(
        "Interval '%s' không khớp market.timeframe enum — bỏ qua",
        raw_interval,
    )
    return None


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Crypto — Tách base/quote từ symbol string                              ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

_KNOWN_QUOTE_ASSETS: tuple[str, ...] = ("USDT", "BUSD", "USDC", "BTC", "ETH", "BNB")


def split_crypto_pair(symbol: str) -> tuple[Optional[str], Optional[str]]:
    """Heuristic tách ``base_asset`` / ``quote_asset`` từ Binance symbol.

    VD: ``BTCUSDT`` → ``('BTC', 'USDT')``.
    Fallback: ``(None, None)`` nếu không nhận diện được.
    """
    upper = symbol.upper()
    for quote in _KNOWN_QUOTE_ASSETS:
        if upper.endswith(quote) and len(upper) > len(quote):
            base = upper[: -len(quote)]
            return base, quote
    return None, None


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Binance kline mappers                                                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def _safe_decimal(value: Any) -> Decimal:
    """Chuyển giá trị sang Decimal, raise nếu thất bại."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Không thể chuyển '{value}' sang Decimal") from exc


def map_binance_kline(
    symbol_id: int,
    timeframe: str,
    kline: list[Any],
) -> dict[str, Any]:
    """Map 1 kline array (12 phần tử) từ Binance REST API sang dict chuẩn.

    Binance kline format: [open_time, open, high, low, close, volume,
    close_time, quote_vol, trades, taker_buy_base, taker_buy_quote, ignore].

    Args:
        symbol_id: FK ``market.symbol.id``.
        timeframe: Đã normalize (VD: ``'1h'``).
        kline: List 12 phần tử từ ``/api/v3/klines``.

    Returns:
        Dict khớp cột ``market.ohlcv_raw`` (bao gồm ``raw_payload``).
    """
    # open_time (epoch ms) → datetime UTC
    ts = datetime.fromtimestamp(int(kline[0]) / 1000, tz=timezone.utc)

    return {
        "symbol_id": symbol_id,
        "timeframe": timeframe,
        "ts": ts,
        "open": _safe_decimal(kline[1]),
        "high": _safe_decimal(kline[2]),
        "low": _safe_decimal(kline[3]),
        "close": _safe_decimal(kline[4]),
        "volume": _safe_decimal(kline[5]),
        "source": "binance",
        "raw_payload": json.dumps(kline, default=str),
        # Extra cho market.ohlcv
        "trade_count": int(kline[8]) if kline[8] is not None else None,
    }


def map_binance_klines_batch(
    symbol_id: int,
    timeframe: str,
    data: list[list[Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map batch klines từ Binance → ``(ohlcv_raw_rows, ohlcv_rows)``.

    ``ohlcv_rows`` đã qua validation: loại bản ghi ``high < low`` hoặc giá âm.
    ``ohlcv_raw_rows`` giữ nguyên tất cả (dữ liệu thô).

    Args:
        symbol_id: FK ``market.symbol.id``.
        timeframe: Đã normalize.
        data: List of kline arrays.

    Returns:
        Tuple ``(raw_rows, clean_rows)``.
    """
    raw_rows: list[dict[str, Any]] = []
    clean_rows: list[dict[str, Any]] = []

    for kline in data:
        try:
            mapped = map_binance_kline(symbol_id, timeframe, kline)
        except (ValueError, IndexError) as exc:
            logger.warning("Bỏ qua kline lỗi: %s — %s", kline[:3], exc)
            continue

        # Raw row — luôn giữ
        raw_rows.append(
            {
                "symbol_id": mapped["symbol_id"],
                "timeframe": mapped["timeframe"],
                "ts": mapped["ts"],
                "open": mapped["open"],
                "high": mapped["high"],
                "low": mapped["low"],
                "close": mapped["close"],
                "volume": mapped["volume"],
                "source": mapped["source"],
                "raw_payload": mapped["raw_payload"],
            }
        )

        # Clean row — chỉ giữ nếu hợp lệ
        h = mapped["high"]
        l_ = mapped["low"]
        o = mapped["open"]
        c = mapped["close"]
        v = mapped["volume"]
        if h >= l_ and o >= 0 and c >= 0 and v >= 0:
            clean_rows.append(
                {
                    "symbol_id": mapped["symbol_id"],
                    "timeframe": mapped["timeframe"],
                    "ts": mapped["ts"],
                    "open": mapped["open"],
                    "high": mapped["high"],
                    "low": mapped["low"],
                    "close": mapped["close"],
                    "volume": mapped["volume"],
                    "trade_count": mapped.get("trade_count"),
                }
            )

    return raw_rows, clean_rows


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Vnstock OHLCV mappers                                                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def _to_utc_datetime(value: Any) -> Optional[datetime]:
    """Chuyển timestamp/date → datetime UTC (timezone-aware).

    Quy ước: nếu input là date/naive datetime, gán 00:00:00 UTC.
    """
    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        dt = value.to_pydatetime()
    elif isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = pd.to_datetime(value).to_pydatetime()
    else:
        dt = pd.to_datetime(value).to_pydatetime()

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        # Chuyển về UTC
        dt = dt.astimezone(timezone.utc)

    return dt


def _clean_json_value(value: Any) -> Any:
    """Xử lý giá trị cho JSON serialization (NaN, Timestamp, numpy)."""
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, datetime):
        return value.isoformat()

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return value


def _safe_decimal_or_none(value: Any) -> Optional[Decimal]:
    """Chuyển giá trị sang Decimal, trả None nếu NaN/None."""
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def map_vnstock_row(
    symbol_id: int,
    timeframe: str,
    row: pd.Series,
) -> Optional[dict[str, Any]]:
    """Map 1 row từ vnstock DataFrame (đã normalize) sang dict chuẩn.

    Args:
        symbol_id: FK ``market.symbol.id``.
        timeframe: Đã normalize (VD: ``'1d'``).
        row: pandas Series với keys ``time, open, high, low, close, volume``.

    Returns:
        Dict chuẩn hoặc ``None`` nếu timestamp không hợp lệ.
    """
    ts = _to_utc_datetime(row.get("time"))
    if ts is None:
        return None

    raw_data = {str(key): _clean_json_value(val) for key, val in row.to_dict().items()}

    return {
        "symbol_id": symbol_id,
        "timeframe": timeframe,
        "ts": ts,
        "open": _safe_decimal_or_none(row.get("open")),
        "high": _safe_decimal_or_none(row.get("high")),
        "low": _safe_decimal_or_none(row.get("low")),
        "close": _safe_decimal_or_none(row.get("close")),
        "volume": _safe_decimal_or_none(row.get("volume")),
        "source": "vnstock",
        "raw_payload": json.dumps(raw_data, default=str),
    }


def map_vnstock_df_batch(
    symbol_id: int,
    timeframe: str,
    df: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map toàn bộ DataFrame vnstock → ``(ohlcv_raw_rows, ohlcv_rows)``.

    ``ohlcv_rows`` đã qua validation: loại bản ghi có giá ``None``,
    ``high < low``, hoặc giá/volume âm.

    Args:
        symbol_id: FK ``market.symbol.id``.
        timeframe: Đã normalize.
        df: DataFrame đã qua ``normalize_dataframe()``.

    Returns:
        Tuple ``(raw_rows, clean_rows)``.
    """
    raw_rows: list[dict[str, Any]] = []
    clean_rows: list[dict[str, Any]] = []

    if df is None or df.empty:
        return raw_rows, clean_rows

    for _, row in df.iterrows():
        mapped = map_vnstock_row(symbol_id, timeframe, row)
        if mapped is None:
            continue

        # Raw — luôn giữ (kể cả khi giá None)
        raw_rows.append(
            {
                "symbol_id": mapped["symbol_id"],
                "timeframe": mapped["timeframe"],
                "ts": mapped["ts"],
                "open": mapped["open"] or Decimal("0"),
                "high": mapped["high"] or Decimal("0"),
                "low": mapped["low"] or Decimal("0"),
                "close": mapped["close"] or Decimal("0"),
                "volume": mapped["volume"] or Decimal("0"),
                "source": mapped["source"],
                "raw_payload": mapped["raw_payload"],
            }
        )

        # Clean — chỉ giữ nếu tất cả giá trị hợp lệ
        o = mapped["open"]
        h = mapped["high"]
        l_ = mapped["low"]
        c = mapped["close"]
        v = mapped["volume"]

        if o is None or h is None or l_ is None or c is None or v is None:
            continue
        if h < l_ or o < 0 or c < 0 or v < 0:
            continue

        clean_rows.append(
            {
                "symbol_id": mapped["symbol_id"],
                "timeframe": mapped["timeframe"],
                "ts": mapped["ts"],
                "open": o,
                "high": h,
                "low": l_,
                "close": c,
                "volume": v,
            }
        )

    return raw_rows, clean_rows
