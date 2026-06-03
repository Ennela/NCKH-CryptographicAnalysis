from datetime import datetime
from typing import List, Optional
import uuid
from sqlalchemy import String, Numeric, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.db.base import Base

class Ticker(Base):
    __tablename__ = "tickers"
    
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)  # stock / crypto
    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    ohlcv_prices: Mapped[List["OHLCVPrice"]] = relationship(back_populates="ticker", cascade="all, delete-orphan")
    features: Mapped[List["Feature"]] = relationship(back_populates="ticker", cascade="all, delete-orphan")
    predictions: Mapped[List["Prediction"]] = relationship(back_populates="ticker", cascade="all, delete-orphan")

class OHLCVPrice(Base):
    __tablename__ = "ohlcv_prices"
    __table_args__ = {"schema": "raw"}

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    ticker_id: Mapped[str] = mapped_column(String(50), ForeignKey("tickers.id", ondelete="CASCADE"), primary_key=True)
    resolution: Mapped[str] = mapped_column(String(5), primary_key=True)  # 1h / 1d
    open: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)

    # Relationship
    ticker: Mapped["Ticker"] = relationship(back_populates="ohlcv_prices")

class Feature(Base):
    __tablename__ = "features"
    __table_args__ = {"schema": "processed"}

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    ticker_id: Mapped[str] = mapped_column(String(50), ForeignKey("tickers.id", ondelete="CASCADE"), primary_key=True)
    resolution: Mapped[str] = mapped_column(String(5), primary_key=True)
    returns: Mapped[Optional[float]] = mapped_column(Numeric(10, 8))
    rsi: Mapped[Optional[float]] = mapped_column(Numeric(6, 3))
    macd: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    macd_signal: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    volatility: Mapped[Optional[float]] = mapped_column(Numeric(10, 8))

    # Relationship
    ticker: Mapped["Ticker"] = relationship(back_populates="features")

class Prediction(Base):
    __tablename__ = "predictions"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker_id: Mapped[str] = mapped_column(String(50), ForeignKey("tickers.id", ondelete="CASCADE"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prediction_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    predicted_value: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    actual_value: Mapped[Optional[float]] = mapped_column(Numeric(18, 8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationship
    ticker: Mapped["Ticker"] = relationship(back_populates="predictions")
