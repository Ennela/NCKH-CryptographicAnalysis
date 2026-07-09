import json
from pathlib import Path
from typing import Any, Optional


DatasetContract = dict[str, Any]


def normalize_ticker(ticker: str) -> str:
    """Normalize stock/crypto ticker for lookup in the dataset contract."""
    return ticker.strip().replace("/", "").upper()


def resolve_contract_path(path: str | Path) -> Path:
    """
    Resolve a contract path from either the current working directory or repo root.

    The training container runs from /app/services/training, while local commands
    may run from the repository root. This helper supports both.
    """
    contract_path = Path(path)
    if contract_path.is_absolute() and contract_path.exists():
        return contract_path
    if contract_path.exists():
        return contract_path

    repo_root = Path(__file__).resolve().parents[2]
    rooted_path = repo_root / contract_path
    if rooted_path.exists():
        return rooted_path

    raise FileNotFoundError(f"Dataset contract not found: {path}")


def load_dataset_contract(path: Optional[str]) -> Optional[DatasetContract]:
    """Load a dataset contract JSON file, or return None when disabled."""
    if path is None:
        return None

    contract_path = resolve_contract_path(path)
    return json.loads(contract_path.read_text(encoding="utf-8"))


def find_asset_for_symbol(contract: DatasetContract, ticker: str) -> str:
    """Return the asset class that owns a ticker in the contract."""
    normalized = normalize_ticker(ticker)
    for asset_class, asset_config in contract["assets"].items():
        symbols = {normalize_ticker(symbol) for symbol in asset_config["symbols"]}
        if normalized in symbols:
            return asset_class

    raise ValueError(
        f"Ticker '{ticker}' is not part of dataset {contract['dataset_version']}."
    )


def get_timeframe_contract(
    contract: DatasetContract,
    ticker: str,
    timeframe: str,
) -> dict[str, Any]:
    """Return timeframe constraints for a ticker/timeframe pair."""
    asset_class = find_asset_for_symbol(contract, ticker)
    timeframes = contract["assets"][asset_class]["timeframes"]
    if timeframe not in timeframes:
        raise ValueError(
            f"Timeframe '{timeframe}' is not allowed for {ticker} "
            f"in dataset {contract['dataset_version']}."
        )
    return timeframes[timeframe]


def get_split_config(contract: Optional[DatasetContract]) -> tuple[float, float]:
    """Return train/validation split ratios."""
    if contract is None:
        return 0.70, 0.15

    split = contract["split"]
    return float(split["train_ratio"]), float(split["validation_ratio"])


def get_target_config(contract: Optional[DatasetContract]) -> tuple[int, str]:
    """Return target horizon and target mode."""
    if contract is None:
        return 1, "next_close"

    target = contract["target"]
    return int(target["horizon"]), str(target["mode"])


def validate_row_count(
    contract: DatasetContract,
    ticker: str,
    timeframe: str,
    row_count: int,
) -> None:
    """Fail fast when local DB data does not match the shared dataset contract."""
    timeframe_config = get_timeframe_contract(contract, ticker, timeframe)

    exact = timeframe_config.get("expected_rows_per_symbol")
    minimum = timeframe_config.get("expected_rows_per_symbol_min")
    maximum = timeframe_config.get("expected_rows_per_symbol_max")

    if exact is not None and row_count != int(exact):
        raise ValueError(
            f"{ticker} {timeframe} has {row_count} rows, expected {exact} "
            f"for dataset {contract['dataset_version']}."
        )

    if minimum is not None and row_count < int(minimum):
        raise ValueError(
            f"{ticker} {timeframe} has {row_count} rows, expected at least {minimum} "
            f"for dataset {contract['dataset_version']}."
        )

    if maximum is not None and row_count > int(maximum):
        raise ValueError(
            f"{ticker} {timeframe} has {row_count} rows, expected at most {maximum} "
            f"for dataset {contract['dataset_version']}."
        )
