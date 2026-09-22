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

export interface ModelInfo {
  model_name: string;
  version: string;
  status: string;
  metrics: {
    mae: number | null;
    rmse: number | null;
    mape: number | null;
  };
  last_updated: string | null;
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

/** Derive the ingestion timeframe from an asset class (crypto→1h, stock→1d). */
export function timeframeForAssetClass(assetClass: string | undefined): Timeframe {
  return assetClass === "crypto" ? "1h" : "1d";
}
