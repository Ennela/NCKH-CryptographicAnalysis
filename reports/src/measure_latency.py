"""Measure /api/v1/predict latency per model for the RQ5 acceptance criterion (p95 <= 2 s).

Three scenarios per model, all against a running stack:
  - first_call: the first request after the inference container starts, which
    downloads and loads the model from MLflow (restart the container first).
  - cache_miss: the Redis prediction key is deleted before every request, so the
    model really runs (model already in memory).
  - cache_hit: the same request repeated; served from Redis.

Requests are paced below RATE_LIMIT_PER_MINUTE (shared by every endpoint for one
API key), otherwise later models would be measured as HTTP 429 instead of latency.

Usage (stack running, inference on :8010, freshly restarted for first_call):
    API_KEY=... python reports/src/measure_latency.py reports/validations/api_latency_2026-10-07.csv
"""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("API", "http://localhost:8010")
API_KEY = os.environ["API_KEY"]
REDIS_CONTAINER = os.environ.get("REDIS_CONTAINER", "forecast_redis")
TICKER = os.environ.get("TICKER", "ACB")
TIMEFRAME = os.environ.get("TIMEFRAME", "1d")
STEPS = int(os.environ.get("STEPS", "5"))
MODELS = ("arima", "xgboost", "random_forest", "gru")
MISS_RUNS = int(os.environ.get("MISS_RUNS", "10"))
HIT_RUNS = int(os.environ.get("HIT_RUNS", "30"))
# 60 requests/minute limit -> one request every 1.1 s keeps a safety margin.
PACE_SECONDS = float(os.environ.get("PACE_SECONDS", "1.1"))


def cache_key(model: str) -> str:
    """Mirror the key built by services/inference/main.py:predict_price."""
    return f"prediction:{TICKER}:{TIMEFRAME}:{model}:{STEPS}"


def clear_cache(model: str) -> None:
    """Delete the Redis prediction entry so the next request runs the model."""
    subprocess.run(
        ["docker", "exec", REDIS_CONTAINER, "redis-cli", "DEL", cache_key(model)],
        check=True,
        capture_output=True,
    )


def timed_predict(model: str) -> tuple[int, float]:
    """POST one forecast request; return (HTTP status, wall-clock seconds)."""
    body = json.dumps(
        {
            "ticker_id": TICKER,
            "model_name": model,
            "steps": STEPS,
            "timeframe": TIMEFRAME,
        }
    ).encode()
    request = urllib.request.Request(
        f"{API}/api/v1/predict",
        data=body,
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    elapsed = time.perf_counter() - start
    time.sleep(max(0.0, PACE_SECONDS - elapsed))
    return status, elapsed


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100) of a non-empty list."""
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100.0 * len(ordered)))
    return ordered[rank - 1]


def measure(model: str) -> list[dict[str, object]]:
    """Run the three scenarios for one model and return one row per request."""
    rows: list[dict[str, object]] = []
    clear_cache(model)
    status, seconds = timed_predict(model)
    rows.append(
        {"model": model, "scenario": "first_call", "status": status, "seconds": seconds}
    )
    for _ in range(MISS_RUNS):
        clear_cache(model)
        status, seconds = timed_predict(model)
        rows.append(
            {
                "model": model,
                "scenario": "cache_miss",
                "status": status,
                "seconds": seconds,
            }
        )
    for _ in range(HIT_RUNS):
        status, seconds = timed_predict(model)
        rows.append(
            {
                "model": model,
                "scenario": "cache_hit",
                "status": status,
                "seconds": seconds,
            }
        )
    return rows


def summarize(rows: list[dict[str, object]]) -> None:
    """Print n, non-200 count, p50/p95/max in milliseconds per model and scenario."""
    print("model,scenario,n,non_200,p50_ms,p95_ms,max_ms")
    for model in MODELS:
        for scenario in ("first_call", "cache_miss", "cache_hit"):
            group = [
                r for r in rows if r["model"] == model and r["scenario"] == scenario
            ]
            ok = [float(r["seconds"]) * 1000 for r in group if r["status"] == 200]
            failed = len(group) - len(ok)
            if not ok:
                print(f"{model},{scenario},{len(group)},{failed},,,")
                continue
            print(
                f"{model},{scenario},{len(group)},{failed},"
                f"{statistics.median(ok):.1f},{percentile(ok, 95):.1f},{max(ok):.1f}"
            )


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "api_latency.csv"
    rows = [row for model in MODELS for row in measure(model)]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["model", "scenario", "status", "seconds"]
        )
        writer.writeheader()
        writer.writerows(rows)
    summarize(rows)


if __name__ == "__main__":
    main()
