"use client";

import { useState, useEffect, useCallback } from "react";
import TechnicalChart from "@/components/chart";
import { Play, Sparkles, Server, Info, Loader2, AlertCircle, BarChart3 } from "lucide-react";
import {
  ApiError,
  fetchSymbols,
  fetchOhlcv,
  fetchPrediction,
  fetchModels,
  timeframeForAssetClass,
  type SymbolInfo,
  type ModelInfo,
  type ModelName,
} from "@/lib/api";

interface ChartCandle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface ChartForecast {
  time: string;
  value: number;
}

const MODEL_METADATA: Record<ModelName, { name: string; type: string }> = {
  arima: { name: "ARIMA Baseline", type: "Statistical" },
  xgboost: { name: "XGBoost Regressor", type: "Machine Learning" },
  random_forest: { name: "Random Forest Regressor", type: "Machine Learning (Ensemble)" },
  gru: { name: "PyTorch GRU", type: "Deep Learning (Recurrent)" },
};

/** Format an ISO timestamp as a compact chart label (adds hour for intraday data). */
function formatChartTime(isoStr: string, timeframe: "1d" | "1h"): string {
  const d = new Date(isoStr);
  const opts: Intl.DateTimeFormatOptions =
    timeframe === "1h"
      ? { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Ho_Chi_Minh" }
      : { year: "2-digit", month: "2-digit", day: "2-digit", timeZone: "Asia/Ho_Chi_Minh" };
  return d.toLocaleString("vi-VN", opts);
}

/** Format a metric value or a placeholder when the backend has no value. */
function formatMetric(val: number | null | undefined, decimals: number = 4): string {
  if (val === null || val === undefined || Number.isNaN(val)) return "—";
  return val.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export default function ForecastPage() {
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [symbolsError, setSymbolsError] = useState<string | null>(null);
  const [ticker, setTicker] = useState<string>("");
  const [modelName, setModelName] = useState<ModelName>("xgboost");
  const [steps, setSteps] = useState(5);

  const [chartHistory, setChartHistory] = useState<ChartCandle[]>([]);
  const [chartForecasts, setChartForecasts] = useState<ChartForecast[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastError, setForecastError] = useState<string | null>(null);

  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState<string | null>(null);

  const selectedSymbol = symbols.find((s) => s.ticker === ticker);
  const timeframe = timeframeForAssetClass(selectedSymbol?.asset_class);

  // Load ticker list once on mount.
  const loadSymbols = useCallback(async () => {
    setSymbolsError(null);
    try {
      const data = await fetchSymbols();
      setSymbols(data);
      if (data.length > 0) {
        setTicker((prev) => (prev && data.some((s) => s.ticker === prev) ? prev : data[0].ticker));
      }
    } catch (err) {
      setSymbolsError(err instanceof Error ? err.message : "Lỗi kết nối API");
    }
  }, []);

  useEffect(() => {
    loadSymbols();
  }, [loadSymbols]);

  // Load registered model metrics for the comparison table.
  const loadModels = useCallback(async () => {
    setModelsLoading(true);
    setModelsError(null);
    try {
      setModels(await fetchModels());
    } catch (err) {
      setModelsError(err instanceof Error ? err.message : "Lỗi kết nối API");
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  // Reload real OHLCV history whenever the selected ticker changes.
  const loadHistory = useCallback(async () => {
    if (!ticker || !selectedSymbol) return;
    setHistoryLoading(true);
    setHistoryError(null);
    setChartForecasts([]);
    setForecastError(null);
    try {
      const rows = await fetchOhlcv(ticker, timeframe, 120);
      // API returns newest-first — reverse to chronological order for charting.
      const chronological = [...rows].reverse();
      setChartHistory(
        chronological.map((c) => ({
          time: formatChartTime(c.ts, timeframe),
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }))
      );
    } catch (err) {
      setChartHistory([]);
      setHistoryError(err instanceof Error ? err.message : "Lỗi kết nối API");
    } finally {
      setHistoryLoading(false);
    }
  }, [ticker, selectedSymbol, timeframe]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleRunForecast = async () => {
    if (!ticker) return;
    setForecastLoading(true);
    setForecastError(null);
    try {
      const result = await fetchPrediction(ticker, modelName, steps, timeframe);
      setChartForecasts(
        result.predictions.map((p) => ({
          time: formatChartTime(p.target_time, timeframe),
          value: p.predicted_value,
        }))
      );
    } catch (err) {
      setChartForecasts([]);
      if (err instanceof ApiError && err.status === 503) {
        setForecastError(
          `Model "${modelName}" chưa được đăng ký trong MLflow Registry — hãy chạy python -m services.training.train_${modelName} trước.`
        );
      } else if (err instanceof ApiError && err.status === 404) {
        setForecastError(`Không tìm thấy mã ${ticker} trong hệ thống. Hãy kiểm tra lại danh sách symbols.`);
      } else if (err instanceof ApiError && err.status === 401) {
        setForecastError("API key không hợp lệ. Kiểm tra biến NEXT_PUBLIC_API_KEY trong .env.local.");
      } else {
        setForecastError(err instanceof Error ? err.message : "Lỗi kết nối API");
      }
    } finally {
      setForecastLoading(false);
    }
  };

  const selectedModelInfo = models.find((m) => m.model_name === modelName);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-200">Dự Báo Chuỗi Thời Gian</h1>
        <p className="text-slate-500 text-sm mt-1">
          Chạy các mô hình Machine Learning / Deep Learning đã đăng ký trong MLflow Registry trên dữ liệu lịch sử thật.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-8">
        {/* Controls Panel */}
        <div className="xl:col-span-1 glass-panel p-6 rounded-xl border border-darkBorder space-y-6">
          <div className="flex items-center gap-2 text-glowIndigo font-semibold">
            <Sparkles className="w-5 h-5" />
            <span>Tham Số Mô Hình</span>
          </div>

          <div className="space-y-4">
            {/* Symbol Selection */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Mã Tài Sản</label>
              {symbolsError ? (
                <div className="text-xs text-glowRose space-y-2">
                  <p>Không tải được danh sách mã: {symbolsError}</p>
                  <button
                    onClick={loadSymbols}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 border border-darkBorder hover:bg-slate-700 transition-all"
                  >
                    Thử lại
                  </button>
                </div>
              ) : (
                <select
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value)}
                  disabled={symbols.length === 0}
                  className="w-full bg-slate-900 border border-darkBorder rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-glowIndigo disabled:text-slate-600"
                >
                  {symbols.length === 0 && <option value="">Đang tải danh sách mã...</option>}
                  {symbols.map((sym) => (
                    <option key={sym.ticker} value={sym.ticker}>
                      {sym.ticker} ({sym.asset_class === "crypto" ? "Crypto" : "Stock VN"})
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Model Selection */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Chọn Mô Hình</label>
              <select
                value={modelName}
                onChange={(e) => setModelName(e.target.value as ModelName)}
                className="w-full bg-slate-900 border border-darkBorder rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-glowIndigo"
              >
                <option value="arima">ARIMA Baseline</option>
                <option value="xgboost">XGBoost Regressor</option>
                <option value="random_forest">Random Forest Regressor</option>
                <option value="gru">GRU (PyTorch Deep Learning)</option>
              </select>
            </div>

            {/* Steps (Slider) */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-semibold text-slate-400 uppercase tracking-wider">
                <span>Số Bước Dự Báo</span>
                <span className="text-glowIndigo font-bold">{steps} bước</span>
              </div>
              <input
                type="range"
                min="1"
                max="30"
                value={steps}
                onChange={(e) => setSteps(parseInt(e.target.value))}
                className="w-full accent-glowIndigo"
              />
              <span className="text-[10px] text-slate-500 block">
                {timeframe === "1h" ? "Khung 1 giờ / bước" : "Khung 1 ngày / bước"}
              </span>
            </div>

            {/* Action button */}
            <button
              onClick={handleRunForecast}
              disabled={forecastLoading || historyLoading || !ticker || chartHistory.length === 0}
              className="w-full py-3 rounded-lg bg-glowIndigo hover:bg-glowIndigo/85 disabled:bg-slate-800 disabled:text-slate-600 transition-all font-bold text-sm text-white flex items-center justify-center gap-2 border border-glowIndigo/20 shadow-lg shadow-glowIndigo/15"
            >
              {forecastLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Đang chạy mô hình...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-white" />
                  <span>Kích Hoạt Dự Báo</span>
                </>
              )}
            </button>

            {/* Forecast error */}
            {forecastError && (
              <div className="p-3 rounded-lg bg-red-500/5 border border-red-500/20 flex gap-2 items-start">
                <AlertCircle className="w-4 h-4 text-glowRose shrink-0 mt-0.5" />
                <div className="text-xs space-y-1.5">
                  <p className="text-glowRose leading-relaxed">{forecastError}</p>
                  <button
                    onClick={handleRunForecast}
                    className="px-3 py-1 rounded bg-slate-800 text-slate-300 border border-darkBorder hover:bg-slate-700 transition-all"
                  >
                    Thử lại
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-darkBorder space-y-3">
            <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold">
              <Info className="w-4 h-4 text-slate-500" />
              <span>Thông Tin Thuật Toán</span>
            </div>

            <div className="bg-slate-900/50 rounded-lg p-3 border border-darkBorder/40 space-y-2 text-xs">
              <div>
                <span className="text-slate-500 block">Tên hiển thị:</span>
                <span className="font-semibold text-slate-300">{MODEL_METADATA[modelName].name}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Phân loại:</span>
                <span className="font-semibold text-slate-300">{MODEL_METADATA[modelName].type}</span>
              </div>
              <div>
                <span className="text-slate-500 block">MAPE (tập test):</span>
                <span className="font-semibold text-glowEmerald">
                  {selectedModelInfo ? `${formatMetric(selectedModelInfo.metrics.mape, 2)}%` : "Chưa có dữ liệu đánh giá"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Chart View */}
        <div className="xl:col-span-3 space-y-6">
          {historyLoading ? (
            <div className="glass-card rounded-xl border border-darkBorder p-6 h-[520px] flex flex-col items-center justify-center gap-3">
              <Loader2 className="w-8 h-8 text-glowIndigo animate-spin" />
              <span className="text-slate-400 text-sm">Đang tải dữ liệu lịch sử {ticker}...</span>
            </div>
          ) : historyError ? (
            <div className="glass-card rounded-xl border border-red-500/20 p-6 h-[520px] flex flex-col items-center justify-center gap-3">
              <AlertCircle className="w-8 h-8 text-glowRose" />
              <span className="text-glowRose font-semibold text-sm">Không thể tải dữ liệu lịch sử</span>
              <span className="text-slate-500 text-xs text-center max-w-md">{historyError}</span>
              <button
                onClick={loadHistory}
                className="mt-2 px-4 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs border border-darkBorder hover:bg-slate-700 transition-all"
              >
                Thử lại
              </button>
            </div>
          ) : chartHistory.length === 0 ? (
            <div className="glass-card rounded-xl border border-darkBorder p-6 h-[520px] flex flex-col items-center justify-center gap-3">
              <BarChart3 className="w-8 h-8 text-slate-600" />
              <span className="text-slate-500 text-sm">
                {ticker ? `Chưa có dữ liệu OHLCV cho mã ${ticker}.` : "Chưa chọn mã tài sản."}
              </span>
              <span className="text-slate-600 text-xs">Hãy chạy ingestion service để thu thập dữ liệu.</span>
            </div>
          ) : (
            <TechnicalChart symbol={ticker} history={chartHistory} forecasts={chartForecasts} />
          )}

          {/* Model Metrics Table */}
          <div className="glass-panel rounded-xl border border-darkBorder overflow-hidden">
            <div className="py-4 px-6 border-b border-darkBorder flex justify-between items-center">
              <h3 className="text-sm font-bold tracking-tight text-slate-300">Mô Hình Đã Đăng Ký (MLflow Registry)</h3>
              {modelsError && (
                <button
                  onClick={loadModels}
                  className="text-xs px-3 py-1 rounded bg-slate-800 text-slate-300 border border-darkBorder hover:bg-slate-700 transition-all"
                >
                  Thử lại
                </button>
              )}
            </div>
            {modelsLoading ? (
              <div className="p-8 flex items-center justify-center gap-2 text-slate-500 text-sm">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Đang tải danh sách mô hình...</span>
              </div>
            ) : modelsError ? (
              <div className="p-8 flex flex-col items-center gap-2">
                <AlertCircle className="w-6 h-6 text-glowRose" />
                <span className="text-glowRose text-sm font-semibold">Không thể tải danh sách mô hình</span>
                <span className="text-slate-500 text-xs">{modelsError}</span>
              </div>
            ) : models.length === 0 ? (
              <div className="p-8 flex flex-col items-center gap-2 text-center">
                <Server className="w-6 h-6 text-slate-600" />
                <span className="text-slate-500 text-sm">Chưa có mô hình nào được đăng ký trong MLflow Registry.</span>
                <span className="text-slate-600 text-xs">
                  Chạy các entrypoint train (python -m services.training.train_&lt;model&gt;) để đăng ký mô hình.
                </span>
              </div>
            ) : (
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-darkBorder bg-slate-900/40 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                    <th className="py-3 px-6">Mô Hình</th>
                    <th className="py-3 px-6">Phiên Bản</th>
                    <th className="py-3 px-6">Trạng Thái</th>
                    <th className="py-3 px-6 text-right">MAE</th>
                    <th className="py-3 px-6 text-right">RMSE</th>
                    <th className="py-3 px-6 text-right">MAPE (%)</th>
                    <th className="py-3 px-6 text-right">Cập Nhật</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-darkBorder/40">
                  {models.map((m) => (
                    <tr key={`${m.model_name}-${m.version}`} className="hover:bg-slate-800/25 transition-all text-sm text-slate-300">
                      <td className="py-3 px-6 font-bold text-glowIndigo">{m.model_name}</td>
                      <td className="py-3 px-6 text-slate-400">v{m.version}</td>
                      <td className="py-3 px-6">
                        <span className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-emerald-500/10 text-glowEmerald border border-emerald-500/20">
                          {m.status}
                        </span>
                      </td>
                      <td className="py-3 px-6 text-right font-mono text-xs">{formatMetric(m.metrics.mae)}</td>
                      <td className="py-3 px-6 text-right font-mono text-xs">{formatMetric(m.metrics.rmse)}</td>
                      <td className="py-3 px-6 text-right font-mono text-xs text-glowEmerald">{formatMetric(m.metrics.mape, 2)}</td>
                      <td className="py-3 px-6 text-right text-xs text-slate-500">
                        {m.last_updated ? new Date(m.last_updated).toLocaleDateString("vi-VN") : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="glass-panel p-4 rounded-xl border border-darkBorder flex items-center gap-3">
            <div className="p-2 rounded bg-glowIndigo/10 text-glowIndigo border border-glowIndigo/20">
              <Server className="w-5 h-5" />
            </div>
            <div className="text-xs">
              <span className="font-semibold block text-slate-300">Kết nối MLflow Registry / Redis Cache</span>
              <p className="text-slate-500">
                Dự báo được phục vụ bởi inference service; mô hình tải từ MLflow Registry và được cache trên Redis.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}