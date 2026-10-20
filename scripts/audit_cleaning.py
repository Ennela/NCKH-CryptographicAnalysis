"""Replay the cleaning pipeline over every symbol's raw history (no writes to bars).

Records one ``cleaning_pipeline`` report per (symbol, timeframe) in
``ops.data_quality_check`` with ``detail.mode = "audit"``; ``market.ohlcv`` is
not modified. See ``services.ingestion.app.pipeline.audit_cleaning``.

Usage (inside the ingestion container, from /app):
    python -m scripts.audit_cleaning
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from services.ingestion.app.pipeline import audit_cleaning
from shared.db.session import SessionLocal
from shared.utils.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

PAIRS_QUERY = text(
    "SELECT DISTINCT r.symbol_id, s.ticker, r.timeframe::text AS timeframe "
    "FROM market.ohlcv_raw r JOIN market.symbol s ON s.id = r.symbol_id "
    "WHERE s.status = 'active' ORDER BY s.ticker, timeframe"
)


def main() -> None:
    """Audit every active (symbol, timeframe) that has raw bars."""
    db = SessionLocal()
    try:
        pairs = db.execute(PAIRS_QUERY).fetchall()
        for pair in pairs:
            try:
                detail = audit_cleaning(db, int(pair.symbol_id), pair.timeframe)
                db.commit()
                print(f"{pair.ticker:<9} {pair.timeframe}: {detail}")
            except Exception as exc:  # noqa: BLE001 — report and continue
                db.rollback()
                logger.error(
                    "Audit failed for %s %s: %s", pair.ticker, pair.timeframe, exc
                )
    finally:
        db.close()


if __name__ == "__main__":
    main()
