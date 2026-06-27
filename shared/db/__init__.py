"""
shared.db — Database layer dùng chung cho mọi service.

Import nhanh::

    from shared.db import Base, get_async_session, get_db
    from shared.db import Exchange, Symbol, MLModel

Bảng hypertable (market.ohlcv, ml.prediction, ops.job_log, …) KHÔNG có
ORM model — truy cập qua repository pattern:

    from shared.db.repositories.market_repo import upsert_ohlcv, ensure_symbol
    from shared.db.mappers import map_binance_klines_batch
"""

from shared.db.base import Base
from shared.db.session import (
    AsyncSessionLocal,
    SessionLocal,
    SyncSessionLocal,
    async_engine,
    engine,
    get_async_session,
    get_db,
    sync_engine,
)
from shared.db.models import (
    BacktestResult,
    BacktestRun,
    DataQualityCheck,
    Exchange,
    FeatureSet,
    MLModel,
    ModelMetric,
    ModelVersion,
    Symbol,
)

__all__ = [
    # Base
    "Base",
    # Engines
    "async_engine",
    "sync_engine",
    "engine",
    # Session factories
    "AsyncSessionLocal",
    "SyncSessionLocal",
    "SessionLocal",
    # Dependencies
    "get_async_session",
    "get_db",
    # Models — market (lookup)
    "Exchange",
    "Symbol",
    # Models — ml (metadata)
    "FeatureSet",
    "MLModel",
    "ModelVersion",
    "ModelMetric",
    "BacktestRun",
    "BacktestResult",
    # Models — ops (metadata)
    "DataQualityCheck",
]
