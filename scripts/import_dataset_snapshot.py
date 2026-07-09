import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from scripts.snapshot_checksum import sha256_file
from shared.db.session import SessionLocal, sync_engine
from shared.utils.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
sync_engine.echo = False


REQUIRED_FILES: tuple[str, ...] = (
    "market_exchange.csv.gz",
    "market_symbol.csv.gz",
    "market_ohlcv_raw.csv.gz",
    "market_ohlcv.csv.gz",
    "manifest.json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a CSV.gz market dataset snapshot into PostgreSQL."
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        required=True,
        help="Snapshot folder created by export_dataset_snapshot.py.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Truncate market dataset tables before import. Use only on dev/local DB.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=5000,
        help="Rows per database batch for large OHLCV tables.",
    )
    return parser.parse_args()


def _validate_snapshot(snapshot_dir: Path) -> None:
    missing = [name for name in REQUIRED_FILES if not (snapshot_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Snapshot directory {snapshot_dir} is missing: {', '.join(missing)}"
        )


def _verify_checksums(snapshot_dir: Path) -> None:
    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checksums = manifest.get("checksums")
    if not checksums:
        logger.warning("Manifest has no checksums; skipping integrity check.")
        return

    for filename, expected in checksums.items():
        if not isinstance(expected, str) or not expected.startswith("sha256:"):
            raise ValueError(f"Invalid checksum entry for {filename}: {expected}")

        path = snapshot_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Checksum file is missing: {path}")

        actual = f"sha256:{sha256_file(path)}"
        if actual != expected:
            raise ValueError(
                f"Checksum mismatch for {filename}: expected {expected}, got {actual}"
            )
        logger.info("[OK] Checksum verified: %s", filename)


def _read_csv(snapshot_dir: Path, filename: str) -> pd.DataFrame:
    path = snapshot_dir / filename
    logger.info("Reading %s", path)
    return pd.read_csv(path, compression="gzip", keep_default_na=True)


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    return value


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: _clean_value(value) for key, value in record.items()}


def _clean_records(df: pd.DataFrame) -> Iterable[dict[str, Any]]:
    for record in df.to_dict(orient="records"):
        yield _clean_record(record)


def _truncate_market_dataset(db: Session) -> None:
    logger.warning(
        "Replacing dataset: truncating market.ohlcv_raw, market.ohlcv, "
        "market.symbol, and market.exchange with CASCADE."
    )
    db.execute(
        text(
            """
            TRUNCATE TABLE
                market.ohlcv_raw,
                market.ohlcv,
                market.symbol,
                market.exchange
            RESTART IDENTITY CASCADE
            """
        )
    )
    db.commit()


def _import_exchange(db: Session, snapshot_dir: Path) -> dict[int, int]:
    df = _read_csv(snapshot_dir, "market_exchange.csv.gz")
    sql = text(
        """
        INSERT INTO market.exchange (code, name, asset_class, timezone, created_at)
        VALUES (
            :code,
            :name,
            CAST(:asset_class AS market.asset_class),
            :timezone,
            COALESCE(CAST(:created_at AS TIMESTAMPTZ), NOW())
        )
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            asset_class = EXCLUDED.asset_class,
            timezone = EXCLUDED.timezone
        RETURNING id
        """
    )

    id_map: dict[int, int] = {}
    for record in _clean_records(df):
        old_id = int(record["id"])
        new_id = db.execute(sql, record).scalar_one()
        id_map[old_id] = int(new_id)

    db.commit()
    logger.info("Imported %d exchanges", len(id_map))
    return id_map


def _import_symbol(
    db: Session,
    snapshot_dir: Path,
    exchange_id_map: dict[int, int],
) -> dict[int, int]:
    df = _read_csv(snapshot_dir, "market_symbol.csv.gz")
    sql = text(
        """
        INSERT INTO market.symbol (
            exchange_id,
            ticker,
            asset_class,
            source,
            base_asset,
            quote_asset,
            company_name,
            status,
            listed_date,
            metadata,
            created_at,
            updated_at
        )
        VALUES (
            :exchange_id,
            :ticker,
            CAST(:asset_class AS market.asset_class),
            CAST(:source AS market.data_source),
            :base_asset,
            :quote_asset,
            :company_name,
            CAST(:status AS market.symbol_status),
            CAST(:listed_date AS DATE),
            COALESCE(CAST(:metadata AS JSONB), '{}'::jsonb),
            COALESCE(CAST(:created_at AS TIMESTAMPTZ), NOW()),
            COALESCE(CAST(:updated_at AS TIMESTAMPTZ), NOW())
        )
        ON CONFLICT (exchange_id, ticker) DO UPDATE SET
            asset_class = EXCLUDED.asset_class,
            source = EXCLUDED.source,
            base_asset = EXCLUDED.base_asset,
            quote_asset = EXCLUDED.quote_asset,
            company_name = EXCLUDED.company_name,
            status = EXCLUDED.status,
            listed_date = EXCLUDED.listed_date,
            metadata = EXCLUDED.metadata,
            updated_at = EXCLUDED.updated_at
        RETURNING id
        """
    )

    id_map: dict[int, int] = {}
    for record in _clean_records(df):
        old_id = int(record["id"])
        old_exchange_id = int(record["exchange_id"])
        if old_exchange_id not in exchange_id_map:
            raise ValueError(f"Missing exchange id mapping for {old_exchange_id}")

        record["exchange_id"] = exchange_id_map[old_exchange_id]
        new_id = db.execute(sql, record).scalar_one()
        id_map[old_id] = int(new_id)

    db.commit()
    logger.info("Imported %d symbols", len(id_map))
    return id_map


def _execute_in_chunks(
    db: Session,
    sql: Any,
    records: list[dict[str, Any]],
    chunk_size: int,
) -> int:
    affected = 0
    for start in range(0, len(records), chunk_size):
        chunk = records[start : start + chunk_size]
        db.execute(sql, chunk)
        affected += len(chunk)
    db.commit()
    return affected


def _import_ohlcv_raw(
    db: Session,
    snapshot_dir: Path,
    symbol_id_map: dict[int, int],
    chunk_size: int,
) -> int:
    sql = text(
        """
        INSERT INTO market.ohlcv_raw (
            symbol_id,
            timeframe,
            ts,
            open,
            high,
            low,
            close,
            volume,
            source,
            ingested_at,
            raw_payload
        )
        VALUES (
            :symbol_id,
            CAST(:timeframe AS market.timeframe),
            CAST(:ts AS TIMESTAMPTZ),
            :open,
            :high,
            :low,
            :close,
            :volume,
            CAST(:source AS market.data_source),
            COALESCE(CAST(:ingested_at AS TIMESTAMPTZ), NOW()),
            CAST(:raw_payload AS JSONB)
        )
        ON CONFLICT (symbol_id, timeframe, ts, source) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            ingested_at = EXCLUDED.ingested_at,
            raw_payload = EXCLUDED.raw_payload
        """
    )

    total = 0
    path = snapshot_dir / "market_ohlcv_raw.csv.gz"
    for df in pd.read_csv(path, compression="gzip", chunksize=chunk_size):
        records: list[dict[str, Any]] = []
        for record in _clean_records(df):
            old_symbol_id = int(record["symbol_id"])
            if old_symbol_id not in symbol_id_map:
                raise ValueError(f"Missing symbol id mapping for {old_symbol_id}")
            record["symbol_id"] = symbol_id_map[old_symbol_id]
            records.append(record)
        total += _execute_in_chunks(db, sql, records, chunk_size)
        logger.info("Imported %d raw OHLCV rows...", total)

    logger.info("Imported %d raw OHLCV rows", total)
    return total


def _import_ohlcv(
    db: Session,
    snapshot_dir: Path,
    symbol_id_map: dict[int, int],
    chunk_size: int,
) -> int:
    sql = text(
        """
        INSERT INTO market.ohlcv (
            symbol_id,
            timeframe,
            ts,
            open,
            high,
            low,
            close,
            volume,
            vwap,
            trade_count,
            updated_at
        )
        VALUES (
            :symbol_id,
            CAST(:timeframe AS market.timeframe),
            CAST(:ts AS TIMESTAMPTZ),
            :open,
            :high,
            :low,
            :close,
            :volume,
            :vwap,
            :trade_count,
            COALESCE(CAST(:updated_at AS TIMESTAMPTZ), NOW())
        )
        ON CONFLICT (symbol_id, timeframe, ts) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            vwap = EXCLUDED.vwap,
            trade_count = EXCLUDED.trade_count,
            updated_at = EXCLUDED.updated_at
        """
    )

    total = 0
    path = snapshot_dir / "market_ohlcv.csv.gz"
    for df in pd.read_csv(path, compression="gzip", chunksize=chunk_size):
        records: list[dict[str, Any]] = []
        for record in _clean_records(df):
            old_symbol_id = int(record["symbol_id"])
            if old_symbol_id not in symbol_id_map:
                raise ValueError(f"Missing symbol id mapping for {old_symbol_id}")
            record["symbol_id"] = symbol_id_map[old_symbol_id]
            records.append(record)
        total += _execute_in_chunks(db, sql, records, chunk_size)
        logger.info("Imported %d clean OHLCV rows...", total)

    logger.info("Imported %d clean OHLCV rows", total)
    return total


def main() -> None:
    args = parse_args()
    snapshot_dir = args.snapshot_dir
    _validate_snapshot(snapshot_dir)
    _verify_checksums(snapshot_dir)

    db = SessionLocal()
    try:
        if args.replace:
            _truncate_market_dataset(db)

        exchange_id_map = _import_exchange(db, snapshot_dir)
        symbol_id_map = _import_symbol(db, snapshot_dir, exchange_id_map)
        raw_count = _import_ohlcv_raw(db, snapshot_dir, symbol_id_map, args.chunk_size)
        clean_count = _import_ohlcv(db, snapshot_dir, symbol_id_map, args.chunk_size)

        logger.info(
            "Snapshot import complete: exchanges=%d symbols=%d raw_rows=%d clean_rows=%d",
            len(exchange_id_map),
            len(symbol_id_map),
            raw_count,
            clean_count,
        )
    except Exception:
        db.rollback()
        logger.exception("Snapshot import failed")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
