"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowDown, CheckCircle2, XCircle } from "lucide-react";
import {
  describeApiError,
  fetchDataQuality,
  fetchHealth,
  fetchJobs,
  type DataQualityReport,
  type HealthStatus,
  type JobLogEntry,
  type Timeframe,
} from "@/lib/api";
import { formatDate, formatNum, timeframeLabel } from "@/lib/format";
import { AssetBadge, Badge, Field, PageHeader, Panel, StateBox } from "@/components/ui";

/* Mirrors services/ingestion/celery_app.py, app/scheduler.py and app/cleaning.py. */
const SOURCES = [
  {
    source: "vnstock (nguồn VCI)",
    market: "Cổ phiếu Việt Nam (HOSE)",
    timeframes: "1 ngày",
    schedule: "Thứ 2–6, 10:00 UTC (17:00 giờ VN), lấy 7 ngày gần nhất",
    symbols: "FPT, VCB, MSN",
    note: "Phụ thuộc tùy chọn: PyPI cách ly gói vnstock từ 09/2026",
  },
  {
    source: "Binance qua thư viện ccxt",
    market: "Tiền mã hóa (cặp USDT)",
    timeframes: "1 giờ, 1 ngày",
    schedule: "1h: phút thứ 5 mỗi giờ · 1d: 00:10 UTC hằng ngày",
    symbols: "BTC/USDT, ETH/USDT",
    note: "API công khai, có giới hạn tần suất (enableRateLimit)",
  },
  {
    source: "Backfill + snapshot khóa",
    market: "Toàn bộ 25 mã",
    timeframes: "1 ngày, 1 giờ",
    schedule: "Chạy tay: scripts/backfill_all.py, import_dataset_snapshot.py",
    symbols: "15 cổ phiếu + 10 crypto",
    note: "Snapshot group_dataset_v1 có fingerprint SHA-256 dùng cho thí nghiệm",
  },
];

const CLEANING_STEPS = [
  { title: "Lưu dữ liệu thô", detail: "Mọi nến từ nguồn được ghi nguyên trạng vào market.ohlcv_raw (kèm raw_payload, ingested_at) để truy vết." },
  { title: "1. Chuẩn hóa múi giờ → UTC", detail: "Binance đã là UTC. vnstock khung ngày giữ nguyên ngày giao dịch; khung trong ngày trừ 7 giờ (giờ VN bị gán nhầm UTC)." },
  { title: "2. Loại bản ghi trùng", detail: "Khóa (symbol_id, timeframe, ts); nếu trùng giữ bản có ingested_at mới nhất." },
  { title: "3. Xử lý dữ liệu khuyết", detail: "Cổ phiếu khung ngày: dựng lịch thứ 2–6, forward-fill tối đa 3 phiên liên tiếp (CLEANING_FFILL_LIMIT), phiên điền có volume = 0; khoảng trống dài hơn bị bỏ. Crypto (24/7) không điền — thiếu nến là lỗi nguồn. Chỉ dùng dữ liệu quá khứ, không nhìn trước." },
  { title: "4. Phát hiện nhiễu (outlier)", detail: "Quy tắc IQR: ngoài [Q1 − 1,5·IQR, Q3 + 1,5·IQR] của close/volume theo từng mã → gắn cờ is_outlier, KHÔNG xóa, để người phân tích quyết định." },
  { title: "Ghi dữ liệu sạch", detail: "Upsert vào market.ohlcv (hypertable TimescaleDB, khóa chính (symbol_id, timeframe, ts), ràng buộc high ≥ low, giá ≥ 0) và ghi báo cáo vào ops.data_quality_check." },
];

const SCALING = [
  { model: "ARIMA(1,1,1)", method: "Không co giãn; sai phân bậc 1 (d = 1) để chuỗi dừng", fit: "—" },
  { model: "XGBoost", method: "StandardScaler (Z-score) cho 19 đặc trưng", fit: "Chỉ trên tập train, rồi transform validation/test" },
  { model: "Random Forest", method: "Không co giãn (cây quyết định bất biến với phép co giãn đơn điệu)", fit: "—" },
  { model: "GRU", method: "MinMaxScaler [0, 1] cho 8 đặc trưng và biến mục tiêu", fit: "Chỉ trên tập train, rồi transform validation/test" },
];

export default function PipelinePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Thu thập & Làm sạch dữ liệu"
        description="Cách hệ thống thu thập dữ liệu tự động, tổ chức – làm sạch – chuẩn hóa trước khi đưa vào mô hình, và kết quả đo chất lượng dữ liệu thực tế trong cơ sở dữ liệu."
      />
      <SourcesPanel />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_1fr]">
        <CleaningPanel />
        <ScalingPanel />
      </div>
      <QualityPanel />
      <OperationsPanel />
    </div>
  );
}

function SourcesPanel() {
  return (
    <Panel title="1. Nguồn dữ liệu & lịch thu thập tự động" subtitle="Celery Beat lập lịch → Celery worker gọi adapter của từng nguồn → ghi ops.job_log" bodyClassName="overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>Nguồn</th>
            <th>Thị trường</th>
            <th>Khung</th>
            <th>Lịch chạy</th>
            <th>Mã theo lịch</th>
            <th>Ghi chú</th>
          </tr>
        </thead>
        <tbody>
          {SOURCES.map((s) => (
            <tr key={s.source}>
              <td className="font-semibold text-white">{s.source}</td>
              <td>{s.market}</td>
              <td>{s.timeframes}</td>
              <td className="text-slate-400">{s.schedule}</td>
              <td className="font-mono text-xs">{s.symbols}</td>
              <td className="text-xs text-slate-400">{s.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function CleaningPanel() {
  return (
    <Panel title="2. Tổ chức & làm sạch dữ liệu" subtitle="services/ingestion/app/cleaning.py — chạy theo lịch: crypto mỗi giờ, cổ phiếu thứ 2–6 từ 11:00 UTC (sau lượt thu thập 10:00 UTC)">
      <ol className="flex flex-col items-stretch">
        {CLEANING_STEPS.map((step, i) => (
          <li key={step.title} className="flex flex-col items-center">
            <div className="metric-box w-full">
              <div className="font-semibold text-white">{step.title}</div>
              <p className="mt-1 text-sm leading-relaxed text-slate-300">{step.detail}</p>
            </div>
            {i < CLEANING_STEPS.length - 1 && <ArrowDown className="my-1 h-4 w-4 text-accentSoft" />}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function ScalingPanel() {
  return (
    <Panel title="3. Chuẩn hóa dữ liệu trước khi đưa vào mô hình" subtitle="Chuẩn hóa nằm trong pipeline huấn luyện của từng mô hình, không ghi đè dữ liệu gốc">
      <div className="space-y-4">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Mô hình</th>
                <th>Phương pháp chuẩn hóa</th>
                <th>Fit trên</th>
              </tr>
            </thead>
            <tbody>
              {SCALING.map((s) => (
                <tr key={s.model}>
                  <td className="font-semibold text-white">{s.model}</td>
                  <td>{s.method}</td>
                  <td className="text-slate-400">{s.fit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="metric-box space-y-1.5 text-sm text-slate-300">
          <div className="font-semibold text-white">Quy tắc chống rò rỉ dữ liệu (look-ahead)</div>
          <p>• Chia tập theo thời gian, không xáo trộn: train 70% · validation 15% · test 15%.</p>
          <p>• Scaler chỉ học (fit) trên tập train; validation/test chỉ được transform.</p>
          <p>• Mọi đặc trưng (lag, SMA, RSI, MACD…) dùng cửa sổ trượt về quá khứ.</p>
          <p>• Thí nghiệm đọc snapshot bất biến có fingerprint SHA-256, không đọc DB đang chạy.</p>
        </div>
        <p className="text-xs text-slate-500">
          Z-score: x′ = (x − μ_train) / σ_train · Min-Max: x′ = (x − min_train) / (max_train − min_train)
        </p>
      </div>
    </Panel>
  );
}

function QualityPanel() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");
  const [rows, setRows] = useState<DataQualityReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await fetchDataQuality(timeframe));
    } catch (err) {
      setRows([]);
      setError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }, [timeframe]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Panel
      title={`4. Chất lượng dữ liệu đã làm sạch (khung ${timeframeLabel(timeframe)})`}
      subtitle="Đo trực tiếp trên market.ohlcv; outlier đếm trên lợi suất giữa hai nến liên tiếp (cùng quy tắc IQR k = 1,5)"
      bodyClassName="overflow-x-auto"
      actions={
        <Field label="" className="min-w-[160px]">
          <select className="field-select" value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe)}>
            <option value="1d">Khung 1 ngày</option>
            <option value="1h">Khung 1 giờ</option>
          </select>
        </Field>
      }
    >
      {loading ? (
        <StateBox kind="loading" message="Đang đo chất lượng dữ liệu…" />
      ) : error ? (
        <StateBox kind="error" message="Không tải được báo cáo chất lượng" hint={error} onRetry={load} />
      ) : rows.length === 0 ? (
        <StateBox kind="empty" message={`Chưa có dữ liệu khung ${timeframeLabel(timeframe)}`} />
      ) : (
        <table className="data-table whitespace-nowrap">
          <thead>
            <tr>
              <th>Mã</th>
              <th>Loại</th>
              <th className="text-right">Số nến</th>
              <th className="text-right">Kỳ vọng</th>
              <th className="text-right">Thiếu</th>
              <th>Độ đầy đủ</th>
              <th className="text-right" title="Phiên được forward-fill hoặc không có giao dịch">Volume = 0</th>
              <th className="text-right">OHLC lỗi</th>
              <th className="text-right">Outlier lợi suất</th>
              <th className="text-right">Outlier KL</th>
              <th>Lần làm sạch gần nhất</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker}>
                <td className="font-bold text-white">{r.ticker}</td>
                <td><AssetBadge assetClass={r.asset_class} /></td>
                <td className="text-right font-mono">{formatNum(r.bars, 0)}</td>
                <td className="text-right font-mono text-slate-400">{formatNum(r.expected_bars, 0)}</td>
                <td className={`text-right font-mono ${r.missing_bars > 0 ? "text-forecast" : ""}`}>{formatNum(r.missing_bars, 0)}</td>
                <td>
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-24 overflow-hidden rounded bg-page">
                      <div className={`h-full ${r.completeness_pct >= 95 ? "bg-up" : "bg-forecast"}`} style={{ width: `${Math.min(r.completeness_pct, 100)}%` }} />
                    </div>
                    <span className="font-mono text-xs">{formatNum(r.completeness_pct, 1)}%</span>
                  </div>
                </td>
                <td className="text-right font-mono">{formatNum(r.zero_volume_bars, 0)}</td>
                <td className={`text-right font-mono ${r.invalid_ohlc_bars > 0 ? "text-down" : ""}`}>{formatNum(r.invalid_ohlc_bars, 0)}</td>
                <td className="text-right font-mono">{formatNum(r.return_outliers, 0)}</td>
                <td className="text-right font-mono">{formatNum(r.volume_outliers, 0)}</td>
                <td className="text-xs">
                  {r.last_pipeline_check ? (
                    <span className="flex items-center gap-2">
                      {r.last_pipeline_check.passed ? <Badge tone="green">Đạt</Badge> : <Badge tone="amber">Có outlier</Badge>}
                      <span className="text-slate-400">
                        {formatDate(r.last_pipeline_check.checked_at, true)} · trùng {r.last_pipeline_check.detail.duplicates_removed ?? 0} · điền{" "}
                        {r.last_pipeline_check.detail.missing_filled ?? 0}
                      </span>
                    </span>
                  ) : (
                    <span className="text-slate-500" title="Dữ liệu nạp bằng import snapshot / backfill, chưa qua clean_and_store_task">
                      Chưa chạy pipeline làm sạch
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="px-5 py-3 text-xs text-slate-500">
        Nến kỳ vọng tính theo lịch thứ 2–6 cho cổ phiếu (chưa trừ ngày lễ Việt Nam, nên ngày lễ hiện là “thiếu”) và theo lịch liên tục cho crypto.
      </p>
    </Panel>
  );
}

function OperationsPanel() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobLogEntry[]>([]);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const [h, j] = await Promise.allSettled([fetchHealth(), fetchJobs(30)]);
    setHealth(h.status === "fulfilled" ? h.value : null);
    setHealthError(h.status === "rejected" ? describeApiError(h.reason) : null);
    setJobs(j.status === "fulfilled" ? j.value : []);
    setJobsError(j.status === "rejected" ? describeApiError(j.reason) : null);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const statusTone = (status: string) => (status === "success" ? "green" : status === "failed" ? "red" : status === "running" ? "blue" : "slate");

  return (
    <Panel
      title="5. Vận hành: trạng thái dịch vụ & nhật ký job"
      subtitle="Nhật ký lấy từ ops.job_log do Celery worker ghi khi thu thập/làm sạch"
      bodyClassName="space-y-4 p-5"
      actions={<button className="btn-secondary" onClick={load}>Làm mới</button>}
    >
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-slate-400">Inference API:</span>
        {loading ? (
          <Badge tone="slate">đang kiểm tra…</Badge>
        ) : health ? (
          <span className="flex items-center gap-1.5 text-up"><CheckCircle2 className="h-4 w-4" /> {health.status}</span>
        ) : (
          <span className="flex items-center gap-1.5 text-down"><XCircle className="h-4 w-4" /> {healthError}</span>
        )}
      </div>
      <div className="overflow-x-auto rounded border border-line">
        {jobsError ? (
          <StateBox kind="error" message="Không đọc được ops.job_log" hint={jobsError} onRetry={load} />
        ) : !loading && jobs.length === 0 ? (
          <StateBox kind="empty" message="Chưa có job nào được ghi" hint="Job xuất hiện khi Celery worker/beat đang chạy." />
        ) : (
          <table className="data-table whitespace-nowrap">
            <thead>
              <tr>
                <th>Bắt đầu</th>
                <th>Loại</th>
                <th>Tên job</th>
                <th>Mã</th>
                <th>Khung</th>
                <th>Trạng thái</th>
                <th className="text-right">Thời gian chạy</th>
                <th className="text-right">Số dòng</th>
                <th>Lỗi</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j, i) => (
                <tr key={`${j.started_at}-${i}`}>
                  <td className="font-mono text-xs text-slate-400">{formatDate(j.started_at, true)}</td>
                  <td>{j.job_type === "ingest" ? "Thu thập" : j.job_type === "clean" ? "Làm sạch" : j.job_type}</td>
                  <td className="font-mono text-xs">{j.job_name}</td>
                  <td className="font-semibold text-white">{j.ticker ?? "—"}</td>
                  <td>{j.timeframe ?? "—"}</td>
                  <td><Badge tone={statusTone(j.status)}>{j.status}</Badge></td>
                  <td className="text-right font-mono">{j.duration_ms === null ? "—" : `${formatNum(j.duration_ms, 0)} ms`}</td>
                  <td className="text-right font-mono">{j.rows_affected ?? "—"}</td>
                  <td className="max-w-xs truncate text-xs text-down" title={j.error_message ?? ""}>{j.error_message ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Panel>
  );
}
