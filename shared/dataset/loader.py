"""Load a complete chronological series from the locked dataset snapshot."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DatasetContract = dict[str, Any]
PathLike = str | Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = REPO_ROOT / "configs" / "group_dataset.json"
DEFAULT_SNAPSHOT_ROOT = REPO_ROOT / "data" / "snapshots"
EXPECTED_DATASET_VERSION = "group_dataset_v1"

SNAPSHOT_COLUMNS: tuple[str, ...] = (
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
NUMERIC_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")
SPLIT_NAMES: tuple[str, ...] = ("train", "val", "test")


def _resolve_repo_path(path: PathLike) -> Path:
    """Resolve a configurable path from the caller's CWD or repository root."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate

    cwd_path = Path.cwd() / candidate
    if cwd_path.exists():
        return cwd_path
    return REPO_ROOT / candidate


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object and fail with a clear error for an invalid document."""
    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def _load_contract(contract_path: PathLike) -> DatasetContract:
    """Load and validate the locked group dataset contract."""
    resolved_path = _resolve_repo_path(contract_path)
    contract = _read_json(resolved_path)
    dataset_version = contract.get("dataset_version")
    if dataset_version != EXPECTED_DATASET_VERSION:
        raise ValueError(
            f"Expected dataset_version={EXPECTED_DATASET_VERSION!r}, "
            f"got {dataset_version!r}."
        )
    return contract


def _normalize_ticker(ticker: str) -> str:
    """Normalize stock and crypto ticker spellings for contract lookup."""
    normalized = ticker.strip().replace("/", "").upper()
    if not normalized:
        raise ValueError("ticker must not be empty.")
    return normalized


def _find_timeframe_config(
    contract: DatasetContract,
    ticker: str,
    timeframe: str,
) -> dict[str, Any]:
    """Return the contract bounds for one allowed ticker/timeframe pair."""
    assets = contract.get("assets")
    if not isinstance(assets, dict):
        raise ValueError("Dataset contract is missing an 'assets' object.")

    for asset_config in assets.values():
        if not isinstance(asset_config, dict):
            raise ValueError("Each dataset asset configuration must be an object.")
        symbols = asset_config.get("symbols", [])
        normalized_symbols = {_normalize_ticker(str(symbol)) for symbol in symbols}
        if ticker not in normalized_symbols:
            continue

        timeframes = asset_config.get("timeframes", {})
        if not isinstance(timeframes, dict):
            raise ValueError("Dataset asset 'timeframes' must be an object.")
        if timeframe not in timeframes:
            raise ValueError(
                f"Timeframe {timeframe!r} is not allowed for ticker {ticker!r}."
            )
        timeframe_config = timeframes[timeframe]
        if not isinstance(timeframe_config, dict):
            raise ValueError("Each dataset timeframe configuration must be an object.")
        return dict(timeframe_config)

    raise ValueError(
        f"Ticker {ticker!r} is not part of dataset {contract['dataset_version']!r}."
    )


def _compute_manifest_fingerprint(manifest: dict[str, Any]) -> str:
    """Compute the canonical fingerprint used by the snapshot exporter."""
    fingerprint_payload = {
        key: value for key, value in manifest.items() if key != "snapshot_fingerprint"
    }
    canonical_json = json.dumps(
        fingerprint_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    """Return the SHA256 digest of a snapshot file without loading it at once."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_snapshot_file(
    snapshot_dir: Path,
    manifest: dict[str, Any],
    table_name: str,
) -> Path:
    """Resolve one manifest file and verify its locked checksum."""
    try:
        filename = str(manifest["files"][table_name]["path"])
        expected_checksum = str(manifest["checksums"][filename])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Manifest is missing metadata for {table_name!r}.") from exc

    file_path = snapshot_dir / filename
    if not file_path.is_file():
        raise FileNotFoundError(f"Snapshot file not found: {file_path}")
    if not expected_checksum.startswith("sha256:"):
        raise ValueError(f"Invalid checksum for snapshot file {filename!r}.")

    actual_checksum = _sha256_file(file_path)
    if actual_checksum != expected_checksum.removeprefix("sha256:"):
        raise ValueError(f"Checksum mismatch for snapshot file {filename!r}.")
    return file_path


def _resolve_snapshot_files(
    contract: DatasetContract,
    snapshot_root: PathLike,
) -> tuple[Path, Path]:
    """Validate the locked manifest and return symbol/OHLCV CSV paths."""
    snapshot_name = str(contract.get("source_snapshot_name", ""))
    if not snapshot_name:
        raise ValueError("Dataset contract is missing 'source_snapshot_name'.")

    snapshot_dir = _resolve_repo_path(snapshot_root) / snapshot_name
    manifest = _read_json(snapshot_dir / "manifest.json")
    expected_fingerprint = str(contract.get("snapshot_fingerprint", ""))
    actual_fingerprint = _compute_manifest_fingerprint(manifest)
    recorded_fingerprint = str(manifest.get("snapshot_fingerprint", ""))

    if manifest.get("snapshot_name") != snapshot_name:
        raise ValueError("Snapshot manifest name does not match the dataset contract.")
    if not expected_fingerprint or actual_fingerprint != expected_fingerprint:
        raise ValueError("Snapshot fingerprint does not match the dataset contract.")
    if recorded_fingerprint != expected_fingerprint:
        raise ValueError("Recorded snapshot fingerprint is inconsistent.")

    symbol_path = _verify_snapshot_file(snapshot_dir, manifest, "market_symbol")
    ohlcv_path = _verify_snapshot_file(snapshot_dir, manifest, "market_ohlcv")
    return symbol_path, ohlcv_path


def _load_symbol_id(symbol_path: Path, ticker: str) -> int:
    """Resolve a normalized ticker to exactly one snapshot symbol ID."""
    symbols = pd.read_csv(
        symbol_path,
        compression="gzip",
        usecols=["id", "ticker"],
    )
    normalized_tickers = symbols["ticker"].astype(str).map(_normalize_ticker)
    matching_ids = symbols.loc[normalized_tickers.eq(ticker), "id"]
    if len(matching_ids) != 1:
        raise ValueError(
            f"Expected one symbol row for ticker {ticker!r}, found {len(matching_ids)}."
        )
    return int(matching_ids.iloc[0])


def _load_ohlcv_rows(
    ohlcv_path: Path,
    symbol_id: int,
    timeframe: str,
    timeframe_config: dict[str, Any],
) -> pd.DataFrame:
    """Read, bound, type, and sort the complete OHLCV series from the snapshot."""
    columns = ["symbol_id", "timeframe", *SNAPSHOT_COLUMNS]
    snapshot = pd.read_csv(ohlcv_path, compression="gzip", usecols=columns)
    symbol_ids = pd.to_numeric(snapshot["symbol_id"], errors="raise")
    matching_rows = symbol_ids.eq(symbol_id) & snapshot["timeframe"].eq(timeframe)
    series = snapshot.loc[matching_rows, list(SNAPSHOT_COLUMNS)].copy()

    series["ts"] = pd.to_datetime(series["ts"], utc=True, errors="raise")
    for column in NUMERIC_COLUMNS:
        series[column] = pd.to_numeric(series[column], errors="raise").astype(float)

    start_ts = pd.to_datetime(timeframe_config["start_ts"], utc=True)
    end_ts = pd.to_datetime(timeframe_config["end_ts"], utc=True)
    series = series.loc[series["ts"].between(start_ts, end_ts, inclusive="both")]
    series = series.sort_values("ts", kind="mergesort").reset_index(drop=True)

    if series.empty:
        raise ValueError(f"No OHLCV rows found for symbol_id={symbol_id}, {timeframe}.")
    if series["ts"].duplicated().any():
        raise ValueError(
            "Snapshot contains duplicate timestamps for the requested series."
        )
    if series["ts"].iloc[0] != start_ts or series["ts"].iloc[-1] != end_ts:
        raise ValueError(
            "Snapshot does not cover the full timestamp bounds in the contract."
        )
    if series[list(NUMERIC_COLUMNS)].isna().any(axis=None):
        raise ValueError("Snapshot contains missing OHLCV values.")
    return series


def _add_split_and_target(
    df: pd.DataFrame,
    contract: DatasetContract,
) -> pd.DataFrame:
    """Add chronological splits and targets without crossing split boundaries."""
    split_config = contract["split"]
    train_ratio = float(split_config["train_ratio"])
    validation_ratio = float(split_config["validation_ratio"])
    test_ratio = float(split_config["test_ratio"])
    if min(train_ratio, validation_ratio, test_ratio) <= 0:
        raise ValueError("All dataset split ratios must be positive.")
    if abs(train_ratio + validation_ratio + test_ratio - 1.0) > 1e-9:
        raise ValueError("Dataset split ratios must sum to 1.0.")

    train_end = int(len(df) * train_ratio)
    validation_end = int(len(df) * (train_ratio + validation_ratio))
    if not 0 < train_end < validation_end < len(df):
        raise ValueError("Dataset is too small to create train/val/test splits.")

    result = df.copy()
    result["split"] = "test"
    result.loc[result.index < train_end, "split"] = "train"
    validation_mask = (result.index >= train_end) & (result.index < validation_end)
    result.loc[validation_mask, "split"] = "val"

    target_config = contract["target"]
    if target_config.get("mode") != "next_close":
        raise ValueError("load_full only supports target mode 'next_close'.")
    horizon = int(target_config["horizon"])
    if horizon <= 0:
        raise ValueError("Target horizon must be positive.")

    result["next_close"] = result.groupby("split", sort=False)["close"].shift(-horizon)
    return result[[*SNAPSHOT_COLUMNS, "next_close", "split"]]


def assert_locked_dataset(
    *,
    contract_path: PathLike = DEFAULT_CONTRACT_PATH,
    snapshot_root: PathLike = DEFAULT_SNAPSHOT_ROOT,
) -> None:
    """Fail fast unless the configured snapshot matches the locked contract."""
    try:
        contract = _load_contract(contract_path)
        _resolve_snapshot_files(contract, snapshot_root)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        logger.exception("Locked dataset validation failed: %s", exc)
        raise

    logger.info(
        "Locked dataset validated: version=%s, snapshot=%s",
        contract["dataset_version"],
        contract["source_snapshot_name"],
    )


def load_full(
    ticker: str,
    timeframe: str,
    *,
    contract_path: PathLike = DEFAULT_CONTRACT_PATH,
    snapshot_root: PathLike = DEFAULT_SNAPSHOT_ROOT,
) -> pd.DataFrame:
    """
    Load one complete locked OHLCV series with chronological split labels.

    The returned rows stay in one DataFrame so downstream lag and rolling
    features can use history across split boundaries. Targets never cross from
    train into validation or from validation into test.
    """
    normalized_ticker = _normalize_ticker(ticker)
    normalized_timeframe = timeframe.strip().lower()
    if not normalized_timeframe:
        raise ValueError("timeframe must not be empty.")

    try:
        contract = _load_contract(contract_path)
        timeframe_config = _find_timeframe_config(
            contract,
            normalized_ticker,
            normalized_timeframe,
        )
        symbol_path, ohlcv_path = _resolve_snapshot_files(contract, snapshot_root)
        symbol_id = _load_symbol_id(symbol_path, normalized_ticker)
        full_series = _load_ohlcv_rows(
            ohlcv_path,
            symbol_id,
            normalized_timeframe,
            timeframe_config,
        )
        result = _add_split_and_target(full_series, contract)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        logger.exception(
            "Failed to load locked dataset for ticker=%s, timeframe=%s: %s",
            normalized_ticker,
            normalized_timeframe,
            exc,
        )
        raise

    logger.info(
        "Loaded %d locked rows for ticker=%s, timeframe=%s",
        len(result),
        normalized_ticker,
        normalized_timeframe,
    )
    return result
