from sqlalchemy import String, Numeric, DateTime, Date, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from .database import Base


class StockOhlcv(Base):
    __tablename__ = "stock_ohlcv"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)

    candle_time: Mapped[object] = mapped_column(
        DateTime(timezone=False), nullable=False
    )

    open_price: Mapped[object] = mapped_column(Numeric(20, 4), nullable=True)
    high_price: Mapped[object] = mapped_column(Numeric(20, 4), nullable=True)
    low_price: Mapped[object] = mapped_column(Numeric(20, 4), nullable=True)
    close_price: Mapped[object] = mapped_column(Numeric(20, 4), nullable=True)

    volume: Mapped[object] = mapped_column(Numeric(30, 4), nullable=True)

    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "interval",
            "candle_time",
            name="uq_stock_ohlcv_symbol_interval_time",
        ),
        Index(
            "idx_stock_ohlcv_symbol_interval_time", "symbol", "interval", "candle_time"
        ),
    )


class StockRawData(Base):
    __tablename__ = "stock_raw_data"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    symbol: Mapped[str] = mapped_column(String(20), nullable=True)
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=True)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    collected_date: Mapped[object] = mapped_column(Date, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "data_type",
            "period",
            "collected_date",
            name="uq_stock_raw_data_symbol_type_period_date",
        ),
        Index("idx_stock_raw_data_symbol_type", "symbol", "data_type"),
    )
