/**
 * Typed fetch helpers for the Inference Service API (/api/v1).
 *
 * Base URL and API key are read from NEXT_PUBLIC_API_URL / NEXT_PUBLIC_API_KEY.
 * Every helper throws ApiError (with HTTP status) when the response is not OK,
 * so pages can render honest error states instead of silent fallbacks.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "generate_a_secure_long_random_string_here";

/** Error thrown when the API responds with a non-2xx status. */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface SymbolInfo {
  ticker: string;
  asset_class: string; // "stock" | "crypto"
  exchange_code: string;
  company_name: string | null;
}

export interface CandleRow {
  ts: string; // ISO timestamp
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface PredictionPoint {
  target_time: string;
  predicted_value: number;
}

export interface PredictResponse {
  ticker_id: string;
  model_name: string;
  prediction_time: string;
  predictions: PredictionPoint[];
}

export interface ModelMetrics {
  mae: number;
  rmse: number;
  mape: number;
  /** Naive baseline (y_hat = current close) on the same test split. */
  naive_mae: number | null;
  naive_rmse: number | null;
  naive_mape: number | null;
  directional_accuracy: number | null;
}

export interface ModelInfo {
  /** Registry name, e.g. "ACB_1d_xgboost" (see registryName). */
  model_name: string;
  version: string;
  status: string;
  /** null when the training run did not log MAE/RMSE/MAPE. */
  metrics: ModelMetrics | null;
  last_updated: string | null;
}

export interface SymbolStats {
  ticker: string;
  asset_class: string;
  timeframe: string;
  bars: number;
  first_ts: string;
  last_ts: string;
  lowest_low: number;
  highest_high: number;
  mean_close: number;
  std_close: number | null;
  first_close: number;
  last_close: number;
  change_pct: number | null;
  mean_volume: number;
  max_volume: number;
  return_std_pct: number | null;
}

export interface IndicatorPoint {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma_20: number | null;
  sma_50: number | null;
  rsi_14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
}

export interface IndicatorResponse {
  ticker: string;
  timeframe: string;
  points: IndicatorPoint[];
}

export interface PipelineCheck {
  checked_at: string;
  passed: boolean;
  /** CleaningReport counts; mode = "audit" when replayed without writing bars. */
  detail: {
    input_rows?: number;
    output_rows?: number;
    duplicates_removed?: number;
    missing_filled?: number;
    outliers_flagged?: number;
    mode?: string;
    persisted?: boolean;
  };
}

export interface DataQualityReport {
  ticker: string;
  asset_class: string;
  timeframe: string;
  bars: number;
  first_ts: string | null;
  last_ts: string | null;
  expected_bars: number;
  missing_bars: number;
  completeness_pct: number;
  zero_volume_bars: number;
  invalid_ohlc_bars: number;
  return_outliers: number;
  volume_outliers: number;
  last_pipeline_check: PipelineCheck | null;
}

export interface JobLogEntry {
  job_type: string;
  job_name: string;
  status: string; // pending | running | success | failed | skipped
  ticker: string | null;
  timeframe: string | null;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  rows_affected: number | null;
  error_message: string | null;
}

export interface HealthStatus {
  status: string;
  service: string;
}

export interface ExplainFeature {
  feature: string;
  importance: number;
  mean_abs_shap: number | null;
}

export interface ExplainResponse {
  ticker: string;
  timeframe: string;
  model_name: string;
  method: string;
  features: ExplainFeature[];
  generated_at: string;
}

export type ModelName = "arima" | "xgboost" | "random_forest" | "gru";
export type Timeframe = "1d" | "1h";

/**
 * Perform an authenticated request against the inference API.
 * Throws ApiError with the HTTP status and the backend `detail` message when available.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "X-API-Key": API_KEY,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body — keep the generic HTTP status message.
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as T;
}

/** GET /api/v1/symbols — list of tracked tickers. */
export function fetchSymbols(): Promise<SymbolInfo[]> {
  return request<SymbolInfo[]>("/api/v1/symbols");
}

/** GET /api/v1/ohlcv — candles, newest first (reverse before charting). */
export function fetchOhlcv(ticker: string, timeframe: Timeframe, limit: number): Promise<CandleRow[]> {
  const params = new URLSearchParams({ ticker, timeframe, limit: String(limit) });
  return request<CandleRow[]>(`/api/v1/ohlcv?${params}`);
}

/** POST /api/v1/predict — run a forecast for a ticker with a registered model. */
export function fetchPrediction(
  tickerId: string,
  modelName: ModelName,
  steps: number,
  timeframe?: Timeframe
): Promise<PredictResponse> {
  return request<PredictResponse>("/api/v1/predict", {
    method: "POST",
    body: JSON.stringify({
      ticker_id: tickerId,
      model_name: modelName,
      steps,
      ...(timeframe ? { timeframe } : {}),
    }),
  });
}

/** GET /api/v1/models — registered models with evaluation metrics. */
export function fetchModels(): Promise<ModelInfo[]> {
  return request<ModelInfo[]>("/api/v1/models");
}

/** GET /api/v1/explain — SHAP feature attribution for a trained model. */
export function fetchExplain(ticker: string, timeframe: Timeframe, modelName: ModelName): Promise<ExplainResponse> {
  const params = new URLSearchParams({ ticker, timeframe, model_name: modelName });
  return request<ExplainResponse>(`/api/v1/explain?${params}`);
}

/** GET /api/v1/stats — descriptive statistics of every symbol for a timeframe. */
export function fetchStats(timeframe: Timeframe): Promise<SymbolStats[]> {
  return request<SymbolStats[]>(`/api/v1/stats?${new URLSearchParams({ timeframe })}`);
}

/** GET /api/v1/indicators — chronological candles with SMA/RSI/MACD. */
export function fetchIndicators(ticker: string, timeframe: Timeframe, limit: number): Promise<IndicatorResponse> {
  const params = new URLSearchParams({ ticker, timeframe, limit: String(limit) });
  return request<IndicatorResponse>(`/api/v1/indicators?${params}`);
}

/** GET /api/v1/data-quality — completeness/anomaly profile of every symbol. */
export function fetchDataQuality(timeframe: Timeframe): Promise<DataQualityReport[]> {
  return request<DataQualityReport[]>(`/api/v1/data-quality?${new URLSearchParams({ timeframe })}`);
}

/** GET /api/v1/jobs — most recent ingestion/cleaning jobs (ops.job_log). */
export function fetchJobs(limit: number = 20): Promise<JobLogEntry[]> {
  return request<JobLogEntry[]>(`/api/v1/jobs?${new URLSearchParams({ limit: String(limit) })}`);
}

/** GET /health — liveness of the inference service (no API key needed). */
export function fetchHealth(): Promise<HealthStatus> {
  return request<HealthStatus>("/health");
}

/** Registry name used by every training entrypoint: "<TICKER>_<tf>_<model>". */
export function registryName(ticker: string, timeframe: Timeframe, model: ModelName): string {
  return `${ticker.replace("/", "").toUpperCase()}_${timeframe}_${model}`;
}

/** Default timeframe for an asset class (crypto→1h, stock→1d). */
export function timeframeForAssetClass(assetClass: string | undefined): Timeframe {
  return assetClass === "crypto" ? "1h" : "1d";
}

/** Human-readable message for an API failure, with hints for common statuses. */
export function describeApiError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return "API key không hợp lệ — kiểm tra NEXT_PUBLIC_API_KEY trong .env.local.";
    if (err.status === 503) return `Dịch vụ phụ thuộc chưa sẵn sàng (503): ${err.message}`;
    return `${err.message} (HTTP ${err.status})`;
  }
  if (err instanceof TypeError) return "Không kết nối được Inference API — dịch vụ đã chạy chưa?";
  return err instanceof Error ? err.message : "Lỗi không xác định";
}
