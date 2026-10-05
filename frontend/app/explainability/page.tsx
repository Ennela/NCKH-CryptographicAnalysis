"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, describeApiError, fetchExplain, type ExplainResponse, type ModelName, type Timeframe } from "@/lib/api";
import { formatDate, formatNum, timeframeLabel } from "@/lib/format";
import { useSymbols } from "@/lib/use-symbols";
import EChart, { CHART_THEME } from "@/components/echart";
import { Badge, Field, FilterBar, MetricRow, PageHeader, Panel, StateBox } from "@/components/ui";

const MODEL_OPTIONS: { value: ModelName; label: string }[] = [
  { value: "xgboost", label: "XGBoost" },
  { value: "random_forest", label: "Random Forest" },
  { value: "gru", label: "GRU" },
  { value: "arima", label: "ARIMA" },
];

const MODEL_LABEL: Record<ModelName, string> = {
  xgboost: "XGBoost",
  random_forest: "Random Forest",
  gru: "GRU",
  arima: "ARIMA",
};

/** Which explanation each model's training entrypoint logs (see docs/api.md §7). */
const METHOD_OF: Record<ModelName, string> = {
  xgboost: "shap_tree_explainer",
  random_forest: "shap_tree_explainer",
  gru: "permutation_importance",
  arima: "arima_coefficients",
};

const METHOD_LABEL: Record<string, string> = {
  shap_tree_explainer: "SHAP TreeExplainer",
  permutation_importance: "Permutation importance",
  arima_coefficients: "Hệ số ARIMA",
};

const PARAM_MEANING: Record<string, string> = {
  "ar.L1": "Biến động giá phiên này phụ thuộc bao nhiêu vào biến động phiên trước.",
  "ma.L1": "Mô hình điều chỉnh theo sai số dự báo của phiên trước bao nhiêu.",
  sigma2: "Phương sai của phần nhiễu mà mô hình không giải thích được.",
};

type Bar = { name: string; value: number; spread: number | null };

/** Bars for the tree/GRU methods: mean |SHAP| for trees, mean RMSE increase for GRU. */
function toBars(data: ExplainResponse): Bar[] {
  return data.features
    .map((f) => ({
      name: f.feature,
      value: data.method === "shap_tree_explainer" ? f.mean_abs_shap ?? f.importance : f.importance,
      spread: f.importance_std ?? null,
    }))
    .sort((a, b) => a.value - b.value);
}

export default function ExplainabilityPage() {
  const { symbols, ticker, setTicker, selected } = useSymbols();
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");
  const [modelName, setModelName] = useState<ModelName>("xgboost");
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
      setData(await fetchExplain(ticker, timeframe, modelName));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true);
      else setError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }, [ticker, timeframe, modelName]);

  useEffect(() => {
    load();
  }, [load]);

  const method = data?.method ?? METHOD_OF[modelName];
  const isArima = method === "arima_coefficients";
  const unit = selected?.asset_class === "crypto" ? "USD" : "nghìn VND";
  const stateHeight = isArima ? "h-64" : "h-full";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Giải thích mô hình"
        description="Mô hình dựa vào đâu để dự báo: SHAP cho XGBoost và Random Forest, permutation importance cho GRU, bảng hệ số cho ARIMA. Mọi giá trị được tính lúc huấn luyện và đọc từ MLflow."
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
          <select className="field-select" value={modelName} onChange={(e) => setModelName(e.target.value as ModelName)}>
            {MODEL_OPTIONS.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </Field>
      </FilterBar>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_400px]">
        <Panel
          title={`${isArima ? "Tham số ước lượng" : "Mức độ ảnh hưởng của đặc trưng"} — ${MODEL_LABEL[modelName]} · ${ticker || "…"} (${timeframeLabel(timeframe)})`}
          actions={<Badge tone="blue">{METHOD_LABEL[method] ?? method}</Badge>}
          className={isArima ? "self-start" : ""}
          bodyClassName={isArima ? "p-0" : "h-[520px] p-3"}
        >
          {loading ? (
            <StateBox kind="loading" message="Đang tải kết quả giải thích…" height={stateHeight} />
          ) : notFound ? (
            <StateBox
              kind="empty"
              message="Chưa có kết quả giải thích cho mô hình này"
              hint={`Huấn luyện bằng: python train_${modelName}.py --ticker ${ticker} --timeframe ${timeframe}`}
              height={stateHeight}
            />
          ) : error ? (
            <StateBox kind="error" message="Không tải được kết quả giải thích" hint={error} onRetry={load} height={stateHeight} />
          ) : !data || data.features.length === 0 ? (
            <StateBox kind="empty" message="Artifact không chứa đặc trưng nào" height={stateHeight} />
          ) : isArima ? (
            <CoefficientTable data={data} />
          ) : (
            <FeatureChart bars={toBars(data)} method={method} unit={unit} />
          )}
        </Panel>

        <div className="flex flex-col gap-6">
          <SummaryPanel data={data} unit={unit} />
          <GuidePanel method={method} />
        </div>
      </div>
    </div>
  );
}

function FeatureChart({ bars, method, unit }: { bars: Bar[]; method: string; unit: string }) {
  const axisName = method === "permutation_importance" ? `RMSE tăng thêm (${unit})` : "mean |SHAP|";
  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      ...CHART_THEME.tooltip,
      formatter: (params: { dataIndex: number }[]) => {
        const bar = bars[params[0].dataIndex];
        const spread = bar.spread !== null ? ` (± ${bar.spread.toPrecision(3)})` : "";
        return `${bar.name}<br/>${axisName}: ${bar.value.toPrecision(4)}${spread}`;
      },
    },
    grid: { left: 8, right: 60, top: 10, bottom: 30, containLabel: true },
    xAxis: {
      type: "value",
      name: axisName,
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: "#94A3B8", fontSize: 11 },
      axisLine: CHART_THEME.axisLine,
      axisLabel: CHART_THEME.axisLabel,
      splitLine: CHART_THEME.splitLine,
    },
    yAxis: { type: "category", data: bars.map((b) => b.name), axisLine: CHART_THEME.axisLine, axisLabel: CHART_THEME.axisLabel },
    series: [
      {
        name: axisName,
        type: "bar",
        // A negative RMSE increase means shuffling the feature did not hurt: shown in grey.
        data: bars.map((b) => ({ value: b.value, itemStyle: { color: b.value < 0 ? "#64748B" : "#3B82F6", borderRadius: [0, 4, 4, 0] } })),
        label: { show: true, position: "right", color: "#CBD5E1", fontSize: 11, formatter: (p: { value: number }) => Number(p.value).toPrecision(3) },
      },
    ],
  };
  return <EChart option={option} notMerge style={{ height: "100%", width: "100%" }} />;
}

function formatPValue(p: number | null | undefined): string {
  if (p === null || p === undefined) return "—";
  return p < 0.0001 ? "< 0,0001" : formatNum(p, 4);
}

function CoefficientTable({ data }: { data: ExplainResponse }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>Tham số</th>
            <th className="text-right">Hệ số</th>
            <th className="text-right">Sai số chuẩn</th>
            <th className="text-right">p-value</th>
            <th>Ý nghĩa</th>
          </tr>
        </thead>
        <tbody>
          {data.features.map((f) => {
            const hasP = f.p_value !== null && f.p_value !== undefined;
            const significant = hasP && (f.p_value as number) < 0.05;
            return (
              <tr key={f.feature}>
                <td className="font-mono font-semibold text-white">{f.feature}</td>
                <td className="text-right font-mono">{formatNum(f.coefficient ?? f.importance, 4)}</td>
                <td className="text-right font-mono">{formatNum(f.std_error, 4)}</td>
                <td className="whitespace-nowrap text-right">
                  <span className="font-mono">{formatPValue(f.p_value)}</span>{" "}
                  {f.feature !== "sigma2" && hasP && <Badge tone={significant ? "green" : "slate"}>{significant ? "có ý nghĩa" : "không rõ"}</Badge>}
                </td>
                <td className="text-slate-400">{PARAM_MEANING[f.feature] ?? "Tham số của mô hình ARIMA."}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** ARIMA(1,1,1): when ar.L1 ≈ −ma.L1 the two terms nearly cancel and the model behaves like a random walk. */
function arimaCancellationNote(data: ExplainResponse): string | null {
  const coef = (name: string) => data.features.find((f) => f.feature === name)?.coefficient;
  const ar = coef("ar.L1");
  const ma = coef("ma.L1");
  if (ar === null || ar === undefined || ma === null || ma === undefined) return null;
  return `ar.L1 + ma.L1 = ${formatNum(ar + ma, 3)}. Tổng càng gần 0 thì hai thành phần càng triệt tiêu nhau và ARIMA(1,1,1) càng gần bước ngẫu nhiên (dự báo ≈ giá đóng cửa gần nhất), một lý do khiến ARIMA bám sát baseline Naive.`;
}

function SummaryPanel({ data, unit }: { data: ExplainResponse | null; unit: string }) {
  if (data?.method === "arima_coefficients") {
    const note = arimaCancellationNote(data);
    return (
      <Panel title="Tóm tắt mô hình" bodyClassName="flex flex-col gap-2.5 p-4">
        <MetricRow label="Bậc (p, d, q)" value={data.order ? `(${data.order.join(", ")})` : "—"} />
        <MetricRow label="Số quan sát lịch sử" value={data.n_observations?.toLocaleString("vi-VN") ?? "—"} />
        {note && <p className="text-xs leading-relaxed text-slate-300">{note}</p>}
        <p className="text-[11px] text-slate-500">Artifact tạo lúc {formatDate(data.generated_at, true)}</p>
      </Panel>
    );
  }
  const top = data ? [...toBars(data)].reverse().slice(0, 5) : [];
  return (
    <Panel title="Đặc trưng ảnh hưởng lớn nhất" bodyClassName="flex flex-col gap-2.5 p-4">
      {top.length === 0 ? (
        <p className="text-sm text-slate-400">Chưa có dữ liệu.</p>
      ) : (
        top.map((f, i) => <MetricRow key={f.name} label={`${i + 1}. ${f.name}`} value={f.value.toPrecision(4)} />)
      )}
      {data?.method === "permutation_importance" && data.baseline_rmse != null && (
        <MetricRow
          label="RMSE gốc trên tập test"
          value={`${formatNum(data.baseline_rmse, 4)} ${unit}`}
          note={`${data.n_repeats ?? "?"} lần xáo trộn mỗi đặc trưng`}
        />
      )}
      {data && <p className="text-[11px] text-slate-500">Artifact tạo lúc {formatDate(data.generated_at, true)}</p>}
    </Panel>
  );
}

function GuidePanel({ method }: { method: string }) {
  return (
    <Panel title="Cách đọc kết quả" bodyClassName="space-y-2 p-4 text-sm leading-relaxed text-slate-300">
      {method === "permutation_importance" ? (
        <>
          <p>Mỗi đặc trưng được xáo trộn giữa các chuỗi 7 bước của tập kiểm thử (giữ nguyên phân phối, phá vỡ liên hệ với giá cần dự báo), lặp lại vài lần với seed cố định. Cột là mức RMSE tăng thêm so với RMSE gốc: càng lớn, GRU càng phụ thuộc vào đặc trưng đó.</p>
          <p>Giá trị gần 0 hoặc âm (màu xám) nghĩa là xáo trộn đặc trưng gần như không làm dự báo kém đi, tức mô hình hầu như không dùng nó.</p>
          <p className="text-xs text-slate-500">GRU dự báo phần hiệu chỉnh cộng vào giá đóng cửa gần nhất (residual), nên đặc trưng close thường chi phối.</p>
        </>
      ) : method === "arima_coefficients" ? (
        <>
          <p>ARIMA chỉ dùng chuỗi giá đóng cửa nên không có đặc trưng để xếp hạng. Phần giải thích là các tham số ước lượng trên tập huấn luyện; d = 1 nghĩa là mô hình dự báo phần thay đổi giá (sai phân) thay vì mức giá.</p>
          <p>p-value &lt; 0,05: hệ số khác 0 có ý nghĩa thống kê ở mức 5%. Sai số chuẩn lớn so với hệ số nghĩa là ước lượng kém chắc chắn.</p>
        </>
      ) : (
        <>
          <p>SHAP phân rã mỗi dự báo thành tổng đóng góp của từng đặc trưng. Giá trị mean |SHAP| là độ lớn đóng góp trung bình trên tập kiểm thử: càng lớn, đặc trưng càng chi phối dự báo.</p>
          <p>Với dữ liệu giá, các đặc trưng trễ (close_lag_*) và trung bình trượt thường đứng đầu: mô hình chủ yếu bám mức giá gần nhất, phù hợp với việc baseline Naive rất khó bị vượt qua.</p>
          <p className="text-xs text-slate-500">XGBoost và Random Forest dùng chung phương pháp nên so sánh trực tiếp được với nhau.</p>
        </>
      )}
    </Panel>
  );
}
