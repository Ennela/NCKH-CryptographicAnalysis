"use client";

import { useEffect, useState, useCallback } from "react";
import ReactECharts from "echarts-for-react";
import { Cpu, AlertCircle, Loader2, FileQuestion } from "lucide-react";
import {
  ApiError,
  fetchSymbols,
  fetchExplain,
  timeframeForAssetClass,
  type SymbolInfo,
  type ExplainResponse,
} from "@/lib/api";

/** Models selectable on this page — only tree-based XGBoost has SHAP artifacts today. */
const MODEL_OPTIONS = [
  { value: "xgboost", label: "XGBoost Regressor", supported: true },
  { value: "arima", label: "ARIMA Baseline (chưa hỗ trợ)", supported: false },
  { value: "random_forest", label: "Random Forest (chưa hỗ trợ)", supported: false },
  { value: "gru", label: "GRU PyTorch (chưa hỗ trợ)", supported: false },
] as const;

export default function ExplainabilityPage() {
  const [domLoaded, setDomLoaded] = useState(false);
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [symbolsError, setSymbolsError] = useState<string | null>(null);
  const [ticker, setTicker] = useState<string>("");
  const [modelName] = useState<"xgboost">("xgboost");

  const [explainData, setExplainData] = useState<ExplainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDomLoaded(true);
  }, []);

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

  const selectedSymbol = symbols.find((s) => s.ticker === ticker);
  const timeframe = timeframeForAssetClass(selectedSymbol?.asset_class);

  const loadExplain = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setNotFound(false);
    setError(null);
    setExplainData(null);
    try {
      const data = await fetchExplain(ticker, timeframe, modelName);
      setExplainData(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setNotFound(true);
      } else {
        setError(err instanceof Error ? err.message : "Lỗi kết nối API");
      }
    } finally {
      setLoading(false);
    }
  }, [ticker, timeframe, modelName]);

  useEffect(() => {
    loadExplain();
  }, [loadExplain]);

  // Sort ascending so the most important feature renders at the top of the bar chart.
  const sortedFeatures = explainData
    ? [...explainData.features]
        .map((f) => ({ feature: f.feature, value: f.mean_abs_shap ?? f.importance }))
        .sort((a, b) => a.value - b.value)
    : [];

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "shadow",
      },
      backgroundColor: "#151b2c",
      borderColor: "#1e293b",
      textStyle: {
        color: "#cbd5e1",
      },
      formatter: function (params: any) {
        const item = params[0];
        return `<div>
                  <span style="font-weight: 600; display: block">${item.name}</span>
                  <span style="color: #10b981">Mean |SHAP|: ${Number(item.value).toPrecision(4)}</span>
                </div>`;
      },
    },
    grid: {
      left: "3%",
      right: "10%",
      bottom: "10%",
      top: "5%",
      containLabel: true,
    },
    xAxis: {
      type: "value",
      axisLine: { lineStyle: { color: "#334155" } },
      axisLabel: { color: "#94a3b8" },
      splitLine: { lineStyle: { color: "#1e293b", type: "dashed" } },
    },
    yAxis: {
      type: "category",
      data: sortedFeatures.map((f) => f.feature),
      axisLine: { lineStyle: { color: "#334155" } },
      axisLabel: { color: "#94a3b8" },
      splitLine: { show: false },
    },
    series: [
      {
        name: "Mức độ ảnh hưởng (mean |SHAP|)",
        type: "bar",
        data: sortedFeatures.map((f) => f.value),
        itemStyle: {
          color: "#10b981",
          borderRadius: [0, 4, 4, 0],
        },
        label: {
          show: true,
          position: "right",
          formatter: function (params: any) {
            return Number(params.value).toPrecision(3);
          },
          textStyle: {
            color: "#cbd5e1",
            fontWeight: "bold",
            fontSize: 11,
          },
        },
      },
    ],
  };

  const topFeatures = [...sortedFeatures].reverse().slice(0, 3);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-200">SHAP Model Explainability</h1>
        <p className="text-slate-500 text-sm mt-1">
          Giải thích cơ chế ra quyết định của mô hình Machine Learning dựa trên SHAP values tính từ artifact huấn luyện thật.
        </p>
      </div>

      {/* Selectors */}
      <div className="glass-panel p-4 rounded-xl border border-darkBorder flex flex-col sm:flex-row gap-4">
        <div className="space-y-1.5 flex-1 max-w-xs">
          <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Mã Tài Sản</label>
          {symbolsError ? (
            <div className="text-xs text-glowRose flex items-center gap-2">
              <span>Không tải được danh sách mã</span>
              <button
                onClick={loadSymbols}
                className="px-3 py-1 rounded bg-slate-800 text-slate-300 border border-darkBorder hover:bg-slate-700 transition-all"
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

        <div className="space-y-1.5 flex-1 max-w-xs">
          <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Mô Hình</label>
          <select
            value={modelName}
            className="w-full bg-slate-900 border border-darkBorder rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-glowIndigo"
            onChange={() => undefined}
          >
            {MODEL_OPTIONS.map((m) => (
              <option key={m.value} value={m.value} disabled={!m.supported}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* SHAP Chart */}
        <div className="lg:col-span-2 space-y-6">
          <div className="glass-card p-6 rounded-xl border border-darkBorder">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-bold tracking-tight text-slate-200">
                Mức Độ Ảnh Hưởng Đặc Trưng — {ticker || "..."} (XGBoost)
              </h3>
              <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-glowEmerald border border-emerald-500/20 font-semibold uppercase">
                {explainData?.method || "SHAP"}
              </span>
            </div>

            {!domLoaded || loading ? (
              <div className="h-[400px] w-full flex flex-col items-center justify-center gap-3 bg-slate-900/50 rounded-xl">
                <Loader2 className="w-8 h-8 text-glowIndigo animate-spin" />
                <span className="text-slate-400 text-sm">Đang tải dữ liệu SHAP...</span>
              </div>
            ) : notFound ? (
              <div className="h-[400px] w-full flex flex-col items-center justify-center gap-3 bg-slate-900/50 rounded-xl px-6 text-center">
                <FileQuestion className="w-10 h-10 text-slate-600" />
                <span className="text-slate-300 font-semibold text-sm">Chưa có artifact SHAP cho model này.</span>
                <span className="text-slate-500 text-xs">
                  Chạy <code className="px-1.5 py-0.5 rounded bg-slate-800 text-glowEmerald font-mono">python -m services.training.train_xgboost</code> để tạo.
                </span>
              </div>
            ) : error ? (
              <div className="h-[400px] w-full flex flex-col items-center justify-center gap-3 bg-slate-900/50 rounded-xl px-6 text-center">
                <AlertCircle className="w-10 h-10 text-glowRose" />
                <span className="text-glowRose font-semibold text-sm">Không thể tải dữ liệu SHAP</span>
                <span className="text-slate-500 text-xs max-w-md">{error}</span>
                <button
                  onClick={loadExplain}
                  className="mt-1 px-4 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs border border-darkBorder hover:bg-slate-700 transition-all"
                >
                  Thử lại
                </button>
              </div>
            ) : sortedFeatures.length === 0 ? (
              <div className="h-[400px] w-full flex flex-col items-center justify-center gap-3 bg-slate-900/50 rounded-xl">
                <FileQuestion className="w-10 h-10 text-slate-600" />
                <span className="text-slate-500 text-sm">Artifact SHAP không chứa đặc trưng nào.</span>
              </div>
            ) : (
              <ReactECharts option={option} style={{ height: "400px", width: "100%" }} notMerge={true} />
            )}
          </div>
        </div>

        {/* Explain Summary Panel */}
        <div className="lg:col-span-1 space-y-6">
          <div className="glass-panel p-6 rounded-xl border border-darkBorder space-y-4">
            <div className="flex items-center gap-2 text-glowIndigo font-semibold">
              <Cpu className="w-5 h-5" />
              <span>Phân Tích Quyết Định</span>
            </div>

            <p className="text-slate-400 text-sm leading-relaxed">
              Mô hình XGBoost sử dụng các đặc trưng kỹ thuật của các phiên trước để dự báo giá đóng cửa của phiên tiếp theo.
              Giá trị mean |SHAP| đo lường mức độ đóng góp trung bình của mỗi đặc trưng vào dự báo trên tập kiểm thử.
            </p>

            {explainData && topFeatures.length > 0 && (
              <div className="space-y-3 pt-4 border-t border-darkBorder">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Đặc trưng ảnh hưởng lớn nhất
                </span>
                {topFeatures.map((f, idx) => (
                  <div key={f.feature} className="flex items-start gap-2.5 text-xs">
                    <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${idx === 0 ? "bg-glowEmerald" : "bg-glowIndigo"}`} />
                    <div>
                      <span className="font-semibold text-slate-300">{f.feature}</span>
                      <p className="text-slate-500 mt-0.5">mean |SHAP| = {f.value.toPrecision(4)}</p>
                    </div>
                  </div>
                ))}
                <p className="text-[10px] text-slate-600">
                  Cập nhật: {new Date(explainData.generated_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}
                </p>
              </div>
            )}
          </div>

          <div className="p-4 rounded-xl bg-slate-900 border border-darkBorder flex gap-2.5 items-start">
            <AlertCircle className="w-5 h-5 text-amber-500 shrink-0" />
            <div className="text-xs space-y-1">
              <span className="font-semibold text-slate-300 block">Lưu Ý Đối Với Các Mô Hình Khác</span>
              <p className="text-slate-500 leading-relaxed">
                ARIMA, Random Forest và GRU hiện chưa có artifact SHAP trong pipeline huấn luyện.
                Trang này sẽ hỗ trợ thêm các mô hình đó khi artifact giải thích tương ứng được bổ sung.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
