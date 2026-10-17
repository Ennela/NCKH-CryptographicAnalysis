#!/usr/bin/env bash
# First-run data and model setup for docker-compose.prod.yml.
#
# A fresh production stack has an empty database and an empty MLflow Model
# Registry, so the web app has nothing to chart or forecast. This script:
#   1. imports the locked dataset snapshot (data/snapshots/ohlcv_full_current),
#   2. checks it against configs/group_dataset.json,
#   3. catches crypto up from the end of the snapshot to now (Binance),
#   4. trains the 4 models for each series and registers them in MLflow,
#   5. restarts inference so it serves the new models.
#
# Run from the repository root while the stack is up:
#   docker compose -f docker-compose.prod.yml up -d
#   bash scripts/prod_bootstrap.sh            # everything
#   bash scripts/prod_bootstrap.sh --skip-train
#
# Environment overrides:
#   COMPOSE          compose command (default: docker compose -f docker-compose.prod.yml)
#   BOOTSTRAP_SERIES series to train, "TICKER:TIMEFRAME ..." (default: the 9 series
#                    reported in the experiments)
#   BOOTSTRAP_SEED   training seed (default: 42)
#
# Stock prices are not caught up: vnstock is optional (see docs/dataset.md), so
# stock data ends where the snapshot ends unless the ingestion image is built
# with INSTALL_VNSTOCK=true.
set -euo pipefail

COMPOSE="${COMPOSE:-docker compose -f docker-compose.prod.yml}"
BOOTSTRAP_SERIES="${BOOTSTRAP_SERIES:-ACB:1d FPT:1d HPG:1d VCB:1d VNM:1d BTCUSDT:1d ETHUSDT:1d SOLUSDT:1d BTCUSDT:1h}"
BOOTSTRAP_SEED="${BOOTSTRAP_SEED:-42}"
MODELS="arima xgboost random_forest gru"
SNAPSHOT_DIR="data/snapshots/ohlcv_full_current"
SKIP_TRAIN=false
[[ "${1:-}" == "--skip-train" ]] && SKIP_TRAIN=true

# Docker on Windows (Git Bash) needs a Windows path for the bind mount.
if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* ]]; then
  export MSYS_NO_PATHCONV=1
  REPO_DIR="$(pwd -W)"
else
  REPO_DIR="$(pwd)"
fi

# One-off containers see the checkout (scripts/, configs/, data/snapshots/).
run_in() {
  local service="$1"
  shift
  $COMPOSE run --rm -v "$REPO_DIR:/app" -w /app -e PYTHONPATH=/app "$service" "$@"
}

psql_value() {
  $COMPOSE exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$0"' "$1"
}

if [[ ! -f "$SNAPSHOT_DIR/manifest.json" ]]; then
  echo "Missing $SNAPSHOT_DIR/manifest.json — copy the dataset snapshot first (docs/deploy.md)." >&2
  exit 1
fi

echo "== 1/5 Import dataset snapshot"
existing_rows="$(psql_value 'SELECT count(*) FROM market.ohlcv')"
if [[ "$existing_rows" -gt 0 ]]; then
  echo "market.ohlcv already has $existing_rows rows — skipping import."
else
  run_in training python scripts/import_dataset_snapshot.py --snapshot-dir "$SNAPSHOT_DIR"
fi

echo "== 2/5 Check dataset contract"
run_in training python scripts/check_group_dataset.py

echo "== 3/5 Catch crypto up to now"
for ticker in $(psql_value "SELECT ticker FROM market.symbol WHERE asset_class = 'crypto' ORDER BY ticker"); do
  pair="${ticker%USDT}/USDT"
  for timeframe in 1h 1d; do
    last_ts="$(psql_value "SELECT to_char(max(o.ts) AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI') FROM market.ohlcv o JOIN market.symbol s ON s.id = o.symbol_id WHERE s.ticker = '$ticker' AND o.timeframe = '$timeframe'")"
    if [[ -z "$last_ts" ]]; then
      echo "  $pair $timeframe: no stored bars, skipped"
      continue
    fi
    echo "  $pair $timeframe from $last_ts"
    run_in ingestion python -m scripts.backfill --symbol "$pair" --resolution "$timeframe" \
      --start "$last_ts" --skip-existing
  done
done

if [[ "$SKIP_TRAIN" == true ]]; then
  echo "== 4/5 Training skipped (--skip-train)"
else
  echo "== 4/5 Train and register models"
  failed=()
  for series in $BOOTSTRAP_SERIES; do
    ticker="${series%%:*}"
    timeframe="${series##*:}"
    for model in $MODELS; do
      echo "  $model $ticker $timeframe"
      if ! run_in training python -m "services.training.train_$model" \
        --ticker "$ticker" --timeframe "$timeframe" --seed "$BOOTSTRAP_SEED"; then
        failed+=("$model $ticker $timeframe")
      fi
    done
  done
  if [[ ${#failed[@]} -gt 0 ]]; then
    printf 'Training failed for: %s\n' "${failed[@]}" >&2
    exit 1
  fi
fi

echo "== 5/5 Restart inference to load the registered models"
$COMPOSE restart inference
echo "Done."
