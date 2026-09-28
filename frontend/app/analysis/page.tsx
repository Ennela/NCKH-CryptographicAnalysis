"use client";

import { useCallback, useEffect, useState } from "react";
import {
  describeApiError,
  fetchIndicators,
  fetchStats,
  type IndicatorPoint,
  type SymbolStats,
  type Timeframe,
} from "@/lib/api";
import { formatDate, formatNum, formatPct, formatPrice, formatVolume, timeframeLabel } from "@/lib/format";
import { readIndicators, rsiZone, TONE_CLASS } from "@/lib/insights";
import AnalysisChart from "@/components/analysis-chart";
import { AssetBadge, Field, FilterBar, MetricRow, PageHeader, Panel, StateBox } from "@/components/ui";

const WINDOW_OPTIONS = [120, 250, 500, 1000];
const RECENT_ROWS = 30;

/** Read ?ticker=&timeframe= once on mount (links from the overview page). */
function initialQuery(): { ticker: string; timeframe: Timeframe } {
  if (typeof window === "undefined") return { ticker: "", timeframe: "1d" };
  const params = new URLSearchParams(window.location.search);
  return { ticker: params.get("ticker") ?? "", timeframe: params.get("timeframe") === "1h" ? "1h" : "1d" };
}

export default function AnalysisPage() {
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");
  const [ticker, setTicker] = useState("");
  const [windowSize, setWindowSize] = useState(250);

  const [stats, setStats] = useState<SymbolStats[]>([]);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);

  const [points, setPoints] = useState<IndicatorPoint[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);

  // Wait until the URL query is applied so stats are not fetched twice (and raced).
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const query = initialQuery();
    setTimeframe(query.timeframe);
    setTicker(query.ticker);
    setReady(true);
  }, []);

  const loadStats = useCallback(async () => {
    if (!ready) return;
    setStatsLoading(true);
    setStatsError(null);
    try {
      const data = await fetchStats(timeframe);
      setStats(data);
      setTicker((prev) => (data.some((s) => s.ticker === prev) ? prev : data[0]?.ticker ?? ""));
    } catch (err) {
      setStats([]);
      setStatsError(describeApiError(err));
    } finally {
      setStatsLoading(false);
    }
  }, [timeframe, ready]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const loadChart = useCallback(async () => {
    if (!ticker || !stats.some((s) => s.ticker === ticker)) return;
    setChartLoading(true);
    setChartError(null);
    try {
      setPoints((await fetchIndicators(ticker, timeframe, windowSize)).points);
    } catch (err) {
      setPoints([]);
      setChartError(describeApiError(err));
    } finally {
      setChartLoading(false);
    }
  }, [ticker, timeframe, windowSize, stats]);

  useEffect(() => {
    loadChart();
  }, [loadChart]);

  const selected = stats.find((s) => s.ticker === ticker);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dữ liệu & Phân tích"
        description="Bảng thông số thống kê của dữ liệu đã làm sạch và dashboard phân tích biến động giá theo thời gian: nến OHLC, đường trung bình động, khối lượng, RSI và MACD."
      />

      <FilterBar>
        <Field label="Khung thời gian">
          <select className="field-select" value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe)}>
            <option value="1d">1 ngày (cổ phiếu + crypto)</option>
            <option value="1h">1 giờ (crypto)</option>
          </select>
        </Field>
        <Field label="Mã tài sản">
          <select className="field-select" value={ticker} onChange={(e) => setTicker(e.target.value)} disabled={stats.length === 0}>
            {stats.length === 0 && <option value="">—</option>}
            {stats.map((s) => (
              <option key={s.ticker} value={s.ticker}>
                {s.ticker} ({s.asset_class === "crypto" ? "Crypto" : "Cổ phiếu VN"})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Số nến hiển thị">
          <select className="field-select" value={windowSize} onChange={(e) => setWindowSize(Number(e.target.value))}>
            {WINDOW_OPTIONS.map((n) => (
              <option key={n} value={n}>{n} nến gần nhất</option>
            ))}
          </select>
        </Field>
      </FilterBar>

      <StatsTable
        stats={stats}
        timeframe={timeframe}
        loading={statsLoading}
        error={statsError}
        onRetry={loadStats}
        selected={ticker}
        onSelect={setTicker}
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_360px]">
        <Panel
          title={`Biểu đồ phân tích kỹ thuật — ${ticker || "…"} (${timeframeLabel(timeframe)})`}
          subtitle="Cuộn chuột hoặc kéo thanh trượt để phóng to một giai đoạn; bốn tầng dùng chung trục thời gian."
          bodyClassName="h-[760px] p-3"
        >
          {chartLoading ? (
            <StateBox kind="loading" message={`Đang tải dữ liệu ${ticker}…`} height="h-full" />
          ) : chartError ? (
            <StateBox kind="error" message="Không tải được dữ liệu biểu đồ" hint={chartError} onRetry={loadChart} height="h-full" />
          ) : points.length === 0 ? (
            <StateBox kind="empty" message="Chưa chọn mã hoặc chưa có dữ liệu" height="h-full" />
          ) : (
            <AnalysisChart points={points} timeframe={timeframe} />
          )}
        </Panel>
        <IndicatorSidebar points={points} stats={selected} timeframe={timeframe} />
      </div>

      <RecentTable points={points} timeframe={timeframe} assetClass={selected?.asset_class ?? "stock"} />
    </div>
  );
}

function StatsTable({
  stats,
  timeframe,
  loading,
  error,
  onRetry,
  selected,
  onSelect,
}: {
  stats: SymbolStats[];
  timeframe: Timeframe;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  selected: string;
  onSelect: (ticker: string) => void;
}) {
  return (
    <Panel
      title={`Bảng thông số dữ liệu (khung ${timeframeLabel(timeframe)})`}
      subtitle="Thống kê mô tả trên toàn bộ dữ liệu đã làm sạch trong market.ohlcv · bấm một dòng để xem biểu đồ"
      bodyClassName="max-h-[440px] overflow-auto"
    >
      {loading ? (
        <StateBox kind="loading" message="Đang tính thống kê…" />
      ) : error ? (
        <StateBox kind="error" message="Không tải được bảng thống kê" hint={error} onRetry={onRetry} />
      ) : stats.length === 0 ? (
        <StateBox kind="empty" message={`Chưa có dữ liệu khung ${timeframeLabel(timeframe)}`} />
      ) : (
        <table className="data-table whitespace-nowrap">
          <thead className="sticky top-0 z-10">
            <tr>
              <th>Mã</th>
              <th>Loại</th>
              <th className="text-right">Số nến</th>
              <th>Từ ngày – đến ngày</th>
              <th className="text-right">Giá thấp nhất</th>
              <th className="text-right">Giá cao nhất</th>
              <th className="text-right">Giá TB (± độ lệch)</th>
              <th className="text-right">Giá cuối</th>
              <th className="text-right">Thay đổi</th>
              <th className="text-right">KL trung bình</th>
              <th className="text-right">KL lớn nhất</th>
              <th className="text-right" title="Độ lệch chuẩn của lợi suất giữa hai nến liên tiếp">Độ biến động</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((s) => (
              <tr
                key={s.ticker}
                onClick={() => onSelect(s.ticker)}
                className={`cursor-pointer ${s.ticker === selected ? "!bg-accent/15" : ""}`}
              >
                <td className="font-bold text-white">{s.ticker}</td>
                <td><AssetBadge assetClass={s.asset_class} /></td>
                <td className="text-right font-mono">{formatNum(s.bars, 0)}</td>
                <td className="text-slate-400">{formatDate(s.first_ts)} – {formatDate(s.last_ts)}</td>
                <td className="text-right font-mono text-down">{formatPrice(s.lowest_low, s.asset_class)}</td>
                <td className="text-right font-mono text-up">{formatPrice(s.highest_high, s.asset_class)}</td>
                <td className="text-right font-mono">
                  {formatPrice(s.mean_close, s.asset_class)} <span className="text-slate-500">± {formatNum(s.std_close)}</span>
                </td>
                <td className="text-right font-mono text-white">{formatPrice(s.last_close, s.asset_class)}</td>
                <td className={`text-right font-mono ${(s.change_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}>{formatPct(s.change_pct)}</td>
                <td className="text-right font-mono">{formatVolume(s.mean_volume)}</td>
                <td className="text-right font-mono">{formatVolume(s.max_volume)}</td>
                <td className="text-right font-mono">{s.return_std_pct === null ? "—" : `${formatNum(s.return_std_pct)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

function IndicatorSidebar({ points, stats, timeframe }: { points: IndicatorPoint[]; stats?: SymbolStats; timeframe: Timeframe }) {
  const last = points[points.length - 1];
  const assetClass = stats?.asset_class ?? "stock";
  const insights = readIndicators(points);
  const high = points.length ? Math.max(...points.map((p) => p.high)) : null;
  const low = points.length ? Math.min(...points.map((p) => p.low)) : null;
  const change = points.length > 1 ? (points[points.length - 1].close / points[0].close - 1) * 100 : null;

  return (
    <div className="flex flex-col gap-6">
      <Panel title="Chỉ số tại nến gần nhất" subtitle={last ? formatDate(last.ts, timeframe === "1h") : undefined} bodyClassName="flex flex-col gap-2.5 p-4">
        <MetricRow label="Giá đóng cửa" value={formatPrice(last?.close, assetClass)} />
        <MetricRow label="SMA 20" value={formatPrice(last?.sma_20, assetClass)} />
        <MetricRow label="SMA 50" value={formatPrice(last?.sma_50, assetClass)} />
        <MetricRow label="RSI 14" value={formatNum(last?.rsi_14, 1)} note={rsiZone(last?.rsi_14 ?? null).label} />
        <MetricRow label="MACD / Signal" value={`${formatNum(last?.macd, 3)} / ${formatNum(last?.macd_signal, 3)}`} />
      </Panel>

      <Panel title="Trong cửa sổ đang xem" bodyClassName="flex flex-col gap-2.5 p-4">
        <MetricRow label="Cao nhất" value={formatPrice(high, assetClass)} />
        <MetricRow label="Thấp nhất" value={formatPrice(low, assetClass)} />
        <MetricRow
          label="Thay đổi"
          value={<span className={(change ?? 0) >= 0 ? "text-up" : "text-down"}>{formatPct(change)}</span>}
          note={`${points.length} nến`}
        />
      </Panel>

      <Panel title="Diễn giải tự động" bodyClassName="p-4">
        {insights.length === 0 ? (
          <p className="text-sm text-slate-400">Chưa đủ dữ liệu để diễn giải.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {insights.map((item) => (
              <li key={item.text} className={TONE_CLASS[item.tone]}>• {item.text}</li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-[11px] text-slate-500">Quy tắc phân tích kỹ thuật cơ bản, chỉ mang tính minh họa — không phải khuyến nghị đầu tư.</p>
      </Panel>
    </div>
  );
}

function RecentTable({ points, timeframe, assetClass }: { points: IndicatorPoint[]; timeframe: string; assetClass: string }) {
  if (points.length === 0) return null;
  const rows = [...points].reverse().slice(0, RECENT_ROWS);
  return (
    <Panel title={`Dữ liệu lịch sử — ${RECENT_ROWS} nến gần nhất`} subtitle="Giá OHLCV đã làm sạch kèm chỉ báo, mới nhất trước" bodyClassName="max-h-[520px] overflow-auto">
      <table className="data-table whitespace-nowrap">
        <thead className="sticky top-0">
          <tr>
            <th>Thời gian</th>
            <th className="text-right">Mở</th>
            <th className="text-right">Cao</th>
            <th className="text-right">Thấp</th>
            <th className="text-right">Đóng</th>
            <th className="text-right">Khối lượng</th>
            <th className="text-right">SMA 20</th>
            <th className="text-right">RSI 14</th>
            <th className="text-right">MACD</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.ts}>
              <td className="font-mono text-xs text-slate-400">{formatDate(p.ts, timeframe === "1h")}</td>
              <td className="text-right font-mono">{formatPrice(p.open, assetClass)}</td>
              <td className="text-right font-mono text-up">{formatPrice(p.high, assetClass)}</td>
              <td className="text-right font-mono text-down">{formatPrice(p.low, assetClass)}</td>
              <td className={`text-right font-mono font-semibold ${p.close >= p.open ? "text-up" : "text-down"}`}>{formatPrice(p.close, assetClass)}</td>
              <td className="text-right font-mono">{formatVolume(p.volume)}</td>
              <td className="text-right font-mono">{formatPrice(p.sma_20, assetClass)}</td>
              <td className="text-right font-mono">{formatNum(p.rsi_14, 1)}</td>
              <td className="text-right font-mono">{formatNum(p.macd, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}
