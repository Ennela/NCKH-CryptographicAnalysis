"""GRU feature-group ablation on the locked dataset.

Retrains the fixed GRU benchmark with subsets of its eight input features and
compares test metrics against the full model and the Naive baseline. Every
variant reuses train_gru's data pipeline (causal features, train-only scalers,
chronological splits) and seed handling, so the "full" variant must reproduce
the registered GRU run exactly; that is the built-in sanity check.

Runs are logged to the MLflow experiment ``ablation_gru_features`` without
registering models, so the serving registry is untouched. Results are also
appended to a CSV for the report.

Usage:
    python -m services.training.ablation_gru --ticker ACB --timeframe 1d \
        --output reports/validations/ablation_gru_features.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from services.training.models.gru_model import GRUForecaster
from services.training.train_gru import (
    DEFAULT_SEED,
    FEATURE_LIST,
    MODEL_NAME,
    GRUTrainingConfig,
    MetricValues,
    PreparedSequences,
    SequenceSplit,
    build_sequence_dataset,
    create_data_loader,
    evaluate_predictions,
    inverse_predictions_once,
    load_dataset_metadata,
    predict_scaled,
    resolve_device,
    set_random_seed,
    train_with_early_stopping,
)
from shared.dataset.loader import assert_locked_dataset, load_full
from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)

EXPERIMENT_NAME = "ablation_gru_features"
# "close" must stay first: the GRU residual head adds its output to input[..., 0].
FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "full": FEATURE_LIST,
    "close_moving_averages": ("close", "moving_average_7", "moving_average_14"),
    "close_only": ("close",),
}
RESULT_FIELDNAMES: tuple[str, ...] = (
    "symbol",
    "timeframe",
    "variant",
    "features",
    "n_features",
    "seed",
    "n_test",
    "best_epoch",
    "rmse",
    "mae",
    "mape_pct",
    "directional_accuracy",
    "naive_rmse",
    "improvement_vs_naive_rmse_pct",
    "run_id",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the ablation CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=sorted(FEATURE_SETS),
        default=list(FEATURE_SETS),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def feature_indices(features: tuple[str, ...]) -> list[int]:
    """Positions of ``features`` in train_gru.FEATURE_LIST; close must be first."""
    if not features or features[0] != "close":
        raise ValueError("Every GRU ablation variant must keep 'close' first.")
    unknown = [name for name in features if name not in FEATURE_LIST]
    if unknown:
        raise ValueError(f"Unknown GRU features: {unknown}")
    return [FEATURE_LIST.index(name) for name in features]


def select_features(split: SequenceSplit, indices: list[int]) -> SequenceSplit:
    """Keep only the given feature channels of every sequence in a split.

    The scaler is per-column MinMax fitted on train, so slicing scaled columns
    equals scaling only the kept columns: no information leaks across splits.
    """
    return replace(split, X=np.ascontiguousarray(split.X[:, :, indices]))


def train_variant(
    sequences: PreparedSequences,
    features: tuple[str, ...],
    seed: int,
) -> tuple[MetricValues, int]:
    """Train and test one GRU on a feature subset; return (metrics, best epoch)."""
    indices = feature_indices(features)
    train, val, test = (
        select_features(split, indices)
        for split in (sequences.train, sequences.val, sequences.test)
    )
    config = replace(GRUTrainingConfig(), input_size=len(features))
    device = resolve_device()
    train_loader = create_data_loader(train, config.batch_size, seed)
    validation_loader = create_data_loader(val, config.batch_size, seed)
    # Re-seed right before weight init so each variant starts like train_gru.
    set_random_seed(seed)
    model = GRUForecaster(
        input_size=config.input_size,
        hidden_size=config.hidden_size,
        num_layers=config.num_layers,
        dropout=config.dropout,
    ).to(device)
    result = train_with_early_stopping(
        model, train_loader, validation_loader, config, device
    )
    scaled = predict_scaled(model, test, config.batch_size, device)
    predictions = inverse_predictions_once(sequences.target_scaler, scaled)
    metrics = evaluate_predictions(test.actual_close, predictions, test.current_close)
    return metrics, result.best_epoch


def log_variant(
    symbol: str,
    timeframe: str,
    variant: str,
    seed: int,
    metrics: MetricValues,
    extra_params: dict[str, Any],
) -> str:
    """Log one ablation run to MLflow (no model registration); return run ID."""
    import mlflow

    from services.training.mlflow_utils import init_mlflow

    init_mlflow()
    mlflow.set_experiment(EXPERIMENT_NAME)
    with mlflow.start_run(
        run_name=f"{MODEL_NAME}_{symbol}_{timeframe}_{variant}"
    ) as run:
        mlflow.log_params(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "model": MODEL_NAME,
                "variant": variant,
                "features": ",".join(FEATURE_SETS[variant]),
                "seed": seed,
                **extra_params,
            }
        )
        mlflow.log_metrics(metrics)
        return str(run.info.run_id)


def append_result(path: Path, row: dict[str, Any]) -> None:
    """Append one result row, writing the header when the file is new."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=RESULT_FIELDNAMES, lineterminator="\n"
        )
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def run_ablation(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Run every requested variant for one series and record the results."""
    set_random_seed(args.seed)
    assert_locked_dataset()
    metadata = load_dataset_metadata()
    symbol = args.ticker.strip().replace("/", "").upper()
    timeframe = args.timeframe.strip().lower()
    sequences = build_sequence_dataset(
        load_full(symbol, timeframe), GRUTrainingConfig()
    )
    rows: list[dict[str, Any]] = []
    for variant in args.variants:
        features = FEATURE_SETS[variant]
        metrics, best_epoch = train_variant(sequences, features, args.seed)
        run_id = log_variant(
            symbol,
            timeframe,
            variant,
            args.seed,
            metrics,
            {"dataset_version": metadata.dataset_version, "best_epoch": best_epoch},
        )
        row = {
            "symbol": symbol,
            "timeframe": timeframe,
            "variant": variant,
            "features": " ".join(features),
            "n_features": len(features),
            "seed": args.seed,
            "n_test": len(sequences.test),
            "best_epoch": best_epoch,
            **{key: metrics[key] for key in RESULT_FIELDNAMES if key in metrics},
            "run_id": run_id,
        }
        append_result(args.output, row)
        logger.info(
            "Ablation %s %s %s: rmse=%.6f", symbol, timeframe, variant, metrics["rmse"]
        )
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> None:
    """Command-line entrypoint."""
    args = parse_args(argv)
    setup_logging()
    run_ablation(args)


if __name__ == "__main__":
    main()
