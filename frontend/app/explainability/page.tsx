"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, describeApiError, fetchExplain, type ExplainResponse, type Timeframe } from "@/lib/api";
import { formatDate, timeframeLabel } from "@/lib/format";
import { useSymbols } from "@/lib/use-symbols";
import EChart, { CHART_THEME } from "@/components/echart";
import { Badge, Field, FilterBar, MetricRow, PageHeader, Panel, StateBox } from "@/components/ui";

/** Only the tree-based XGBoost pipeline logs a SHAP artifact today. */
const MODEL_OPTIONS = [
  { value: "xgboost", label: "XGBoost", supported: true },
  { value: "random_forest", label: "Random Forest (chưa hỗ trợ)", supported: false },
  { value: "arima", label: "ARIMA (chưa hỗ trợ)", supported: false },
  { value: "gru", label: "GRU (chưa hỗ trợ)", supported: false },
] as const;

export default function ExplainabilityPage() {
  const { symbols, ticker, setTicker, selected } = useSymbols();
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");
  const [data, setData] = useState<ExplainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (selected?.asset_class !== "crypto") setTimeframe("1d");
  }, [selected?.asset_class]);

  const load = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setNotFound(false);
    setError(null);
    setData(null);
    try {
      setData(await fetchExplain(ticker, timeframe, "xgboost"));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true);
      else setError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }, [ticker, timeframe]);

  useEffect(() => {
    load();
  }, [load]);

  const features = data
    ? [...data.features].map((f) => ({ name: f.feature, value: f.mean_abs_shap ?? f.importance })).sort((a, b) => a.value - b.value)
    : [];
  const top = [...features].reverse().slice(0, 5);

  const option = {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, ...CHART_THEME.tooltip },
    grid: { left: 8, right: 60, top: 10, bottom: 10, containLabel: true },
    xAxis: { type: "value", axisLine: CHART_THEME.axisLine, axisLabel: CHART_THEME.axisLabel, splitLine: CHART_THEME.splitLine },
    yAxis: { type: "category", data: features.map((f) => f.name), axisLine: CHART_THEME.axisLine, axisLabel: CHART_THEME.axisLabel },
    series: [
      {
        name: "mean |SHAP|",
        type: "bar",
        data: features.map((f) => f.value),
        itemStyle: { color: "#3B82F6", borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: "#CBD5E1", fontSize: 11, formatter: (p: { value: number }) => Number(p.value).toPrecision(3) },
      },
    ],
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Giải thích mô hình (SHAP)"
        description="Mức đóng góp trung bình của từng đặc trưng vào dự báo của XGBoost trên tập kiểm thử, đọc từ artifact SHAP được ghi lúc huấn luyện."
      />

      <FilterBar>
        <Field label="Tài sản">
          <select className="field-select" value={ticker} onChange={(e) => setTicker(e.target.value)} disabled={symbols.length === 0}>
            {symbols.map((s) => (
              <option key={s.ticker} value={s.ticker}>{s.ticker} ({s.asset_class === "crypto" ? "Crypto" : "Cổ phiếu VN"})</option>
            ))}
          </select>
        </Field>
        <Field label="Khung thời gian">
          <select className="field-select" value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe)}>
            <option value="1d">1 ngày</option>
            <option value="1h" disabled={selected?.asset_class !== "crypto"}>1 giờ (chỉ crypto)</option>
          </select>
        </Field>
        <Field label="Mô hình">
          <select className="field-select" value="xgboost" onChange={() => undefined}>
            {MODEL_OPTIONS.map((m) => (
              <option key={m.value} value={m.value} disabled={!m.supported}>{m.label}</option>
            ))}
          </select>
        </Field>
      </FilterBar>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_400px]">
        <Panel
          title={`Mức độ ảnh hưởng của đặc trưng — ${ticker || "…"} (${timeframeLabel(timeframe)})`}
          actions={data && <Badge tone="blue">{data.method}</Badge>}
          bodyClassName="h-[520px] p-3"
        >
          {loading ? (
            <StateBox kind="loading" message="Đang tải artifact SHAP…" height="h-full" />
          ) : notFound ? (
            <StateBox
              kind="empty"
              message="Chưa có artifact SHAP cho mô hình này"
              hint={`Huấn luyện bằng: python train_xgboost.py --ticker ${ticker} --timeframe ${timeframe}`}
              height="h-full"
            />
          ) : error ? (
            <StateBox kind="error" message="Không tải được dữ liệu SHAP" hint={error} onRetry={load} height="h-full" />
          ) : features.length === 0 ? (
            <StateBox kind="empty" message="Artifact SHAP không chứa đặc trưng nào" height="h-full" />
          ) : (
            <EChart option={option} notMerge style={{ height: "100%", width: "100%" }} />
          )}
        </Panel>

        <div className="flex flex-col gap-6">
          <Panel title="Đặc trưng ảnh hưởng lớn nhất" bodyClassName="flex flex-col gap-2.5 p-4">
            {top.length === 0 ? (
              <p className="text-sm text-slate-400">Chưa có dữ liệu.</p>
            ) : (
              top.map((f, i) => <MetricRow key={f.name} label={`${i + 1}. ${f.name}`} value={f.value.toPrecision(4)} />)
            )}
            {data && <p className="text-[11px] text-slate-500">Artifact tạo lúc {formatDate(data.generated_at, true)}</p>}
          </Panel>
          <Panel title="Cách đọc biểu đồ" bodyClassName="space-y-2 p-4 text-sm leading-relaxed text-slate-300">
            <p>SHAP phân rã mỗi dự báo thành tổng đóng góp của từng đặc trưng. Giá trị mean |SHAP| là độ lớn đóng góp trung bình trên tập kiểm thử — càng lớn, đặc trưng càng chi phối dự báo.</p>
            <p>Với dữ liệu giá, các đặc trưng trễ (close_lag_*) và trung bình trượt thường đứng đầu: mô hình chủ yếu bám mức giá gần nhất, phù hợp với việc baseline Naive rất khó bị vượt qua.</p>
            <p className="text-xs text-slate-500">ARIMA, Random Forest và GRU chưa ghi artifact SHAP trong pipeline huấn luyện.</p>
          </Panel>
        </div>
      </div>
    </div>
  );
}
