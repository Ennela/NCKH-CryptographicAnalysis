"""Summarize the GRU feature ablation CSV across seeds.

Reads the rows written by services/training/ablation_gru.py and prints, per
series and variant, mean ± sample std of test RMSE over seeds, the mean change
versus the full model, and whether that change exceeds the seed-to-seed spread.

Usage:
    python reports/src/ablation_summary.py reports/validations/ablation_gru_features_2026-10-09.csv
"""

from __future__ import annotations

import csv
import statistics
import sys
from collections import defaultdict

VARIANTS = ("full", "close_moving_averages", "close_only")


def load(path: str) -> dict[tuple[str, str], dict[str, list[float]]]:
    """Group RMSE values by (symbol, timeframe) then variant."""
    grouped: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    naive: dict[tuple[str, str], float] = {}
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row["symbol"], row["timeframe"])
            grouped[key][row["variant"]].append(float(row["rmse"]))
            naive[key] = float(row["naive_rmse"])
    for key, value in naive.items():
        grouped[key]["naive"] = [value]
    return grouped


def describe(values: list[float]) -> tuple[float, float]:
    """Mean and sample standard deviation (0 for a single value)."""
    spread = statistics.stdev(values) if len(values) > 1 else 0.0
    return statistics.fmean(values), spread


def main() -> None:
    grouped = load(sys.argv[1])
    print(
        "symbol,timeframe,n_seeds,naive_rmse,"
        + ",".join(f"{v}_mean,{v}_std" for v in VARIANTS)
        + ",close_only_vs_full_pct,close_only_vs_naive_pct,gap_exceeds_2std"
    )
    better = 0
    for key in sorted(grouped):
        stats = {v: describe(grouped[key][v]) for v in VARIANTS}
        naive = grouped[key]["naive"][0]
        full_mean, full_std = stats["full"]
        close_mean, close_std = stats["close_only"]
        vs_full = (close_mean - full_mean) / full_mean * 100.0
        vs_naive = (naive - close_mean) / naive * 100.0
        exceeds = abs(close_mean - full_mean) > 2 * max(full_std, close_std)
        better += close_mean <= full_mean
        cells = ",".join(f"{m:.6g},{s:.3g}" for m, s in stats.values())
        print(
            f"{key[0]},{key[1]},{len(grouped[key]['full'])},{naive:.6g},{cells},"
            f"{vs_full:+.2f},{vs_naive:+.2f},{exceeds}"
        )
    print(f"# close_only mean RMSE <= full mean RMSE in {better}/{len(grouped)} series")


if __name__ == "__main__":
    main()
