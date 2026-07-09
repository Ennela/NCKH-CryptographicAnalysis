import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from scripts.snapshot_checksum import compute_manifest_fingerprint
from services.training.dataset_contract import load_dataset_contract, normalize_ticker
from shared.db.session import sync_engine
from shared.utils.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
sync_engine.echo = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate local PostgreSQL data against the shared dataset contract."
    )
    parser.add_argument(
        "--dataset-config",
        type=str,
        default="configs/group_dataset.json",
        help="Dataset contract JSON file.",
    )
    return parser.parse_args()


def _query_df(sql: str) -> pd.DataFrame:
    with sync_engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn)


def _expected_contract_rows(contract: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for asset_class, asset_config in contract["assets"].items():
        for symbol in asset_config["symbols"]:
            for timeframe, timeframe_config in asset_config["timeframes"].items():
                rows.append(
                    {
                        "asset_class": asset_class,
                        "ticker": normalize_ticker(symbol),
                        "timeframe": timeframe,
                        "start_ts": pd.Timestamp(timeframe_config["start_ts"]),
                        "end_ts": pd.Timestamp(timeframe_config["end_ts"]),
                        "expected_rows": timeframe_config.get("expected_rows_per_symbol"),
                        "expected_min": timeframe_config.get(
                            "expected_rows_per_symbol_min"
                        ),
                        "expected_max": timeframe_config.get(
                            "expected_rows_per_symbol_max"
                        ),
                    }
                )
    return rows


def _validate_count(expected: dict[str, Any], actual_count: int) -> list[str]:
    errors: list[str] = []
    expected_rows = expected.get("expected_rows")
    expected_min = expected.get("expected_min")
    expected_max = expected.get("expected_max")

    if expected_rows is not None and actual_count != int(expected_rows):
        errors.append(f"rows={actual_count}, expected={expected_rows}")
    if expected_min is not None and actual_count < int(expected_min):
        errors.append(f"rows={actual_count}, expected_min={expected_min}")
    if expected_max is not None and actual_count > int(expected_max):
        errors.append(f"rows={actual_count}, expected_max={expected_max}")
    return errors


def _check_snapshot_fingerprint(contract: dict[str, Any]) -> None:
    expected = contract.get("snapshot_fingerprint")
    if expected is None:
        logger.info("Fingerprint not locked yet (null); skipping fingerprint check.")
        return

    snapshot_name = contract["source_snapshot_name"]
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = repo_root / "data" / "snapshots" / snapshot_name / "manifest.json"
    if not manifest_path.exists():
        logger.warning(
            "Local snapshot manifest not found; cannot verify fingerprint: %s",
            manifest_path,
        )
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = compute_manifest_fingerprint(manifest)
    if actual == expected:
        logger.info("[OK] Fingerprint matches contract.")
    else:
        logger.warning(
            "Snapshot fingerprint mismatch: expected %s, got %s",
            expected,
            actual,
        )


def main() -> None:
    args = parse_args()
    contract = load_dataset_contract(args.dataset_config)
    if contract is None:
        raise ValueError("Dataset contract is required for validation.")

    logger.info(
        "Checking DB against %s from snapshot %s",
        contract["dataset_version"],
        contract["source_snapshot_name"],
    )

    actual = _query_df(
        """
        SELECT
            s.asset_class::text AS asset_class,
            s.ticker,
            o.timeframe::text AS timeframe,
            COUNT(*) AS row_count,
            MIN(o.ts) AS min_ts,
            MAX(o.ts) AS max_ts
        FROM market.ohlcv o
        JOIN market.symbol s ON s.id = o.symbol_id
        GROUP BY s.asset_class, s.ticker, o.timeframe
        ORDER BY s.asset_class, s.ticker, o.timeframe
        """
    )

    actual["ticker"] = actual["ticker"].map(normalize_ticker)
    actual["min_ts"] = pd.to_datetime(actual["min_ts"])
    actual["max_ts"] = pd.to_datetime(actual["max_ts"])

    actual_keys = {
        (row.ticker, row.timeframe): row
        for row in actual.itertuples(index=False)
    }
    expected_rows = _expected_contract_rows(contract)
    expected_keys = {(row["ticker"], row["timeframe"]) for row in expected_rows}

    errors: list[str] = []
    for expected in expected_rows:
        key = (expected["ticker"], expected["timeframe"])
        actual_row = actual_keys.get(key)
        if actual_row is None:
            errors.append(f"Missing {expected['ticker']} {expected['timeframe']}")
            continue

        errors.extend(
            f"{expected['ticker']} {expected['timeframe']}: {message}"
            for message in _validate_count(expected, int(actual_row.row_count))
        )
        if actual_row.min_ts != expected["start_ts"]:
            errors.append(
                f"{expected['ticker']} {expected['timeframe']}: "
                f"min_ts={actual_row.min_ts}, expected={expected['start_ts']}"
            )
        if actual_row.max_ts != expected["end_ts"]:
            errors.append(
                f"{expected['ticker']} {expected['timeframe']}: "
                f"max_ts={actual_row.max_ts}, expected={expected['end_ts']}"
            )

    extra_keys = set(actual_keys) - expected_keys
    for ticker, timeframe in sorted(extra_keys):
        errors.append(f"Extra data found: {ticker} {timeframe}")

    if errors:
        logger.error("Dataset check failed with %d issue(s):", len(errors))
        for error in errors:
            logger.error("  - %s", error)
        raise SystemExit(1)

    _check_snapshot_fingerprint(contract)
    logger.info("Dataset check passed: local DB matches %s", contract["dataset_version"])


if __name__ == "__main__":
    main()
