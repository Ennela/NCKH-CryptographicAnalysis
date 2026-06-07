from sqlalchemy import (
    BigInteger,
    String,
    Numeric,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from .database import Base


class SpotKline(Base):
    __tablename__ = "spot_klines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)

    open_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    close_time: Mapped[int] = mapped_column(BigInteger, nullable=False)

    open_price: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    high_price: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    low_price: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    close_price: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)

    volume: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    quote_asset_volume: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)

    number_of_trades: Mapped[int] = mapped_column(Integer, nullable=False)

    taker_buy_base_asset_volume: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    taker_buy_quote_asset_volume: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)

    ignore_value: Mapped[str] = mapped_column(String(50), nullable=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("symbol", "interval", "open_time", name="uq_spot_klines_symbol_interval_open_time"),
        Index("idx_spot_klines_symbol_interval_time", "symbol", "interval", "open_time"),
    )


class AggTrade(Base):
    __tablename__ = "agg_trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    agg_trade_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    price: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)

    first_trade_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_trade_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    trade_time: Mapped[int] = mapped_column(BigInteger, nullable=False)

    is_buyer_maker: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_best_match: Mapped[bool] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("symbol", "agg_trade_id", name="uq_agg_trades_symbol_agg_trade_id"),
        Index("idx_agg_trades_symbol_time", "symbol", "trade_time"),
    )


class OrderBookSnapshot(Base):
    __tablename__ = "order_book_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    last_update_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    collected_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    levels = relationship("OrderBookLevel", back_populates="snapshot")


class OrderBookLevel(Base):
    __tablename__ = "order_book_levels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    snapshot_id: Mapped[int] = mapped_column(ForeignKey("order_book_snapshots.id"), nullable=False)

    side: Mapped[str] = mapped_column(String(10), nullable=False)  # bid / ask
    price: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    snapshot = relationship("OrderBookSnapshot", back_populates="levels")

    __table_args__ = (
        Index("idx_order_book_levels_snapshot_side", "snapshot_id", "side"),
    )


class RawBinanceData(Base):
    __tablename__ = "raw_binance_data"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    collected_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_raw_binance_endpoint", "endpoint"),
    )