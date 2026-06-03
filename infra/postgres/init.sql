-- ==============================================================================
-- TimescaleDB Initialization Script
-- ==============================================================================

-- 1. Kích hoạt extension TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- 2. Tạo các schema raw và processed
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS processed;

-- 3. Tạo bảng tickers trong public schema (Dữ liệu chung)
CREATE TABLE IF NOT EXISTS public.tickers (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    asset_type VARCHAR(20) NOT NULL CHECK (asset_type IN ('stock', 'crypto')),
    exchange VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tạo bảng ohlcv_prices trong raw schema (Dữ liệu thô từ APIs)
CREATE TABLE IF NOT EXISTS raw.ohlcv_prices (
    timestamp TIMESTAMPTZ NOT NULL,
    ticker_id VARCHAR(50) NOT NULL REFERENCES public.tickers(id) ON DELETE CASCADE,
    resolution VARCHAR(5) NOT NULL CHECK (resolution IN ('1h', '1d')),
    open NUMERIC(18, 8) NOT NULL,
    high NUMERIC(18, 8) NOT NULL,
    low NUMERIC(18, 8) NOT NULL,
    close NUMERIC(18, 8) NOT NULL,
    volume NUMERIC(24, 8) NOT NULL,
    PRIMARY KEY (timestamp, ticker_id, resolution)
);

-- Chuyển đổi ohlcv_prices thành hypertable phân mảnh theo timestamp (mỗi mảnh 7 ngày)
SELECT create_hypertable('raw.ohlcv_prices', 'timestamp', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);

-- 5. Tạo bảng features trong processed schema (Đặc trưng phục vụ training)
CREATE TABLE IF NOT EXISTS processed.features (
    timestamp TIMESTAMPTZ NOT NULL,
    ticker_id VARCHAR(50) NOT NULL REFERENCES public.tickers(id) ON DELETE CASCADE,
    resolution VARCHAR(5) NOT NULL,
    returns NUMERIC(10, 8),
    rsi NUMERIC(6, 3),
    macd NUMERIC(12, 6),
    macd_signal NUMERIC(12, 6),
    volatility NUMERIC(10, 8),
    PRIMARY KEY (timestamp, ticker_id, resolution)
);

-- Chuyển đổi features thành hypertable
SELECT create_hypertable('processed.features', 'timestamp', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);

-- 6. Tạo bảng predictions trong public schema (Lưu lịch sử dự báo để so sánh đánh giá)
CREATE TABLE IF NOT EXISTS public.predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker_id VARCHAR(50) NOT NULL REFERENCES public.tickers(id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,
    prediction_time TIMESTAMPTZ NOT NULL,
    target_time TIMESTAMPTZ NOT NULL,
    predicted_value NUMERIC(18, 8) NOT NULL,
    actual_value NUMERIC(18, 8),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 7. Tạo Index tối ưu hóa truy vấn
CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_time ON raw.ohlcv_prices (ticker_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_features_ticker_time ON processed.features (ticker_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_ticker_time ON public.predictions (ticker_id, target_time DESC);
