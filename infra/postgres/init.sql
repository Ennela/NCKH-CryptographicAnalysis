-- =============================================================================
-- init.sql — NGUỒN SỰ THẬT schema cho hệ thống dự báo giá cổ phiếu & crypto
-- Target: timescale/timescaledb:latest-pg15  (tương thích pg16)
-- Idempotent: mọi lệnh dùng IF NOT EXISTS / DO $$ ... $$
-- =============================================================================

-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  0. EXTENSIONS                                                          ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  1. SCHEMAS                                                             ║
-- ║  market — dữ liệu thị trường (exchange, symbol, OHLCV)                 ║
-- ║  ml     — mô hình, đặc trưng, dự báo, backtest                         ║
-- ║  ops    — vận hành (job log, kiểm tra chất lượng dữ liệu)              ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS ml;
CREATE SCHEMA IF NOT EXISTS ops;

-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  2. ENUM TYPES                                                          ║
-- ║  Dùng DO $$ để tạo idempotent (IF NOT EXISTS cho TYPE chỉ có từ pg11+) ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- ---------- market enums ----------

DO $$ BEGIN
    CREATE TYPE market.asset_class AS ENUM ('stock', 'crypto');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE market.data_source AS ENUM ('vnstock', 'binance', 'manual');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE market.timeframe AS ENUM ('1m', '5m', '15m', '1h', '4h', '1d', '1w');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE market.symbol_status AS ENUM ('active', 'delisted', 'suspended');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ---------- ml enums ----------

DO $$ BEGIN
    CREATE TYPE ml.model_family AS ENUM (
        'arima', 'regression', 'xgboost', 'lstm', 'gru', 'transformer', 'baseline'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE ml.model_stage AS ENUM ('dev', 'staging', 'production', 'archived');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE ml.task_type AS ENUM ('regression', 'classification');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE ml.metric_split AS ENUM ('train', 'val', 'test', 'live');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ---------- ops enums ----------

DO $$ BEGIN
    CREATE TYPE ops.job_type AS ENUM (
        'ingest', 'clean', 'feature', 'train', 'predict', 'backtest'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE ops.job_status AS ENUM (
        'pending', 'running', 'success', 'failed', 'skipped'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  3. BẢNG SCHEMA market — Dữ liệu thị trường                            ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- ---------- 3.1 market.exchange — Sàn giao dịch ----------

CREATE TABLE IF NOT EXISTS market.exchange (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(20)  NOT NULL UNIQUE,          -- VD: HOSE, BINANCE
    name        VARCHAR(120) NOT NULL,
    asset_class market.asset_class NOT NULL,
    timezone    VARCHAR(40)  NOT NULL DEFAULT 'UTC',   -- VD: Asia/Ho_Chi_Minh
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE market.exchange IS 'Danh sách sàn giao dịch (HOSE, HNX, BINANCE, …)';

-- ---------- 3.2 market.symbol — Mã chứng khoán / cặp crypto ----------

CREATE TABLE IF NOT EXISTS market.symbol (
    id            SERIAL PRIMARY KEY,
    exchange_id   INT                  NOT NULL REFERENCES market.exchange(id),
    ticker        VARCHAR(30)          NOT NULL,       -- VD: FPT, BTCUSDT
    asset_class   market.asset_class   NOT NULL,
    source        market.data_source   NOT NULL,
    base_asset    VARCHAR(20),                         -- VD: BTC  (NULL cho stock)
    quote_asset   VARCHAR(20),                         -- VD: USDT (NULL cho stock)
    company_name  VARCHAR(255),
    status        market.symbol_status NOT NULL DEFAULT 'active',
    listed_date   DATE,
    metadata      JSONB                NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ          NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ          NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_symbol_exchange_ticker UNIQUE (exchange_id, ticker)
);

COMMENT ON TABLE market.symbol IS 'Mã chứng khoán (FPT, VNM…) và cặp crypto (BTCUSDT…)';

-- Index GIN trigram cho tìm kiếm gần đúng theo ticker
CREATE INDEX IF NOT EXISTS idx_symbol_ticker_trgm
    ON market.symbol USING gin (ticker gin_trgm_ops);

-- ---------- 3.3 market.ohlcv_raw — Dữ liệu thô từ nguồn ----------
-- Lưu nguyên bản dữ liệu thu thập, phục vụ audit & replay.

CREATE TABLE IF NOT EXISTS market.ohlcv_raw (
    id           BIGSERIAL,
    symbol_id    INT                NOT NULL REFERENCES market.symbol(id),
    timeframe    market.timeframe   NOT NULL,
    ts           TIMESTAMPTZ        NOT NULL,        -- mốc thời gian nến
    open         NUMERIC(20, 8)     NOT NULL,
    high         NUMERIC(20, 8)     NOT NULL,
    low          NUMERIC(20, 8)     NOT NULL,
    close        NUMERIC(20, 8)     NOT NULL,
    volume       NUMERIC(30, 8)     NOT NULL,
    source       market.data_source NOT NULL,
    ingested_at  TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    raw_payload  JSONB,

    PRIMARY KEY (id),
    CONSTRAINT uq_ohlcv_raw UNIQUE (symbol_id, timeframe, ts, source)
);

COMMENT ON TABLE market.ohlcv_raw IS 'Dữ liệu OHLCV thô — giữ nguyên bản từ nguồn, dùng để audit';

-- ---------- 3.4 market.ohlcv — Dữ liệu OHLCV sạch (hypertable) ----------
-- Bảng chính cho mọi truy vấn phân tích & tính feature.

CREATE TABLE IF NOT EXISTS market.ohlcv (
    symbol_id    INT              NOT NULL REFERENCES market.symbol(id),
    timeframe    market.timeframe NOT NULL,
    ts           TIMESTAMPTZ      NOT NULL,
    open         NUMERIC(20, 8)   NOT NULL,
    high         NUMERIC(20, 8)   NOT NULL,
    low          NUMERIC(20, 8)   NOT NULL,
    close        NUMERIC(20, 8)   NOT NULL,
    volume       NUMERIC(30, 8)   NOT NULL,
    vwap         NUMERIC(20, 8),
    trade_count  INT,
    updated_at   TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    PRIMARY KEY (symbol_id, timeframe, ts),

    -- Ràng buộc dữ liệu: high >= low, giá & volume >= 0
    CONSTRAINT chk_ohlcv_high_low    CHECK (high >= low),
    CONSTRAINT chk_ohlcv_open_gte0   CHECK (open  >= 0),
    CONSTRAINT chk_ohlcv_close_gte0  CHECK (close >= 0),
    CONSTRAINT chk_ohlcv_volume_gte0 CHECK (volume >= 0)
);

COMMENT ON TABLE market.ohlcv IS 'Dữ liệu OHLCV đã làm sạch — hypertable phân mảnh theo ts';

-- Chuyển thành hypertable, chunk 7 ngày
SELECT create_hypertable(
    'market.ohlcv', 'ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

-- Index chính cho truy vấn theo symbol + timeframe + thời gian giảm dần
CREATE INDEX IF NOT EXISTS idx_ohlcv_sym_tf_ts
    ON market.ohlcv (symbol_id, timeframe, ts DESC);

-- ---------- 3.5 Continuous Aggregate — Gộp 1h → 1 ngày ----------

CREATE MATERIALIZED VIEW IF NOT EXISTS market.ohlcv_1d_cagg
WITH (timescaledb.continuous) AS
SELECT
    symbol_id,
    time_bucket('1 day', ts)    AS bucket,
    first(open,  ts)            AS open,
    max(high)                   AS high,
    min(low)                    AS low,
    last(close, ts)             AS close,
    sum(volume)                 AS volume
FROM market.ohlcv
WHERE timeframe = '1h'
GROUP BY symbol_id, time_bucket('1 day', ts)
WITH NO DATA;

-- Policy tự động refresh: dữ liệu từ 3 ngày trước đến 1 giờ trước
SELECT add_continuous_aggregate_policy(
    'market.ohlcv_1d_cagg',
    start_offset  => INTERVAL '3 days',
    end_offset    => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  4. BẢNG SCHEMA ml — Mô hình, đặc trưng, dự báo                        ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- ---------- 4.1 ml.feature_set — Định nghĩa tập đặc trưng ----------

CREATE TABLE IF NOT EXISTS ml.feature_set (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(120)  NOT NULL,               -- VD: ta_basic_v1
    version       INT           NOT NULL DEFAULT 1,
    feature_list  JSONB         NOT NULL DEFAULT '[]',   -- ["rsi_14","macd","returns_5d"]
    params        JSONB         NOT NULL DEFAULT '{}',   -- tham số tính feature
    description   TEXT,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_feature_set_name_ver UNIQUE (name, version)
);

COMMENT ON TABLE ml.feature_set IS 'Định nghĩa tập đặc trưng dùng cho training (tên + phiên bản)';

-- ---------- 4.2 ml.feature_value — Giá trị feature theo thời gian ----------

CREATE TABLE IF NOT EXISTS ml.feature_value (
    feature_set_id INT              NOT NULL REFERENCES ml.feature_set(id),
    symbol_id      INT              NOT NULL REFERENCES market.symbol(id),
    timeframe      market.timeframe NOT NULL,
    ts             TIMESTAMPTZ      NOT NULL,
    features       JSONB            NOT NULL DEFAULT '{}',   -- {"rsi_14": 55.3, "macd": 0.12}
    label          NUMERIC(20, 8),                           -- target (giá close T+1, returns…)

    PRIMARY KEY (feature_set_id, symbol_id, timeframe, ts)
);

COMMENT ON TABLE ml.feature_value IS 'Giá trị feature đã tính — hypertable phân mảnh theo ts';

SELECT create_hypertable(
    'ml.feature_value', 'ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

-- ---------- 4.3 ml.model — Định nghĩa mô hình ----------

CREATE TABLE IF NOT EXISTS ml.model (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(120)     NOT NULL UNIQUE,       -- VD: lstm_fpt_1d
    family     ml.model_family  NOT NULL,
    task       ml.task_type     NOT NULL DEFAULT 'regression',
    symbol_id  INT              REFERENCES market.symbol(id),  -- NULL = all symbols
    timeframe  market.timeframe,
    created_at TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ml.model IS 'Khai báo mô hình ML (tên, họ, loại bài toán)';

-- ---------- 4.4 ml.model_version — Phiên bản mô hình ----------

CREATE TABLE IF NOT EXISTS ml.model_version (
    id              SERIAL PRIMARY KEY,
    model_id        INT           NOT NULL REFERENCES ml.model(id),
    version         INT           NOT NULL DEFAULT 1,
    feature_set_id  INT           NOT NULL REFERENCES ml.feature_set(id),
    stage           ml.model_stage NOT NULL DEFAULT 'dev',
    mlflow_run_id   VARCHAR(64),
    artifact_uri    TEXT,
    hyperparams     JSONB         NOT NULL DEFAULT '{}',
    train_window    TSTZRANGE,
    val_window      TSTZRANGE,
    test_window     TSTZRANGE,
    random_seed     INT,
    framework       VARCHAR(30)   NOT NULL DEFAULT 'pytorch',
    git_commit      VARCHAR(40),
    trained_at      TIMESTAMPTZ,
    is_active       BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_model_version UNIQUE (model_id, version)
);

COMMENT ON TABLE ml.model_version
    IS 'Phiên bản cụ thể của model — lưu hyperparams, windows, MLflow run';

-- Partial unique index: chỉ 1 version active per model
CREATE UNIQUE INDEX IF NOT EXISTS idx_model_version_active
    ON ml.model_version (model_id) WHERE is_active = TRUE;

-- ---------- 4.5 ml.model_metric — Chỉ số đánh giá ----------

CREATE TABLE IF NOT EXISTS ml.model_metric (
    id                SERIAL PRIMARY KEY,
    model_version_id  INT              NOT NULL REFERENCES ml.model_version(id),
    split             ml.metric_split  NOT NULL,
    metric_name       VARCHAR(30)      NOT NULL,       -- VD: rmse, mae, mape
    metric_value      NUMERIC(20, 8)   NOT NULL,
    horizon           INT,                             -- bước dự báo (1, 5, 10…)
    recorded_at       TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_model_metric UNIQUE (model_version_id, split, metric_name, horizon)
);

COMMENT ON TABLE ml.model_metric IS 'Chỉ số đánh giá model (MAE, RMSE, MAPE…) theo split';

-- ---------- 4.6 ml.prediction — Dự báo (hypertable) ----------
-- CHECK(feature_asof_ts < target_ts) chặn look-ahead bias.

CREATE TABLE IF NOT EXISTS ml.prediction (
    id                UUID             NOT NULL DEFAULT uuid_generate_v4(),
    model_version_id  INT              NOT NULL REFERENCES ml.model_version(id),
    symbol_id         INT              NOT NULL REFERENCES market.symbol(id),
    feature_asof_ts   TIMESTAMPTZ      NOT NULL,       -- thời điểm cuối cùng feature được tính
    target_ts         TIMESTAMPTZ      NOT NULL,       -- thời điểm mục tiêu dự báo
    horizon           INT              NOT NULL,       -- bước dự báo
    y_pred            NUMERIC(20, 8)   NOT NULL,
    y_pred_lower      NUMERIC(20, 8),                  -- khoảng tin cậy dưới
    y_pred_upper      NUMERIC(20, 8),                  -- khoảng tin cậy trên
    y_true            NUMERIC(20, 8),                  -- giá trị thực (backfill sau)
    abs_error         NUMERIC(20, 8)   GENERATED ALWAYS AS (abs(y_pred - y_true)) STORED,
    created_at        TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id, target_ts),

    CONSTRAINT chk_prediction_no_lookahead CHECK (feature_asof_ts < target_ts),
    CONSTRAINT uq_prediction UNIQUE (model_version_id, symbol_id, target_ts, horizon, feature_asof_ts)
);

COMMENT ON TABLE ml.prediction
    IS 'Kết quả dự báo — hypertable theo target_ts, có CHECK chống look-ahead';

SELECT create_hypertable(
    'ml.prediction', 'target_ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

-- ---------- 4.7 ml.backtest_run & ml.backtest_result ----------

CREATE TABLE IF NOT EXISTS ml.backtest_run (
    id                SERIAL PRIMARY KEY,
    model_version_id  INT         NOT NULL REFERENCES ml.model_version(id),
    period            TSTZRANGE   NOT NULL,            -- khoảng thời gian backtest
    params            JSONB       NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ml.backtest_run IS 'Phiên backtest — lưu khoảng thời gian và tham số';

CREATE TABLE IF NOT EXISTS ml.backtest_result (
    id               SERIAL PRIMARY KEY,
    backtest_run_id  INT            NOT NULL REFERENCES ml.backtest_run(id),
    metric_name      VARCHAR(30)    NOT NULL,
    metric_value     NUMERIC(20, 8) NOT NULL,

    CONSTRAINT uq_backtest_result UNIQUE (backtest_run_id, metric_name)
);

COMMENT ON TABLE ml.backtest_result IS 'Kết quả backtest — metric tổng hợp cho mỗi phiên';


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  5. BẢNG SCHEMA ops — Vận hành hệ thống                                ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- ---------- 5.1 ops.job_log — Log tác vụ Celery (hypertable) ----------

CREATE TABLE IF NOT EXISTS ops.job_log (
    id              UUID           NOT NULL DEFAULT uuid_generate_v4(),
    job_type        ops.job_type   NOT NULL,
    job_name        VARCHAR(120)   NOT NULL,
    status          ops.job_status NOT NULL DEFAULT 'pending',
    symbol_id       INT            REFERENCES market.symbol(id),
    timeframe       market.timeframe,
    started_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    duration_ms     INT,
    rows_affected   INT,
    celery_task_id  VARCHAR(64),
    error_message   TEXT,
    context         JSONB          NOT NULL DEFAULT '{}',

    PRIMARY KEY (id, started_at)
);

COMMENT ON TABLE ops.job_log IS 'Log chạy tác vụ (ingest, train, predict…) — hypertable';

SELECT create_hypertable(
    'ops.job_log', 'started_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

-- ---------- 5.2 ops.data_quality_check — Kiểm tra chất lượng dữ liệu ----------

CREATE TABLE IF NOT EXISTS ops.data_quality_check (
    id           SERIAL PRIMARY KEY,
    symbol_id    INT              NOT NULL REFERENCES market.symbol(id),
    timeframe    market.timeframe NOT NULL,
    check_name   VARCHAR(80)      NOT NULL,           -- VD: missing_candles, spike_check
    ts_range     TSTZRANGE        NOT NULL,
    passed       BOOLEAN          NOT NULL,
    detail       JSONB            NOT NULL DEFAULT '{}',
    checked_at   TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ops.data_quality_check
    IS 'Kết quả kiểm tra chất lượng dữ liệu (thiếu nến, spike, …)';


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  6. COMPRESSION & RETENTION POLICIES                                    ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- Nén market.ohlcv sau 90 ngày
ALTER TABLE market.ohlcv SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol_id, timeframe',
    timescaledb.compress_orderby   = 'ts DESC'
);
SELECT add_compression_policy('market.ohlcv', INTERVAL '90 days', if_not_exists => TRUE);

-- Nén ml.prediction sau 60 ngày
ALTER TABLE ml.prediction SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'model_version_id, symbol_id',
    timescaledb.compress_orderby   = 'target_ts DESC'
);
SELECT add_compression_policy('ml.prediction', INTERVAL '60 days', if_not_exists => TRUE);

-- Nén ops.job_log sau 30 ngày + xóa sau 365 ngày
ALTER TABLE ops.job_log SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'job_type, status',
    timescaledb.compress_orderby   = 'started_at DESC'
);
SELECT add_compression_policy('ops.job_log', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('ops.job_log',   INTERVAL '365 days', if_not_exists => TRUE);


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  7. TRIGGER — Tự động cập nhật updated_at                               ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger cho market.symbol
DO $$ BEGIN
    CREATE TRIGGER trg_symbol_updated_at
        BEFORE UPDATE ON market.symbol
        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Trigger cho market.ohlcv
DO $$ BEGIN
    CREATE TRIGGER trg_ohlcv_updated_at
        BEFORE UPDATE ON market.ohlcv
        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  8. VIEWS                                                               ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- ---------- 8.1 market.v_latest_ohlcv — Giá đóng cửa mới nhất ----------

CREATE OR REPLACE VIEW market.v_latest_ohlcv AS
SELECT DISTINCT ON (s.id, o.timeframe)
    s.id          AS symbol_id,
    s.ticker,
    e.code        AS exchange_code,
    o.timeframe,
    o.ts,
    o.open,
    o.high,
    o.low,
    o.close,
    o.volume,
    o.vwap
FROM market.ohlcv o
JOIN market.symbol s   ON s.id = o.symbol_id
JOIN market.exchange e ON e.id = s.exchange_id
ORDER BY s.id, o.timeframe, o.ts DESC;

COMMENT ON VIEW market.v_latest_ohlcv IS 'Nến OHLCV mới nhất cho mỗi symbol & timeframe';

-- ---------- 8.2 ml.v_latest_prediction — Dự báo mới nhất ----------

CREATE OR REPLACE VIEW ml.v_latest_prediction AS
SELECT DISTINCT ON (p.model_version_id, p.symbol_id)
    p.model_version_id,
    m.name           AS model_name,
    mv.version       AS model_version,
    s.ticker,
    p.target_ts,
    p.horizon,
    p.y_pred,
    p.y_pred_lower,
    p.y_pred_upper,
    p.y_true,
    p.abs_error,
    p.created_at
FROM ml.prediction p
JOIN ml.model_version mv ON mv.id = p.model_version_id
JOIN ml.model m          ON m.id  = mv.model_id
JOIN market.symbol s     ON s.id  = p.symbol_id
ORDER BY p.model_version_id, p.symbol_id, p.target_ts DESC;

COMMENT ON VIEW ml.v_latest_prediction IS 'Dự báo mới nhất cho mỗi model_version & symbol';

-- ---------- 8.3 ml.v_model_leaderboard — Bảng xếp hạng model ----------
-- Sắp xếp theo RMSE trên tập test tăng dần (model tốt nhất trước).

CREATE OR REPLACE VIEW ml.v_model_leaderboard AS
SELECT
    m.name            AS model_name,
    mv.version,
    m.family,
    mv.stage,
    mv.framework,
    mm.metric_value   AS rmse_test,
    mv.trained_at,
    mv.is_active
FROM ml.model_metric mm
JOIN ml.model_version mv ON mv.id = mm.model_version_id
JOIN ml.model m          ON m.id  = mv.model_id
WHERE mm.split       = 'test'
  AND mm.metric_name = 'rmse'
ORDER BY mm.metric_value ASC;

COMMENT ON VIEW ml.v_model_leaderboard
    IS 'Bảng xếp hạng model theo RMSE test (thấp nhất = tốt nhất)';


-- ╔═══════════════════════════════════════════════════════════════════════════╗
-- ║  9. SEED DATA — Dữ liệu khởi tạo                                       ║
-- ╚═══════════════════════════════════════════════════════════════════════════╝

-- Sàn giao dịch
INSERT INTO market.exchange (code, name, asset_class, timezone)
VALUES
    ('HOSE',    'Sở Giao dịch Chứng khoán TP.HCM',  'stock',  'Asia/Ho_Chi_Minh'),
    ('BINANCE', 'Binance Cryptocurrency Exchange',     'crypto', 'UTC')
ON CONFLICT (code) DO NOTHING;

-- Mã chứng khoán & cặp crypto mẫu
INSERT INTO market.symbol (exchange_id, ticker, asset_class, source, company_name, status)
VALUES
    (
        (SELECT id FROM market.exchange WHERE code = 'HOSE'),
        'FPT',
        'stock',
        'vnstock',
        'Công ty Cổ phần FPT',
        'active'
    ),
    (
        (SELECT id FROM market.exchange WHERE code = 'BINANCE'),
        'BTCUSDT',
        'crypto',
        'binance',
        NULL,
        'active'
    )
ON CONFLICT (exchange_id, ticker) DO NOTHING;

-- Cập nhật base_asset / quote_asset cho cặp crypto
UPDATE market.symbol
SET base_asset  = 'BTC',
    quote_asset = 'USDT'
WHERE ticker = 'BTCUSDT'
  AND base_asset IS NULL;

-- =============================================================================
-- Hoàn tất khởi tạo schema.
-- =============================================================================
