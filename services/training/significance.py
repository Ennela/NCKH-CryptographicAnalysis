"""Statistical significance of the benchmark against the Naive baseline.

Two analyses on the locked dataset, both read-only (no training, no registry
changes):

1. Diebold-Mariano test with the Harvey-Leybourne-Newbold small-sample
   correction, comparing each registered model with the Naive forecast
   (predicted = current close) on the exact test rows the model was scored on.
   Forecast vectors come from the ``predictions/`` CSV artifact of the latest
   registered version of ``{SYMBOL}_{timeframe}_{model}``. p-values are also
   Holm-adjusted across all model x dataset comparisons.
2. ADF and KPSS stationarity tests on the closing price and on its log return
   for each dataset, read through the shared locked loader.

Usage:
    python -m services.training.significance --output-dir reports/validations
"""

from __future__ import annotations

import argparse
import logging
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from shared.utils.logging import setup_logging

logger = logging.getLogger(__name__)

DATASETS: tuple[tuple[str, str], ...] = (
    ("ACB", "1d"),
    ("FPT", "1d"),
    ("HPG", "1d"),
    ("VCB", "1d"),
    ("VNM", "1d"),
    ("BTCUSDT", "1d"),
    ("ETHUSDT", "1d"),
    ("SOLUSDT", "1d"),
    ("BTCUSDT", "1h"),
)
MODELS: tuple[str, ...] = ("arima", "xgboost", "random_forest", "gru")
LOSSES: tuple[str, ...] = ("squared", "absolute")
ALPHA = 0.05


@dataclass(frozen=True)
class DMResult:
    """Diebold-Mariano comparison of one model against Naive."""

    statistic: float
    p_two_sided: float
    p_model_better: float
    mean_loss_differential: float
    n: int


def diebold_mariano(
    errors_baseline: np.ndarray,
    errors_model: np.ndarray,
    horizon: int = 1,
    loss: str = "squared",
) -> DMResult:
    """Diebold-Mariano test with the HLN (1997) small-sample correction.

    Input: forecast errors (actual - predicted) of the baseline and the model
    on the same rows. The loss differential is d_t = L(e_baseline) - L(e_model),
    so a positive statistic means the model has the lower loss. The long-run
    variance uses autocovariances up to lag horizon-1, and the statistic is
    compared with Student t on n-1 degrees of freedom.
    Output: the statistic, two-sided p, one-sided p for "model better", mean d.
    """
    if errors_baseline.shape != errors_model.shape or errors_baseline.ndim != 1:
        raise ValueError("Error vectors must be one-dimensional and equal length.")
    if loss == "squared":
        differential = errors_baseline**2 - errors_model**2
    elif loss == "absolute":
        differential = np.abs(errors_baseline) - np.abs(errors_model)
    else:
        raise ValueError(f"Unknown loss {loss!r}; use 'squared' or 'absolute'.")

    n = differential.size
    if n <= horizon + 1:
        raise ValueError("Need more observations than horizon + 1.")
    mean_d = float(differential.mean())
    centered = differential - mean_d
    autocov = [
        float(centered[lag:] @ centered[: n - lag]) / n for lag in range(horizon)
    ]
    long_run_variance = autocov[0] + 2.0 * sum(autocov[1:])
    if long_run_variance <= 0.0:
        raise ValueError(
            "Loss differential has zero variance; forecasts are identical."
        )

    dm = mean_d / np.sqrt(long_run_variance / n)
    hln = np.sqrt((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n)
    statistic = float(dm * hln)
    return DMResult(
        statistic=statistic,
        p_two_sided=float(2.0 * stats.t.sf(abs(statistic), df=n - 1)),
        p_model_better=float(stats.t.sf(statistic, df=n - 1)),
        mean_loss_differential=mean_d,
        n=n,
    )


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni step-down adjustment, returned in the input order."""
    m = len(p_values)
    order = np.argsort(p_values)
    adjusted = np.empty(m)
    running_max = 0.0
    for rank, index in enumerate(order):
        running_max = max(running_max, (m - rank) * p_values[index])
        adjusted[index] = min(1.0, running_max)
    return adjusted.tolist()


def stationarity(series: pd.Series) -> dict[str, float]:
    """ADF (H0: unit root) and KPSS (H0: level-stationary) on one series."""
    from statsmodels.tsa.stattools import adfuller, kpss

    values = series.dropna().to_numpy(dtype=np.float64)
    adf_stat, adf_p, *_ = adfuller(values, autolag="AIC")
    # KPSS p-values are interpolated from a table and capped to [0.01, 0.10].
    kpss_stat, kpss_p, *_ = kpss(values, regression="c", nlags="auto")
    return {
        "adf_stat": float(adf_stat),
        "adf_p": float(adf_p),
        "kpss_stat": float(kpss_stat),
        "kpss_p": float(kpss_p),
        "n": int(values.size),
    }


def load_registered_predictions(
    symbol: str, timeframe: str, model: str
) -> pd.DataFrame:
    """Download the prediction CSV of the latest registered model version."""
    from mlflow.tracking import MlflowClient

    client = MlflowClient()
    name = f"{symbol}_{timeframe}_{model}"
    versions = client.search_model_versions(f"name='{name}'")
    if not versions:
        raise LookupError(f"No registered versions for {name}.")
    latest = max(versions, key=lambda version: int(version.version))
    files = [item.path for item in client.list_artifacts(latest.run_id, "predictions")]
    if len(files) != 1:
        raise LookupError(
            f"{name} v{latest.version}: expected one prediction CSV, got {files}."
        )
    with tempfile.TemporaryDirectory() as tmp:
        local = client.download_artifacts(latest.run_id, files[0], tmp)
        frame = pd.read_csv(local)
    frame = frame.loc[frame["split"] == "test"].sort_values("target_ts")
    frame["model_version"] = int(latest.version)
    return frame


def dm_rows(datasets: Sequence[tuple[str, str]]) -> pd.DataFrame:
    """Run DM (both losses) for every model x dataset; add Holm-adjusted p."""
    rows: list[dict[str, object]] = []
    for symbol, timeframe in datasets:
        for model in MODELS:
            frame = load_registered_predictions(symbol, timeframe, model)
            actual = frame["actual_close"].to_numpy(dtype=np.float64)
            naive_error = actual - frame["current_close"].to_numpy(dtype=np.float64)
            model_error = actual - frame["predicted_close"].to_numpy(dtype=np.float64)
            row: dict[str, object] = {
                "symbol": symbol,
                "timeframe": timeframe,
                "model": model,
                "model_version": int(frame["model_version"].iloc[0]),
                "run_id": str(frame["run_id"].iloc[0]),
                "n": int(actual.size),
                "rmse": float(np.sqrt(np.mean(model_error**2))),
                "naive_rmse": float(np.sqrt(np.mean(naive_error**2))),
            }
            for loss in LOSSES:
                result = diebold_mariano(naive_error, model_error, loss=loss)
                row[f"dm_{loss}"] = result.statistic
                row[f"p_{loss}"] = result.p_two_sided
                row[f"p_better_{loss}"] = result.p_model_better
            rows.append(row)
            logger.info("DM %s %s %s: %s", symbol, timeframe, model, row)
    table = pd.DataFrame(rows)
    for loss in LOSSES:
        table[f"p_holm_{loss}"] = holm_adjust(table[f"p_{loss}"].tolist())
    table["verdict_squared"] = [
        _verdict(stat, p)
        for stat, p in zip(table["dm_squared"], table["p_holm_squared"])
    ]
    return table


def _verdict(statistic: float, adjusted_p: float) -> str:
    """Label one comparison after Holm adjustment."""
    if adjusted_p >= ALPHA:
        return "no_significant_difference"
    return "better_than_naive" if statistic > 0 else "worse_than_naive"


def stationarity_rows(datasets: Sequence[tuple[str, str]]) -> pd.DataFrame:
    """ADF/KPSS on close price and log return of each locked dataset."""
    from shared.dataset.loader import assert_locked_dataset, load_full

    assert_locked_dataset()
    rows: list[dict[str, object]] = []
    for symbol, timeframe in datasets:
        close = load_full(symbol, timeframe)["close"].astype(np.float64)
        series = {"close": close, "log_return": np.log(close).diff()}
        for name, values in series.items():
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "series": name,
                    **stationarity(values),
                }
            )
    return pd.DataFrame(rows)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path, default=Path("reports/validations"))
    parser.add_argument(
        "--tag", default=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Write dm_test_<tag>.csv and stationarity_<tag>.csv."""
    setup_logging()
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dm_path = args.output_dir / f"dm_test_{args.tag}.csv"
    stationarity_path = args.output_dir / f"stationarity_{args.tag}.csv"
    dm_rows(DATASETS).to_csv(dm_path, index=False, float_format="%.6g")
    stationarity_rows(DATASETS).to_csv(
        stationarity_path, index=False, float_format="%.6g"
    )
    logger.info("Wrote %s and %s", dm_path, stationarity_path)


if __name__ == "__main__":
    main()
