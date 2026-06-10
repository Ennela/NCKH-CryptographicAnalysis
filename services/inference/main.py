import logging
import redis
from datetime import timedelta
from typing import List
from fastapi import FastAPI, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import text

# Import Shared Module Components
from shared.utils.logging import setup_logging
from shared.utils.timezone import now_utc, to_utc
from shared.config.settings import settings
from shared.db.session import get_db
# Note: hypertable tables (market.ohlcv, ml.prediction) use raw SQL, not ORM models
from shared.schemas.predict import (
    PredictRequest,
    PredictResponse,
    PredictionItem,
    ModelInfoResponse,
    ModelMetrics,
)

# Local imports
from model_loader import model_loader
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

# ==============================================================================
# Security Middleware & Helpers
# ==============================================================================


async def verify_api_key(
    x_api_key: str = Header(..., description="API Key for client verification"),
):
    """Verifies client request API Key."""
    if x_api_key != settings.API_KEY_SECRET:
        logger.warning(f"Unauthorized access attempt with API Key: {x_api_key}")
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
    Dự báo giá tài sản chứng khoán/crypto bằng mô hình đã chọn.
    Sử dụng Cache Redis và lưu nhật ký dự đoán vào DB.
    """
    cache_key = f"prediction:{payload.ticker_id}:{payload.model_name}:{payload.steps}"

    # 1. Check Redis Cache
    cached_response = redis_cache.get(cache_key)
    if cached_response:
        logger.info(f"Cache hit for {cache_key}")
        return PredictResponse(**cached_response)

    # 2. Get latest features/data from database
    logger.info(
        f"Predicting price for {payload.ticker_id} using {payload.model_name}..."
    )

    # Determine step duration (1 hour for crypto 1h, 1 day for stock 1d)
    # Fetching the asset type from market.symbol by ticker name
    ticker_query = text(
        "SELECT id, asset_class FROM market.symbol WHERE ticker = :ticker"
    )
    ticker_res = db.execute(ticker_query, {"ticker": payload.ticker_id}).first()
    if not ticker_res:
        raise HTTPException(
            status_code=404, detail=f"Ticker '{payload.ticker_id}' not found."
        )

    symbol_id = ticker_res[0]
    asset_type = ticker_res[1]
    # Set step interval
    step_delta = timedelta(days=1)
    resolution = "1d"
    if asset_type == "crypto":
        step_delta = timedelta(hours=1)
        resolution = "1h"

    # Get latest close price from market.ohlcv hypertable (raw SQL)
    latest_query = text(
        "SELECT close FROM market.ohlcv "
        "WHERE symbol_id = :symbol_id AND timeframe = :timeframe "
        "ORDER BY ts DESC LIMIT 1"
    )
    latest_row = db.execute(
        latest_query, {"symbol_id": symbol_id, "timeframe": resolution}
    ).first()

    if not latest_row:
        raise HTTPException(
            status_code=400,
            detail=f"No historical price records found for ticker {payload.ticker_id} (res={resolution}). Can't forecast.",
        )

    # 3. Load model from MLflow Model Registry
    try:
        model = model_loader.load_registered_model(
            payload.ticker_id, payload.model_name
        )
    except Exception as e:
        logger.error(f"Failed loading model: {str(e)}")
        # Demo fallback: If MLflow is unavailable, we generate mock prediction trajectory
        logger.warning(
            "MLflow model registry unavailable. Generating mock trend trajectory for demo/frontend testing."
        )
        model = None

    # 4. Generate Predictions (Multi-step ahead forecasting)
    # Note: In a real system, the features matrix is loaded and model.predict(X) is executed.
    prediction_time = now_utc()
    predictions = []

    current_val = float(latest_row[0])
    for i in range(1, payload.steps + 1):
        target_time = prediction_time + (step_delta * i)

        if model:
            # TODO: Dev 3 & 4. Pass actual features into the MLflow model.
            # Example: features = load_latest_features(payload.ticker_id)
            # current_val = model.predict(features)

            # Simple placeholder using loaded model details
            current_val = current_val * 1.001  # small upward drift mock
        else:
            # Mock drift for demo if MLflow is offline
            import random

            drift = random.uniform(-0.02, 0.02)
            current_val = current_val * (1 + drift)

        predictions.append(
            PredictionItem(target_time=to_utc(target_time), predicted_value=current_val)
        )

    # 5. Log predictions (skipping DB write for now — ml.prediction requires
    #    model_version_id + horizon which aren't available in demo mode)
    logger.info(
        "Generated %d predictions for %s using %s",
        len(predictions),
        payload.ticker_id,
        payload.model_name,
    )

    # 6. Format Response
    response = PredictResponse(
        ticker_id=payload.ticker_id,
        model_name=payload.model_name,
        prediction_time=prediction_time,
        predictions=predictions,
    )

    # 7. Save to Redis Cache (expires in 5 minutes)
    redis_cache.set(cache_key, response.dict(), ttl_seconds=300)

    return response


@app.get(
    "/api/v1/models",
    response_model=List[ModelInfoResponse],
    dependencies=[Depends(verify_api_key)],
)
def get_active_models(db: Session = Depends(get_db)):
    """
    Lấy danh sách các mô hình đang hoạt động và chất lượng huấn luyện (metrics) từ MLflow.
    """
    # TODO: Connect to MLflow client to list registered models.
    # client = mlflow.tracking.MlflowClient()
    # models = client.search_registered_models()

    # Mocking active models structure based on the API Contract
    now = now_utc()
    return [
        ModelInfoResponse(
            model_name="arima",
            version="1",
            status="active",
            metrics=ModelMetrics(mae=150.25, rmse=180.40, mape=0.024),
            last_updated=now - timedelta(days=2),
        ),
        ModelInfoResponse(
            model_name="xgboost",
            version="3",
            status="active",
            metrics=ModelMetrics(mae=98.12, rmse=120.34, mape=0.015),
            last_updated=now - timedelta(days=1),
        ),
        ModelInfoResponse(
            model_name="lstm",
            version="2",
            status="staging",
            metrics=ModelMetrics(mae=85.50, rmse=105.10, mape=0.012),
            last_updated=now - timedelta(hours=6),
        ),
    ]
