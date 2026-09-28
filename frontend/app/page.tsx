"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, ArrowRight, Brain, Database, DownloadCloud, Eraser, LineChart, Sparkles } from "lucide-react";
import {
  describeApiError,
  fetchJobs,
  fetchModels,
  fetchStats,
  type JobLogEntry,
  type ModelInfo,
  type SymbolStats,
} from "@/lib/api";
import { formatDate, formatNum, formatPct, formatPrice } from "@/lib/format";
import { AssetBadge, PageHeader, Panel, StatCard, StateBox } from "@/components/ui";

const FLOW = [
  { href: "/pipeline", icon: DownloadCloud, title: "1. Thu thập", text: "Celery Beat gọi vnstock (cổ phiếu VN) và Binance (crypto) theo lịch, lưu thô vào market.ohlcv_raw." },
  { href: "/pipeline", icon: Eraser, title: "2. Làm sạch", text: "Chuẩn hóa UTC, loại trùng, điền phiên thiếu, gắn cờ outlier IQR → market.ohlcv." },
  { href: "/analysis", icon: LineChart, title: "3. Phân tích", text: "Thống kê mô tả, nến + SMA, khối lượng, RSI, MACD cho từng mã." },
  { href: "/forecast", icon: Sparkles, title: "4. Dự báo", text: "ARIMA, XGBoost, Random Forest, GRU từ MLflow Registry, so với baseline Naive." },
];

export default function OverviewPage() {
  const [daily, setDaily] = useState<SymbolStats[]>([]);
  const [hourly, setHourly] = useState<SymbolStats[]>([]);
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [jobs, setJobs] = useState<JobLogEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Registry and job log are best-effort: an MLflow outage must not hide market data.
      const [d, h, m, j] = await Promise.all([
        fetchStats("1d"),
        fetchStats("1h"),
        fetchModels().catch(() => null),
        fetchJobs(20).catch(() => null),
      ]);
      setDaily(d);
      setHourly(h);
      setModels(m);
      setJobs(j);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const tickers = new Set([...daily, ...hourly].map((s) => s.ticker));
  const stockCount = new Set([...daily, ...hourly].filter((s) => s.asset_class === "stock").map((s) => s.ticker)).size;
  const totalBars = [...daily, ...hourly].reduce((sum, s) => sum + s.bars, 0);
  const finishedJobs = (jobs ?? []).filter((j) => j.status === "success" || j.status === "failed");
  const jobSuccess = finishedJobs.length
    ? (100 * finishedJobs.filter((j) => j.status === "success").length) / finishedJobs.length
    : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tổng quan hệ thống"
        description="Hệ thống thu thập, làm sạch, phân tích và dự báo giá cổ phiếu Việt Nam và tiền mã hóa — mọi số liệu dưới đây đọc trực tiếp từ cơ sở dữ liệu qua Inference API."
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {FLOW.map(({ href, icon: Icon, title, text }) => (
          <Link key={title} href={href} className="panel group flex flex-col gap-2 p-4 transition-colors hover:border-accentSoft">
            <div className="flex items-center justify-between text-white">
              <span className="flex items-center gap-2 font-semibold">
                <Icon className="h-5 w-5 text-accentSoft" /> {title}
              </span>
              <ArrowRight className="h-4 w-4 text-slate-500 transition-transform group-hover:translate-x-1 group-hover:text-accentSoft" />
            </div>
            <p className="text-xs leading-relaxed text-slate-400">{text}</p>
          </Link>
        ))}
      </div>

      {error ? (
        <Panel>
          <StateBox kind="error" message="Không tải được dữ liệu tổng quan" hint={error} onRetry={load} />
        </Panel>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Mã theo dõi"
              value={loading ? "…" : String(tickers.size)}
              hint={`${stockCount} cổ phiếu VN · ${tickers.size - stockCount} crypto`}
              icon={<Database className="h-5 w-5 text-accentSoft" />}
            />
            <StatCard
              label="Nến đã lưu (đã làm sạch)"
              value={loading ? "…" : formatNum(totalBars, 0)}
              hint={`${formatNum(daily.reduce((s, x) => s + x.bars, 0), 0)} nến 1 ngày · ${formatNum(hourly.reduce((s, x) => s + x.bars, 0), 0)} nến 1 giờ`}
              icon={<Activity className="h-5 w-5 text-up" />}
            />
            <StatCard
              label="Mô hình đã đăng ký"
              value={loading ? "…" : models ? String(models.length) : "—"}
              hint={models ? "Trong MLflow Model Registry" : "Không kết nối được MLflow"}
              icon={<Brain className="h-5 w-5 text-forecast" />}
            />
            <StatCard
              label="Job thành công (20 gần nhất)"
              value={loading ? "…" : jobSuccess === null ? "—" : `${formatNum(jobSuccess, 0)}%`}
              hint={jobs === null ? "Không đọc được ops.job_log" : `${finishedJobs.length} job đã kết thúc`}
              icon={<DownloadCloud className="h-5 w-5 text-purple-300" />}
            />
          </div>

          <Panel
            title="Bảng giá các mã (khung 1 ngày)"
            subtitle="Giá đóng cửa gần nhất, biên độ cao/thấp và mức thay đổi trên toàn bộ lịch sử đã thu thập"
            bodyClassName="overflow-x-auto"
            actions={
              <Link href="/analysis" className="btn-secondary">
                Phân tích chi tiết <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            }
          >
            {loading ? (
              <StateBox kind="loading" message="Đang tải thống kê…" />
            ) : daily.length === 0 ? (
              <StateBox kind="empty" message="Chưa có dữ liệu khung 1 ngày" hint="Chạy import snapshot hoặc ingestion để nạp dữ liệu." />
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Mã</th>
                    <th>Loại</th>
                    <th className="text-right">Giá cuối</th>
                    <th>Cập nhật</th>
                    <th className="text-right">Thấp nhất</th>
                    <th className="text-right">Cao nhất</th>
                    <th className="text-right">Thay đổi toàn kỳ</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {daily.map((s) => (
                    <tr key={s.ticker}>
                      <td className="font-bold text-white">{s.ticker}</td>
                      <td><AssetBadge assetClass={s.asset_class} /></td>
                      <td className="text-right font-mono">{formatPrice(s.last_close, s.asset_class)}</td>
                      <td className="text-slate-400">{formatDate(s.last_ts)}</td>
                      <td className="text-right font-mono text-down">{formatPrice(s.lowest_low, s.asset_class)}</td>
                      <td className="text-right font-mono text-up">{formatPrice(s.highest_high, s.asset_class)}</td>
                      <td className={`text-right font-mono ${(s.change_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}>{formatPct(s.change_pct)}</td>
                      <td className="text-right">
                        <Link href={`/analysis?ticker=${s.ticker}&timeframe=1d`} className="text-xs text-accentSoft hover:underline">
                          Xem biểu đồ
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
          <p className="text-xs text-slate-500">
            Giá cổ phiếu VN tính theo nghìn đồng (đơn vị của nguồn vnstock); giá crypto tính theo USDT.
          </p>
        </>
      )}
    </div>
  );
}
