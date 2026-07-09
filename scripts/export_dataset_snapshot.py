import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from scripts.snapshot_checksum import compute_manifest_fingerprint, sha256_file
from shared.db.session import sync_engine
from shared.utils.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
sync_engine.echo = False


TABLE_EXPORTS: dict[str, str] = {
    "market_exchange": """
        SELECT
            id,
            code,
            name,
            asset_class::text AS asset_class,
            timezone,
            created_at
        FROM market.exchange
        ORDER BY id
    """,
    "market_symbol": """
        SELECT
            id,
            exchange_id,
            ticker,
            asset_class::text AS asset_class,
            source::text AS source,
            base_asset,
            quote_asset,
            company_name,
            status::text AS status,
            listed_date,
            metadata::text AS metadata,
            created_at,
            updated_at
        FROM market.symbol
        ORDER BY id
    """,
    "market_ohlcv": """
        SELECT
            symbol_id,
            timeframe::text AS timeframe,
            ts,
            open,
            high,
            low,
            close,
            volume,
            vwap,
            trade_count,
            updated_at
        FROM market.ohlcv
        ORDER BY symbol_id, timeframe, ts
    """,
    "market_ohlcv_raw": """
        SELECT
            id,
            symbol_id,
            timeframe::text AS timeframe,
            ts,
            open,
            high,
            low,
            close,
            volume,
            source::text AS source,
            ingested_at,
            raw_payload::text AS raw_payload
        FROM market.ohlcv_raw
        ORDER BY symbol_id, timeframe, ts, source, id
    """,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export market dataset tables to a CSV.gz snapshot."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/snapshots"),
        help="Directory that will contain snapshot folders.",
    )
    parser.add_argument(
        "--snapshot-name",
        type=str,
        default=None,
        help="Optional fixed snapshot folder name.",
    )
    return parser.parse_args()


def _snapshot_name() -> str:
    exported_at = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"ohlcv_full_{exported_at}"


def _query_list(sql: str) -> list[dict[str, Any]]:
    with sync_engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return [dict(row) for row in rows]


def _query_one(sql: str) -> dict[str, Any]:
    with sync_engine.connect() as conn:
        row = conn.execute(text(sql)).mappings().first()
    return dict(row) if row is not None else {}


def _write_table(table_name: str, sql: str, snapshot_dir: Path) -> int:
    output_path = snapshot_dir / f"{table_name}.csv.gz"
    logger.info("Exporting %s -> %s", table_name, output_path)

    with sync_engine.connect() as conn:
        df = pd.read_sql_query(text(sql), conn)

    df.to_csv(output_path, index=False, compression="gzip")
    logger.info("Exported %s rows from %s", len(df), table_name)
    return int(len(df))


def _build_checksums(snapshot_dir: Path, manifest: dict[str, Any]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for file_info in manifest["files"].values():
        filename = file_info["path"]
        checksums[filename] = f"sha256:{sha256_file(snapshot_dir / filename)}"
    return checksums


def _build_manifest(snapshot_name: str, table_counts: dict[str, int]) -> dict[str, Any]:
    exported_at = datetime.now(timezone.utc).isoformat()
    ohlcv_summary = _query_one(
        """
        SELECT
            COUNT(*) AS row_count,
            MIN(ts) AS min_ts,
            MAX(ts) AS max_ts
        FROM market.ohlcv
        """
    )
    symbol_counts = _query_list(
        """
        SELECT asset_class::text AS asset_class, COUNT(*) AS symbol_count
        FROM market.symbol
        GROUP BY asset_class
        ORDER BY asset_class
        """
    )
    timeframes = _query_list(
        """
        SELECT DISTINCT timeframe::text AS timeframe
        FROM market.ohlcv
        ORDER BY timeframe
        """
    )
    rows_by_asset_timeframe = _query_list(
        """
        SELECT
            s.asset_class::text AS asset_class,
            o.timeframe::text AS timeframe,
            COUNT(*) AS row_count,
            MIN(o.ts) AS min_ts,
            MAX(o.ts) AS max_ts
        FROM market.ohlcv o
        JOIN market.symbol s ON s.id = o.symbol_id
        GROUP BY s.asset_class, o.timeframe
        ORDER BY s.asset_class, o.timeframe
        """
    )

    return {
        "snapshot_name": snapshot_name,
        "exported_at": exported_at,
        "source": {
            "database": "stock_crypto_db",
            "schemas": ["market"],
            "tables": [
                "market.exchange",
                "market.symbol",
                "market.ohlcv",
                "market.ohlcv_raw",
            ],
        },
        "files": {
            table_name: {
                "path": f"{table_name}.csv.gz",
                "rows": row_count,
            }
            for table_name, row_count in table_counts.items()
        },
        "summary": {
            "ohlcv": ohlcv_summary,
            "symbols_by_asset_class": symbol_counts,
            "timeframes": [item["timeframe"] for item in timeframes],
            "rows_by_asset_timeframe": rows_by_asset_timeframe,
        },
    }


def main() -> None:
    args = parse_args()
    snapshot_name = args.snapshot_name or _snapshot_name()
    snapshot_dir = args.output_dir / snapshot_name

    if snapshot_dir.exists() and any(snapshot_dir.iterdir()):
        raise FileExistsError(
            f"Snapshot directory already exists and is not empty: {snapshot_dir}"
        )

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Writing dataset snapshot to %s", snapshot_dir)

    table_counts: dict[str, int] = {}
    for table_name, sql in TABLE_EXPORTS.items():
        table_counts[table_name] = _write_table(table_name, sql, snapshot_dir)

    manifest = _build_manifest(snapshot_name, table_counts)
    manifest["checksums"] = _build_checksums(snapshot_dir, manifest)
    manifest["snapshot_fingerprint"] = compute_manifest_fingerprint(manifest)

    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Wrote manifest -> %s", manifest_path)
    logger.info("[OK] Snapshot fingerprint: %s", manifest["snapshot_fingerprint"])
    logger.info("Snapshot export complete: %s", snapshot_dir)


if __name__ == "__main__":
    main()
