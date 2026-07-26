import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import mlflow
import pandas as pd
import redis
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient
from sqlalchemy import text
from sqlalchemy.orm import Session

# Import Shared Module Components
from shared.utils.logging import setup_logging
from shared.utils.timezone import now_utc
from shared.config.settings import settings
from shared.db.session import get_db

# Note: hypertable tables (market.ohlcv, ml.prediction) use raw SQL, not ORM models
from shared.schemas.predict import (
    ALLOWED_MODELS,
    ALLOWED_TIMEFRAMES,
    ExplainFeature,
    ExplainResponse,
    ModelInfoResponse,
    ModelMetrics,
    PredictRequest,
    PredictResponse,
    PredictionItem,
)

# Local imports
from model_loader import (
    LoadedModel,
    ModelLoadError,
    ModelNotRegisteredError,
    build_registry_name,
    model_loader,
    normalize_ticker,
)
from redis_cache import redis_cache

# Initialize logs
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Stock & Crypto Inference Service",
    description="Serving ML model predictions cached via Redis",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# CORS — cho phép frontend dev server kết nối
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Số nến lịch sử nạp cho các model dạng feature (đủ dư cho lag 20 và
# giai đoạn warm-up của các chỉ báo EWM như RSI/MACD).
FEATURE_HISTORY_BARS = 400
# ARIMA cần mọi nến sau history_end_ts của model đã log để tiến trạng thái.
ARIMA_HISTORY_BARS = 5000
STEP_DELTAS = {"1d": timedelta(days=1), "1h": timedelta(hours=1)}
PREDICTION_CACHE_TTL_SECONDS = 300
EXPLAIN_ARTIFACT_PATH = "explainability/feature_importance.json"

# ==============================================================================
# Security Middleware & Helpers
# ==============================================================================


async def verify_api_key(
    x_api_key: str = Header(..., description="API Key for client verification"),
):
    """Verifies client request API Key."""
    if x_api_key != settings.API_KEY_SECRET:
        logger.warning("Unauthorized access attempt with an invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )
    return x_api_key


async def rate_limiter(request: Request, x_api_key: str = Depends(verify_api_key)):
    """
    Very simple Redis-based Rate Limiter.
    Limits clients based on their API Key and IP.
    """
    if not redis_cache.client:
        return  # Skip rate limit checks if Redis is not running

    client_ip = request.client.host
    rate_limit_key = f"rate_limit:{x_api_key}:{client_ip}"

    try:
        current_requests = redis_cache.client.get(rate_limit_key)
        if current_requests and int(current_requests) >= settings.RATE_LIMIT_PER_MINUTE:
            logger.warning(f"Rate limit exceeded for client: {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Limit exceeded.",
            )

        # Increment request count and set 60s expiration
        pipe = redis_cache.client.pipeline()
        pipe.incr(rate_limit_key)
        pipe.expire(rate_limit_key, 60)
        pipe.execute()

    except redis.RedisError as e:
        logger.error(f"Rate limiter Redis error: {str(e)}")
        # Allow request to proceed if rate limiting fails due to Redis error (Fail-open design)
        return


# ==============================================================================
# Data access helpers
# ==============================================================================


def _resolve_symbol(db: Session, ticker: str) -> tuple[int, str]:
    """Lookup (symbol_id, asset_class) for a normalized ticker, else 404."""
    row = db.execute(
        text(
            "SELECT id, asset_class::text FROM market.symbol "
            "WHERE ticker = :ticker AND status = 'active'"
        ),
        {"ticker": ticker},
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found.")
    return int(row[0]), str(row[1])


def _load_history(
    db: Session, symbol_id: int, timeframe: str, limit: int
) -> pd.DataFrame:
    """Load the newest `limit` OHLCV bars as a chronological DataFrame."""
    rows = db.execute(
        text(
            "SELECT ts, open, high, low, close, volume FROM market.ohlcv "
            "WHERE symbol_id = :symbol_id AND timeframe = :timeframe "
            "ORDER BY ts DESC LIMIT :limit"
        ),
        {"symbol_id": symbol_id, "timeframe": timeframe, "limit": limit},
    ).fetchall()
    frame = pd.DataFrame(
        list(reversed(rows)),
        columns=["ts", "open", "high", "low", "close", "volume"],
    )
    if not frame.empty:
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = frame[column].astype(float)
    return frame


def _persist_predictions(
    db: Session,
    loaded: LoadedModel,
    symbol_id: int,
    feature_asof_ts: datetime,
    predictions: List[PredictionItem],
) -> None:
    """Best-effort write of predictions into ml.prediction.

    ml.prediction requires a model_version_id FK; rows are only written when
    an ml.model_version entry exists for the MLflow run that produced the
    model (registered by the training/ops flow). Missing rows are logged and
    skipped — the API response is never affected.
    """
    try:
        row = db.execute(
            text(
                "SELECT id FROM ml.model_version "
                "WHERE mlflow_run_id = :run_id ORDER BY id DESC LIMIT 1"
            ),
            {"run_id": loaded.run_id},
        ).first()
        if not row:
            logger.info(
                "No ml.model_version row for MLflow run %s — "
                "skipping prediction persistence.",
                loaded.run_id,
            )
            return
        model_version_id = int(row[0])
        for horizon, item in enumerate(predictions, start=1):
            db.execute(
                text(
                    "INSERT INTO ml.prediction "
                    "(model_version_id, symbol_id, feature_asof_ts, target_ts, "
                    " horizon, y_pred) "
                    "VALUES (:model_version_id, :symbol_id, :feature_asof_ts, "
                    "        :target_ts, :horizon, :y_pred) "
                    "ON CONFLICT ON CONSTRAINT uq_prediction "
                    "DO UPDATE SET y_pred = EXCLUDED.y_pred"
                ),
                {
                    "model_version_id": model_version_id,
                    "symbol_id": symbol_id,
                    "feature_asof_ts": feature_asof_ts,
                    "target_ts": item.target_time,
                    "horizon": horizon,
                    "y_pred": item.predicted_value,
                },
            )
        db.commit()
        logger.info(
            "Persisted %d predictions (model_version_id=%d).",
            len(predictions),
            model_version_id,
        )
    except Exception as exc:  # noqa: BLE001 — persistence must never break the API
        logger.warning("Prediction persistence failed: %s", exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


# ==============================================================================
# API Endpoints
# ==============================================================================


@app.get("/health")
def health_check():
    """Health check endpoint for Docker Compose / Kubernetes."""
    return {"status": "healthy", "service": "inference"}


@app.post(
    "/api/v1/predict",
    response_model=PredictResponse,
    dependencies=[Depends(rate_limiter)],
)
def predict_price(payload: PredictRequest, db: Session = Depends(get_db)):
    """
    Dự báo giá tài sản chứng khoán/crypto bằng model đã đăng ký trong
    MLflow Registry. Kết quả được cache Redis và ghi ml.prediction (best-effort).
    """
    ticker = normalize_ticker(payload.ticker_id)
    symbol_id, asset_class = _resolve_symbol(db, ticker)
    timeframe = payload.timeframe or ("1h" if asset_class == "crypto" else "1d")

    cache_key = f"prediction:{ticker}:{timeframe}:{payload.model_name}:{payload.steps}"
    cached_response = redis_cache.get(cache_key)
    if cached_response:
        logger.info(f"Cache hit for {cache_key}")
        return PredictResponse(**cached_response)

    # 1. Load model từ MLflow Registry (503 khi chưa train / MLflow down)
    try:
        loaded = model_loader.load(ticker, timeframe, payload.model_name)
    except ModelNotRegisteredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ModelLoadError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # 2. Nạp lịch sử OHLCV làm input cho feature/sequence/state
    history_bars = (
        ARIMA_HISTORY_BARS if payload.model_name == "arima" else FEATURE_HISTORY_BARS
    )
    history = _load_history(db, symbol_id, timeframe, history_bars)
    if history.empty:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No historical price records found for ticker {ticker} "
                f"(timeframe={timeframe}). Can't forecast."
            ),
        )

    # 3. Chạy dự báo thật bằng predictor tương ứng flavor
    try:
        values = loaded.predictor.predict_steps(history, payload.steps)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough usable history for {ticker} ({timeframe}): {exc}",
        ) from exc

    step_delta = STEP_DELTAS[timeframe]
    last_bar_ts = history["ts"].iloc[-1].to_pydatetime()
    prediction_time = now_utc()
    predictions = [
        PredictionItem(
            target_time=last_bar_ts + step_delta * step,
            predicted_value=value,
        )
        for step, value in enumerate(values, start=1)
    ]

    # 4. Ghi ml.prediction (best-effort, không ảnh hưởng response)
    _persist_predictions(db, loaded, symbol_id, last_bar_ts, predictions)

    logger.info(
        "Generated %d predictions for %s/%s using %s v%d",
        len(predictions),
        ticker,
        timeframe,
        loaded.registry_name,
        loaded.version,
    )

    response = PredictResponse(
        ticker_id=ticker,
        model_name=payload.model_name,
        prediction_time=prediction_time,
        predictions=predictions,
    )

    # 5. Cache Redis (JSON-safe dump để serialize được datetime)
    redis_cache.set(
        cache_key,
        response.model_dump(mode="json"),
        ttl_seconds=PREDICTION_CACHE_TTL_SECONDS,
    )
    return response


@app.get(
    "/api/v1/models",
    response_model=List[ModelInfoResponse],
    dependencies=[Depends(verify_api_key)],
)
def get_active_models():
    """
    Lấy danh sách model đã đăng ký trong MLflow Registry kèm metrics
    (mae/rmse/mape) đọc từ run huấn luyện tương ứng.
    """
    client = MlflowClient()
    try:
        registered = client.search_registered_models()
    except MlflowException as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MLflow Registry unavailable: {exc}",
        ) from exc

    results: List[ModelInfoResponse] = []
    for registered_model in registered:
        versions = registered_model.latest_versions or []
        if not versions:
            continue
        newest = max(versions, key=lambda v: int(v.version))

        metrics: Optional[ModelMetrics] = None
        try:
            run_metrics = client.get_run(newest.run_id).data.metrics
            mae = run_metrics.get("mae")
            rmse = run_metrics.get("rmse")
            mape = run_metrics.get("mape_pct", run_metrics.get("mape"))
            if mae is not None and rmse is not None and mape is not None:
                metrics = ModelMetrics(mae=mae, rmse=rmse, mape=mape)
        except MlflowException as exc:
            logger.warning(
                "Could not read metrics for %s: %s", registered_model.name, exc
            )

        stage = (newest.current_stage or "None").lower()
        status_label = "active" if stage in ("none", "production") else stage
        last_updated = None
        if registered_model.last_updated_timestamp:
            last_updated = datetime.fromtimestamp(
                registered_model.last_updated_timestamp / 1000, tz=timezone.utc
            )
        results.append(
            ModelInfoResponse(
                model_name=registered_model.name,
                version=str(newest.version),
                status=status_label,
                metrics=metrics,
                last_updated=last_updated,
            )
        )
    return results


@app.get(
    "/api/v1/explain",
    response_model=ExplainResponse,
    dependencies=[Depends(rate_limiter)],
)
def explain_model(
    ticker: str = Query(..., description="Mã tài sản, VD: ACB, BTCUSDT"),
    timeframe: str = Query("1d", description="Khung thời gian: 1d, 1h"),
    model_name: str = Query("xgboost", description="Model cần giải thích"),
):
    """
    Trả về giải thích mô hình (SHAP) đọc từ artifact
    explainability/feature_importance.json do train_xgboost log lên MLflow.
    """
    timeframe = timeframe.strip().lower()
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe '{timeframe}'. Must be one of {ALLOWED_TIMEFRAMES}",
        )
    model_name = model_name.strip().lower()
    if model_name not in ALLOWED_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model '{model_name}'. Must be one of {ALLOWED_MODELS}",
        )

    registry_name = build_registry_name(ticker, timeframe, model_name)
    try:
        _version, run_id = model_loader.latest_version(registry_name)
    except ModelNotRegisteredError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelLoadError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        artifact_path = mlflow.artifacts.download_artifacts(
            run_id=run_id, artifact_path=EXPLAIN_ARTIFACT_PATH
        )
        payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — missing artifact -> 404
        raise HTTPException(
            status_code=404,
            detail=(
                f"Model '{registry_name}' has no SHAP explainability artifact. "
                "Re-run its training entrypoint to generate one."
            ),
        ) from exc

    features = [ExplainFeature(**feature) for feature in payload.get("features", [])]
    return ExplainResponse(
        ticker=normalize_ticker(ticker),
        timeframe=timeframe,
        model_name=model_name,
        method=payload.get("method", "shap_tree_explainer"),
        features=features,
        generated_at=payload.get("generated_at"),
    )


@app.get(
    "/api/v1/symbols",
    dependencies=[Depends(verify_api_key)],
)
def list_symbols(db: Session = Depends(get_db)):
    """
    Lấy danh sách tất cả mã tài sản đang hoạt động từ market.symbol.
    Returns: list of {ticker, asset_class, exchange_code, company_name}.
    """
    query = text(
        "SELECT s.ticker, s.asset_class::text, e.code AS exchange_code, "
        "       s.company_name "
        "FROM market.symbol s "
        "JOIN market.exchange e ON e.id = s.exchange_id "
        "WHERE s.status = 'active' "
        "ORDER BY s.asset_class, s.ticker"
    )
    rows = db.execute(query).fetchall()
    return [
        {
            "ticker": row[0],
            "asset_class": row[1],
            "exchange_code": row[2],
            "company_name": row[3],
        }
        for row in rows
    ]


@app.get(
    "/api/v1/ohlcv",
    dependencies=[Depends(verify_api_key)],
)
def get_ohlcv_history(
    ticker: str = Query(..., description="Mã tài sản, VD: FPT, BTCUSDT"),
    timeframe: str = Query("1d", description="Khung thời gian: 1h, 1d"),
    limit: int = Query(100, ge=1, le=500, description="Số nến tối đa trả về"),
    db: Session = Depends(get_db),
):
    """
    Truy vấn dữ liệu OHLCV lịch sử từ market.ohlcv cho một mã tài sản.
    Input: ticker (str), timeframe (str), limit (int).
    Output: list of {ts, open, high, low, close, volume}.
    """
    # Validate timeframe
    allowed_tf = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")
    timeframe = timeframe.strip().lower()
    if timeframe not in allowed_tf:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe '{timeframe}'. Must be one of {allowed_tf}",
        )

    # Lookup symbol_id
    ticker_clean = ticker.strip().upper()
    sym_query = text(
        "SELECT id FROM market.symbol WHERE ticker = :ticker AND status = 'active'"
    )
    sym_row = db.execute(sym_query, {"ticker": ticker_clean}).first()
    if not sym_row:
        raise HTTPException(
            status_code=404, detail=f"Ticker '{ticker_clean}' not found."
        )
    symbol_id = sym_row[0]

    # Query OHLCV data
    ohlcv_query = text(
        "SELECT ts, open, high, low, close, volume "
        "FROM market.ohlcv "
        "WHERE symbol_id = :symbol_id AND timeframe = :timeframe "
        "ORDER BY ts DESC "
        "LIMIT :limit"
    )
    rows = db.execute(
        ohlcv_query,
        {"symbol_id": symbol_id, "timeframe": timeframe, "limit": limit},
    ).fetchall()

    # Return newest-first, frontend can reverse if needed
    return [
        {
            "ts": row[0].isoformat(),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in rows
    ]
