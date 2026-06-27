"""
ORM Models — khớp CHÍNH XÁC ``infra/postgres/init.sql`` (nguồn sự thật).

Quy ước:
- Mỗi model khai báo ``__table_args__ = {"schema": "..."}`` đúng schema.
- Tên bảng, tên cột, kiểu dữ liệu khớp 1:1 với init.sql.
- Enum types dùng ``postgresql.ENUM(name=..., schema=..., create_type=False)``
  vì init.sql đã tạo sẵn — ORM KHÔNG tự tạo lại type.

Bảng hypertable / khối lượng lớn (market.ohlcv_raw, market.ohlcv,
ml.feature_value, ml.prediction, ops.job_log) KHÔNG có ORM model ở đây.
Truy cập bằng SQL thô qua ``sqlalchemy.text()`` hoặc repository pattern.
Xem TODO bên dưới trỏ ``shared/db/repositories/``.

LƯU Ý: Module này KHÔNG gọi ``metadata.create_all()`` ở bất kỳ đâu.
Schema chỉ do ``infra/postgres/init.sql`` + Alembic migrations quản lý.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Enum types — create_type=False vì init.sql đã tạo sẵn                 ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

AssetClassEnum = sa.Enum(
    "stock",
    "crypto",
    name="asset_class",
    schema="market",
    create_type=False,
)

DataSourceEnum = sa.Enum(
    "vnstock",
    "binance",
    "manual",
    name="data_source",
    schema="market",
    create_type=False,
)

TimeframeEnum = sa.Enum(
    "1m",
    "5m",
    "15m",
    "1h",
    "4h",
    "1d",
    "1w",
    name="timeframe",
    schema="market",
    create_type=False,
)

SymbolStatusEnum = sa.Enum(
    "active",
    "delisted",
    "suspended",
    name="symbol_status",
    schema="market",
    create_type=False,
)

ModelFamilyEnum = sa.Enum(
    "arima",
    "regression",
    "xgboost",
    "lstm",
    "gru",
    "transformer",
    "baseline",
    name="model_family",
    schema="ml",
    create_type=False,
)

ModelStageEnum = sa.Enum(
    "dev",
    "staging",
    "production",
    "archived",
    name="model_stage",
    schema="ml",
    create_type=False,
)

TaskTypeEnum = sa.Enum(
    "regression",
    "classification",
    name="task_type",
    schema="ml",
    create_type=False,
)

MetricSplitEnum = sa.Enum(
    "train",
    "val",
    "test",
    "live",
    name="metric_split",
    schema="ml",
    create_type=False,
)

JobTypeEnum = sa.Enum(
    "ingest",
    "clean",
    "feature",
    "train",
    "predict",
    "backtest",
    name="job_type",
    schema="ops",
    create_type=False,
)

JobStatusEnum = sa.Enum(
    "pending",
    "running",
    "success",
    "failed",
    "skipped",
    name="job_status",
    schema="ops",
    create_type=False,
)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Schema: market — bảng lookup (không phải hypertable)                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


class Exchange(Base):
    """market.exchange — Sàn giao dịch (HOSE, BINANCE, …)."""

    __tablename__ = "exchange"
    __table_args__ = {"schema": "market"}

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(sa.String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    asset_class: Mapped[str] = mapped_column(AssetClassEnum, nullable=False)
    timezone: Mapped[str] = mapped_column(
        sa.String(40),
        nullable=False,
        server_default="UTC",
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # Relationships
    symbols: Mapped[list["Symbol"]] = relationship(back_populates="exchange")


class Symbol(Base):
    """market.symbol — Mã chứng khoán / cặp crypto."""

    __tablename__ = "symbol"
    __table_args__ = (
        sa.UniqueConstraint("exchange_id", "ticker", name="uq_symbol_exchange_ticker"),
        {"schema": "market"},
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    exchange_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("market.exchange.id"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    asset_class: Mapped[str] = mapped_column(AssetClassEnum, nullable=False)
    source: Mapped[str] = mapped_column(DataSourceEnum, nullable=False)
    base_asset: Mapped[Optional[str]] = mapped_column(sa.String(20))
    quote_asset: Mapped[Optional[str]] = mapped_column(sa.String(20))
    company_name: Mapped[Optional[str]] = mapped_column(sa.String(255))
    status: Mapped[str] = mapped_column(
        SymbolStatusEnum,
        nullable=False,
        server_default="active",
    )
    listed_date: Mapped[Optional[date]] = mapped_column(sa.Date)
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # Relationships
    exchange: Mapped["Exchange"] = relationship(back_populates="symbols")


# ── Hypertable market tables — KHÔNG có ORM model ───────────────────────
#
# TODO: Tạo shared/db/repositories/ohlcv_repo.py cho:
#   - market.ohlcv_raw  (BIGSERIAL, hypertable — dữ liệu thô từ nguồn)
#   - market.ohlcv      (composite PK, hypertable — dữ liệu sạch)
#
# Truy vấn bằng sqlalchemy.text() hoặc async connection.execute().
# Lý do: hypertable có khối lượng lớn, composite PK phức tạp, TimescaleDB
# compression/continuous aggregate không tương thích tốt với ORM heavy.
# ────────────────────────────────────────────────────────────────────────


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Schema: ml — bảng metadata (không phải hypertable)                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


class FeatureSet(Base):
    """ml.feature_set — Định nghĩa tập đặc trưng."""

    __tablename__ = "feature_set"
    __table_args__ = (
        sa.UniqueConstraint("name", "version", name="uq_feature_set_name_ver"),
        {"schema": "ml"},
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    version: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default="1",
    )
    feature_list: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    description: Mapped[Optional[str]] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


# ── Hypertable: ml.feature_value — KHÔNG có ORM model ──────────────────
#
# TODO: Tạo shared/db/repositories/feature_repo.py cho:
#   - ml.feature_value  (composite PK, hypertable — giá trị feature)
# ────────────────────────────────────────────────────────────────────────


class MLModel(Base):
    """ml.model — Định nghĩa mô hình ML."""

    __tablename__ = "model"
    __table_args__ = {"schema": "ml"}

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False, unique=True)
    family: Mapped[str] = mapped_column(ModelFamilyEnum, nullable=False)
    task: Mapped[str] = mapped_column(
        TaskTypeEnum,
        nullable=False,
        server_default="regression",
    )
    symbol_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        sa.ForeignKey("market.symbol.id"),
    )
    timeframe: Mapped[Optional[str]] = mapped_column(TimeframeEnum)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # Relationships
    versions: Mapped[list["ModelVersion"]] = relationship(back_populates="model")


class ModelVersion(Base):
    """ml.model_version — Phiên bản cụ thể của model."""

    __tablename__ = "model_version"
    __table_args__ = (
        sa.UniqueConstraint("model_id", "version", name="uq_model_version"),
        {"schema": "ml"},
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("ml.model.id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default="1",
    )
    feature_set_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("ml.feature_set.id"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(
        ModelStageEnum,
        nullable=False,
        server_default="dev",
    )
    mlflow_run_id: Mapped[Optional[str]] = mapped_column(sa.String(64))
    artifact_uri: Mapped[Optional[str]] = mapped_column(sa.Text)
    hyperparams: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    train_window: Mapped[Optional[str]] = mapped_column(TSTZRANGE)
    val_window: Mapped[Optional[str]] = mapped_column(TSTZRANGE)
    test_window: Mapped[Optional[str]] = mapped_column(TSTZRANGE)
    random_seed: Mapped[Optional[int]] = mapped_column(sa.Integer)
    framework: Mapped[str] = mapped_column(
        sa.String(30),
        nullable=False,
        server_default="pytorch",
    )
    git_commit: Mapped[Optional[str]] = mapped_column(sa.String(40))
    trained_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # Relationships
    model: Mapped["MLModel"] = relationship(back_populates="versions")
    metrics: Mapped[list["ModelMetric"]] = relationship(
        back_populates="model_version",
    )


class ModelMetric(Base):
    """ml.model_metric — Chỉ số đánh giá model (MAE, RMSE, MAPE…)."""

    __tablename__ = "model_metric"
    __table_args__ = (
        sa.UniqueConstraint(
            "model_version_id",
            "split",
            "metric_name",
            "horizon",
            name="uq_model_metric",
        ),
        {"schema": "ml"},
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    model_version_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("ml.model_version.id"),
        nullable=False,
    )
    split: Mapped[str] = mapped_column(MetricSplitEnum, nullable=False)
    metric_name: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    metric_value: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 8),
        nullable=False,
    )
    horizon: Mapped[Optional[int]] = mapped_column(sa.Integer)
    recorded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # Relationships
    model_version: Mapped["ModelVersion"] = relationship(
        back_populates="metrics",
    )


# ── Hypertable: ml.prediction — KHÔNG có ORM model ─────────────────────
#
# TODO: Tạo shared/db/repositories/prediction_repo.py cho:
#   - ml.prediction  (UUID + target_ts composite PK, hypertable)
#   - Cột abs_error là GENERATED ALWAYS AS (abs(y_pred - y_true)) STORED
#   - CHECK(feature_asof_ts < target_ts) chặn look-ahead bias
# ────────────────────────────────────────────────────────────────────────


class BacktestRun(Base):
    """ml.backtest_run — Phiên backtest."""

    __tablename__ = "backtest_run"
    __table_args__ = {"schema": "ml"}

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    model_version_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("ml.model_version.id"),
        nullable=False,
    )
    period: Mapped[str] = mapped_column(TSTZRANGE, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # Relationships
    results: Mapped[list["BacktestResult"]] = relationship(
        back_populates="backtest_run",
    )


class BacktestResult(Base):
    """ml.backtest_result — Kết quả backtest."""

    __tablename__ = "backtest_result"
    __table_args__ = (
        sa.UniqueConstraint(
            "backtest_run_id",
            "metric_name",
            name="uq_backtest_result",
        ),
        {"schema": "ml"},
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    backtest_run_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("ml.backtest_run.id"),
        nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    metric_value: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 8),
        nullable=False,
    )

    # Relationships
    backtest_run: Mapped["BacktestRun"] = relationship(back_populates="results")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Schema: ops — bảng metadata (không phải hypertable)                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# ── Hypertable: ops.job_log — KHÔNG có ORM model ───────────────────────
#
# TODO: Tạo shared/db/repositories/job_repo.py cho:
#   - ops.job_log  (UUID + started_at composite PK, hypertable)
# ────────────────────────────────────────────────────────────────────────


class DataQualityCheck(Base):
    """ops.data_quality_check — Kết quả kiểm tra chất lượng dữ liệu."""

    __tablename__ = "data_quality_check"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    symbol_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("market.symbol.id"),
        nullable=False,
    )
    timeframe: Mapped[str] = mapped_column(TimeframeEnum, nullable=False)
    check_name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    ts_range: Mapped[str] = mapped_column(TSTZRANGE, nullable=False)
    passed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    checked_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
