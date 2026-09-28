"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Play } from "lucide-react";
import {
  ApiError,
  describeApiError,
  fetchIndicators,
  fetchModels,
  fetchPrediction,
  registryName,
  type IndicatorPoint,
  type ModelInfo,
  type ModelName,
  type PredictResponse,
  type Timeframe,
} from "@/lib/api";
import { formatAxisTime, formatDate, formatNum, formatPct, formatPrice, timeframeLabel } from "@/lib/format";
import { readIndicators, TONE_CLASS } from "@/lib/insights";
import { useSymbols } from "@/lib/use-symbols";
import ForecastChart, { ForecastLegend } from "@/components/forecast-chart";
import { Badge, Field, FilterBar, MetricRow, PageHeader, Panel, StateBox } from "@/components/ui";

const HISTORY_BARS = 120;
const STEP_OPTIONS = [1, 3, 5, 7, 14, 30];
const MODELS: ModelName[] = ["arima", "xgboost", "random_forest", "gru"];

const MODEL_INFO: Record<ModelName, { name: string; family: string; summary: string; caveat?: string }> = {
  arima: {
    name: "ARIMA",
    family: "Thống kê chuỗi thời gian",
    summary: "Mô hình tự hồi quy tích hợp trung bình trượt ARIMA(1, 1, 1) một biến trên giá đóng cửa; lấy sai phân bậc 1 để khử xu hướng, cập nhật trạng thái cuốn chiếu từng bước.",
  },
  xgboost: {
    name: "XGBoost",
    family: "Học máy — gradient boosting",
    summary: "Tập hợp cây quyết định tăng cường trên 19 đặc trưng kỹ thuật (lag, SMA, độ lệch, RSI, MACD, Bollinger, ATR); siêu tham số tối ưu bằng Optuna.",
    caveat: "Mô hình cây không ngoại suy được ra ngoài vùng giá đã thấy khi huấn luyện.",
  },
  random_forest: {
    name: "Random Forest",
    family: "Học máy — rừng ngẫu nhiên",
    summary: "Trung bình nhiều cây quyết định huấn luyện trên mẫu bootstrap với 18 đặc trưng giá/khối lượng trễ và thống kê cuộn.",
    caveat: "Mô hình cây không ngoại suy được ra ngoài vùng giá đã thấy khi huấn luyện.",
  },
  gru: {
    name: "GRU",
    family: "Học sâu — mạng hồi tiếp (PyTorch)",
    summary: "Mạng GRU đọc chuỗi 8 đặc trưng; đầu ra là phần hiệu chỉnh cộng vào giá đóng cửa gần nhất (residual), khởi tạo đúng bằng baseline Naive.",
  },
};

export default function ForecastPage() {
  const { symbols, ticker, setTicker, selected, error: symbolsError, reload: reloadSymbols } = useSymbols();
  const [modelName, setModelName] = useState<ModelName>("gru");
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");
  const [steps, setSteps] = useState(5);

  const [history, setHistory] = useState<IndicatorPoint[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [forecast, setForecast] = useState<PredictResponse | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);
  const [forecastLoading, setForecastLoading] = useState(false);

  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);

  const assetClass = selected?.asset_class ?? "stock";
  // Only crypto has hourly data; switching to a stock resets the timeframe.
  useEffect(() => {
    if (assetClass !== "crypto") setTimeframe("1d");
  }, [assetClass]);

  const loadHistory = useCallback(async () => {
    if (!ticker) return;
    setHistoryLoading(true);
    setHistoryError(null);
    setForecast(null);
    setForecastError(null);
    try {
      setHistory((await fetchIndicators(ticker, timeframe, HISTORY_BARS)).points);
    } catch (err) {
      setHistory([]);
      setHistoryError(describeApiError(err));
    } finally {
      setHistoryLoading(false);
    }
  }, [ticker, timeframe]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const loadModels = useCallback(async () => {
    setModelsError(null);
    try {
      setModels(await fetchModels());
    } catch (err) {
      setModelsError(describeApiError(err));
    }
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  const runForecast = async () => {
    setForecastLoading(true);
    setForecastError(null);
    try {
      setForecast(await fetchPrediction(ticker, modelName, steps, timeframe));
    } catch (err) {
      setForecast(null);
      setForecastError(
        err instanceof ApiError && err.status === 503
          ? `Chưa có mô hình ${registryName(ticker, timeframe, modelName)} trong MLflow Registry. Huấn luyện bằng: python train_${modelName}.py --ticker ${ticker} --timeframe ${timeframe}`
          : describeApiError(err)
      );
    } finally {
      setForecastLoading(false);
    }
  };

  const registry = models.find((m) => m.model_name === registryName(ticker, timeframe, modelName));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Phân tích & Dự báo"
        description="Chạy mô hình đã huấn luyện và đăng ký trong MLflow Registry trên dữ liệu thật; so sánh sai số với baseline Naive trên cùng tập kiểm thử."
      />

      <FilterBar>
        <Field label="Tài sản mục tiêu">
          {symbolsError ? (
            <button onClick={reloadSymbols} className="btn-secondary h-[42px]">Lỗi tải danh sách — thử lại</button>
          ) : (
            <select className="field-select" value={ticker} onChange={(e) => setTicker(e.target.value)} disabled={symbols.length === 0}>
              {symbols.map((s) => (
                <option key={s.ticker} value={s.ticker}>{s.ticker} ({s.asset_class === "crypto" ? "Crypto" : "Cổ phiếu VN"})</option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Mô hình huấn luyện">
          <select className="field-select" value={modelName} onChange={(e) => setModelName(e.target.value as ModelName)}>
            {MODELS.map((m) => (
              <option key={m} value={m}>{MODEL_INFO[m].name}</option>
            ))}
          </select>
        </Field>
        <Field label="Khung thời gian">
          <select className="field-select" value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe)}>
            <option value="1d">1 ngày</option>
            <option value="1h" disabled={assetClass !== "crypto"}>1 giờ (chỉ crypto)</option>
          </select>
        </Field>
        <Field label="Số bước dự báo">
          <select className="field-select" value={steps} onChange={(e) => setSteps(Number(e.target.value))}>
            {STEP_OPTIONS.map((n) => (
              <option key={n} value={n}>{n} {timeframe === "1h" ? "giờ" : "phiên"} tới</option>
            ))}
          </select>
        </Field>
        <button className="btn-primary" onClick={runForecast} disabled={forecastLoading || historyLoading || !ticker || history.length === 0}>
          {forecastLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Tiến hành dự báo
        </button>
      </FilterBar>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_400px] xl:grid-rows-[auto_auto]">
        <ChartPanel
          ticker={ticker}
          timeframe={timeframe}
          history={history}
          forecast={forecast}
          loading={historyLoading}
          error={historyError}
          forecastError={forecastError}
          onRetry={loadHistory}
        />
        <EvaluationPanel registry={registry} modelsError={modelsError} name={registryName(ticker, timeframe, modelName)} />
        <SummaryPanel model={modelName} history={history} forecast={forecast} assetClass={assetClass} />
      </div>

      {forecast && <ForecastTable forecast={forecast} lastClose={history[history.length - 1]?.close} assetClass={assetClass} timeframe={timeframe} />}
      <ComparisonTable models={models} ticker={ticker} timeframe={timeframe} />
    </div>
  );
}

function ChartPanel(props: {
  ticker: string;
  timeframe: Timeframe;
  history: IndicatorPoint[];
  forecast: PredictResponse | null;
  loading: boolean;
  error: string | null;
  forecastError: string | null;
  onRetry: () => void;
}) {
  const { ticker, timeframe, history, forecast, loading, error, forecastError, onRetry } = props;
  const historyPoints = history.map((p) => ({ label: formatAxisTime(p.ts, timeframe), value: p.close }));
  const forecastPoints = (forecast?.predictions ?? []).map((p) => ({ label: formatAxisTime(p.target_time, timeframe), value: p.predicted_value }));

  return (
    <section className="panel flex flex-col gap-3 p-5 xl:row-span-2">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[25px] font-bold text-white">Biểu đồ dự đoán</h2>
          <p className="text-xs text-slate-400">{ticker} · khung {timeframeLabel(timeframe)} · {history.length} nến gần nhất</p>
        </div>
        <ForecastLegend />
      </div>
      {forecastError && <div className="rounded border border-down/40 bg-down/10 px-3 py-2 text-sm text-rose-200">{forecastError}</div>}
      <div className="h-[560px]">
        {loading ? (
          <StateBox kind="loading" message={`Đang tải dữ liệu ${ticker}…`} height="h-full" />
        ) : error ? (
          <StateBox kind="error" message="Không tải được dữ liệu lịch sử" hint={error} onRetry={onRetry} height="h-full" />
        ) : history.length === 0 ? (
          <StateBox kind="empty" message={`Chưa có dữ liệu khung ${timeframeLabel(timeframe)} cho ${ticker || "mã này"}`} height="h-full" />
        ) : (
          <ForecastChart history={historyPoints} forecast={forecastPoints} />
        )}
      </div>
    </section>
  );
}

/** "% tốt hơn Naive" note for an error metric (lower is better). */
function vsNaive(model: number, naive: number | null, decimals: number = 4): string {
  if (naive === null || naive === 0) return "Chưa có số liệu Naive cho run này";
  const gain = (1 - model / naive) * 100;
  return `Naive: ${formatNum(naive, decimals)} · ${gain >= 0 ? "tốt hơn" : "kém hơn"} ${formatNum(Math.abs(gain), 1)}%`;
}

function EvaluationPanel({ registry, modelsError, name }: { registry?: ModelInfo; modelsError: string | null; name: string }) {
  const m = registry?.metrics;
  return (
    <section className="panel flex flex-col gap-3 p-5">
      <div>
        <h2 className="text-[25px] font-bold text-white">Đánh giá Mô hình</h2>
        <p className="text-sm text-muted">Trên tập dữ liệu kiểm thử (Test set)</p>
      </div>
      {modelsError ? (
        <p className="text-sm text-down">Không đọc được MLflow Registry: {modelsError}</p>
      ) : !registry ? (
        <p className="text-sm text-slate-400">Chưa có <span className="font-mono">{name}</span> trong Registry.</p>
      ) : !m ? (
        <p className="text-sm text-slate-400">Run huấn luyện không ghi MAE/RMSE/MAPE.</p>
      ) : (
        <>
          <MetricRow label="Root Mean Sq. Error (RMSE)" value={formatNum(m.rmse, 4)} note={vsNaive(m.rmse, m.naive_rmse)} />
          <MetricRow label="Mean Absolute Error (MAE)" value={formatNum(m.mae, 4)} note={vsNaive(m.mae, m.naive_mae)} />
          <MetricRow label="MAPE" value={`${formatNum(m.mape, 3)}%`} note={vsNaive(m.mape, m.naive_mape, 3)} />
          <MetricRow
            label="Directional accuracy"
            value={m.directional_accuracy === null ? "—" : `${formatNum(m.directional_accuracy * 100, 1)}%`}
            note="Tỷ lệ đoán đúng chiều tăng/giảm"
          />
          <p className="text-[11px] text-slate-500">
            {registry.model_name} · v{registry.version} · cập nhật {formatDate(registry.last_updated)}
          </p>
        </>
      )}
    </section>
  );
}

function SummaryPanel({ model, history, forecast, assetClass }: { model: ModelName; history: IndicatorPoint[]; forecast: PredictResponse | null; assetClass: string }) {
  const info = MODEL_INFO[model];
  const lastClose = history[history.length - 1]?.close;
  const finalValue = forecast?.predictions[forecast.predictions.length - 1]?.predicted_value;
  const move = lastClose && finalValue !== undefined ? (finalValue / lastClose - 1) * 100 : null;
  const insights = readIndicators(history);

  return (
    <section className="panel flex flex-col gap-3 p-5">
      <h2 className="text-[25px] font-bold text-white">Tóm tắt thuật toán</h2>
      <div className="metric-box space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-white">{info.name}</span>
          <Badge tone="slate">{info.family}</Badge>
        </div>
        <p className="text-sm leading-relaxed text-slate-300">{info.summary}</p>
        {info.caveat && <p className="text-xs text-amber-300">Lưu ý: {info.caveat}</p>}
      </div>
      <div className="metric-box space-y-2">
        <h3 className="font-semibold text-white">Phân tích chuyên sâu:</h3>
        {move !== null && (
          <p className={`text-sm ${move >= 0 ? "text-up" : "text-down"}`}>
            • Mô hình dự báo giá {move >= 0 ? "tăng" : "giảm"} {formatPct(Math.abs(move)).replace("+", "")} sau {forecast?.predictions.length} bước
            (từ {formatPrice(lastClose, assetClass)} → {formatPrice(finalValue, assetClass)}).
          </p>
        )}
        {insights.map((item) => (
          <p key={item.text} className={`text-sm ${TONE_CLASS[item.tone]}`}>• {item.text}</p>
        ))}
        {!forecast && <p className="text-xs text-slate-500">Bấm “Tiến hành dự báo” để thêm nhận định về kết quả dự báo.</p>}
      </div>
    </section>
  );
}

function ForecastTable({ forecast, lastClose, assetClass, timeframe }: { forecast: PredictResponse; lastClose?: number; assetClass: string; timeframe: string }) {
  return (
    <Panel title="Kết quả dự báo chi tiết" subtitle={`Tạo lúc ${formatDate(forecast.prediction_time, true)} · mô hình ${forecast.model_name}`} bodyClassName="overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>Bước</th>
            <th>Thời điểm dự báo</th>
            <th className="text-right">Giá dự báo</th>
            <th className="text-right">So với giá đóng cửa cuối</th>
          </tr>
        </thead>
        <tbody>
          {forecast.predictions.map((p, i) => (
            <tr key={p.target_time}>
              <td>{i + 1}</td>
              <td className="font-mono text-xs">{formatDate(p.target_time, timeframe === "1h")}</td>
              <td className="text-right font-mono text-forecast">{formatPrice(p.predicted_value, assetClass)}</td>
              <td className="text-right font-mono">{lastClose ? formatPct((p.predicted_value / lastClose - 1) * 100) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function ComparisonTable({ models, ticker, timeframe }: { models: ModelInfo[]; ticker: string; timeframe: Timeframe }) {
  const rows = MODELS.map((m) => ({ key: m, info: models.find((x) => x.model_name === registryName(ticker, timeframe, m)) }));
  const ratios = rows.map((r) => (r.info?.metrics?.naive_rmse ? r.info.metrics.rmse / r.info.metrics.naive_rmse : null));
  const best = Math.min(...ratios.filter((x): x is number => x !== null));

  return (
    <Panel
      title={`So sánh 4 mô hình — ${ticker} khung ${timeframeLabel(timeframe)}`}
      subtitle="RMSE/Naive < 1 nghĩa là mô hình tốt hơn dự báo “giá ngày mai = giá hôm nay”"
      bodyClassName="overflow-x-auto"
    >
      <table className="data-table whitespace-nowrap">
        <thead>
          <tr>
            <th>Mô hình</th>
            <th>Phiên bản</th>
            <th className="text-right">RMSE</th>
            <th className="text-right">RMSE Naive</th>
            <th className="text-right">RMSE / Naive</th>
            <th className="text-right">MAE</th>
            <th className="text-right">MAPE</th>
            <th className="text-right">Đúng chiều</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ key, info }, i) => {
            const m = info?.metrics;
            const ratio = ratios[i];
            return (
              <tr key={key}>
                <td className="font-semibold text-white">
                  {MODEL_INFO[key].name} {ratio !== null && ratio === best && <Badge tone="green">Tốt nhất</Badge>}
                </td>
                <td className="text-slate-400">{info ? `v${info.version}` : "chưa huấn luyện"}</td>
                <td className="text-right font-mono">{formatNum(m?.rmse, 4)}</td>
                <td className="text-right font-mono text-slate-400">{formatNum(m?.naive_rmse, 4)}</td>
                <td className={`text-right font-mono ${ratio === null ? "" : ratio < 1 ? "text-up" : "text-down"}`}>{formatNum(ratio, 3)}</td>
                <td className="text-right font-mono">{formatNum(m?.mae, 4)}</td>
                <td className="text-right font-mono">{m ? `${formatNum(m.mape, 3)}%` : "—"}</td>
                <td className="text-right font-mono">{m?.directional_accuracy == null ? "—" : `${formatNum(m.directional_accuracy * 100, 1)}%`}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Panel>
  );
}
