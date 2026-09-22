"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { ArrowUpRight, Database, Brain, Activity, Bitcoin, AlertCircle, Loader2 } from "lucide-react";
import {
  fetchSymbols,
  fetchOhlcv,
  fetchModels,
  timeframeForAssetClass,
  type SymbolInfo,
  type ModelInfo,
} from "@/lib/api";

/** Number of symbols to enrich with latest close price on the dashboard. */
const MAX_QUOTE_ROWS = 8;

interface QuoteRow extends SymbolInfo {
  lastClose: number | null;
  lastTs: string | null;
  changePct: number | null;
}

/** Format number with locale grouping. */
function formatNum(val: number, decimals: number = 2): string {
  return val.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** Format the latest close per asset class (USD quote for crypto, VND for stocks). */
function formatPrice(row: QuoteRow): string {
  if (row.lastClose === null) return "—";
  return row.asset_class === "crypto" ? `$${formatNum(row.lastClose)}` : `${formatNum(row.lastClose, 0)} đ`;
}

export default function Dashboard() {
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [quotes, setQuotes] = useState<QuoteRow[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [quotesLoading, setQuotesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelsError, setModelsError] = useState<boolean>(false);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    setModelsError(false);
    try {
      // Models are fetched best-effort: a registry outage should not hide the symbol list.
      const [symbolData, modelData] = await Promise.all([
        fetchSymbols(),
        fetchModels().catch(() => {
          setModelsError(true);
          return [] as ModelInfo[];
        }),
      ]);
      setSymbols(symbolData);
      setModels(modelData);
      setLoading(false);

      // Enrich the first N symbols with their latest close (2 candles → real change %).
      const head = symbolData.slice(0, MAX_QUOTE_ROWS);
      setQuotesLoading(true);
      const enriched = await Promise.all(
        head.map(async (sym): Promise<QuoteRow> => {
          try {
            const candles = await fetchOhlcv(sym.ticker, timeframeForAssetClass(sym.asset_class), 2);
            const latest = candles[0] ?? null;
            const prev = candles[1] ?? null;
            return {
              ...sym,
              lastClose: latest ? latest.close : null,
              lastTs: latest ? latest.ts : null,
              changePct: latest && prev && prev.close !== 0 ? ((latest.close - prev.close) / prev.close) * 100 : null,
            };
          } catch {
            return { ...sym, lastClose: null, lastTs: null, changePct: null };
          }
        })
      );
      setQuotes(enriched);
      setQuotesLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi kết nối API");
      setLoading(false);
      setQuotesLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const stockCount = symbols.filter((s) => s.asset_class === "stock").length;
  const cryptoCount = symbols.filter((s) => s.asset_class === "crypto").length;

  const stats = [
    {
      label: "Mã Theo Dõi",
      value: String(symbols.length),
      description: `${stockCount} Cổ phiếu VN + ${cryptoCount} Crypto`,
      icon: Database,
      color: "text-glowIndigo",
    },
    {
      label: "Cổ Phiếu VN",
      value: String(stockCount),
      description: "Thu thập từ vnstock (khung 1 ngày)",
      icon: Activity,
      color: "text-amber-400",
    },
    {
      label: "Crypto",
      value: String(cryptoCount),
      description: "Thu thập từ Binance (khung 1 giờ)",
      icon: Bitcoin,
      color: "text-glowRose",
    },
    {
      label: "Mô Hình Đã Đăng Ký",
      value: modelsError ? "—" : String(models.length),
      description: modelsError
        ? "Không tải được từ MLflow Registry"
        : models.length > 0
          ? models.map((m) => m.model_name).join(", ")
          : "Chưa có mô hình trong MLflow Registry",
      icon: Brain,
      color: "text-glowEmerald",
    },
  ];

  return (
    <div className="space-y-10 animate-fade-in">
      {/* Hero Welcome banner */}
      <section className="glass-panel p-8 md:p-12 rounded-2xl border border-darkBorder flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
        <div className="space-y-4 max-w-2xl">
          <h1 className="text-3xl md:text-5xl font-extrabold tracking-tight bg-gradient-to-r from-glowIndigo to-glowEmerald bg-clip-text text-transparent">
            Hệ Thống Phân Tích & Dự Báo Giá
          </h1>
          <p className="text-slate-400 text-sm md:text-base leading-relaxed">
            Dự án nghiên cứu xây dựng pipeline tự động thu thập dữ liệu giá OHLCV thị trường Tài chính & Crypto,
            huấn luyện mô hình học sâu chuỗi thời gian, và giải thích quyết định dự báo dựa trên SHAP.
          </p>
        </div>
        <div className="flex gap-4">
          <Link href="/forecast" className="px-6 py-3 rounded-xl bg-glowIndigo text-white font-semibold shadow-lg shadow-glowIndigo/20 hover:bg-glowIndigo/80 hover:shadow-glowIndigo/35 transition-all">
            Chạy Dự Báo
          </Link>
          <Link href="/symbols" className="px-6 py-3 rounded-xl bg-slate-800 border border-slate-700 hover:bg-slate-700/50 transition-all text-slate-300 font-semibold">
            Xem Bảng Giá
          </Link>
        </div>
      </section>

      {/* Error State */}
      {error && !loading && (
        <section className="glass-panel rounded-xl border border-red-500/20 p-8 flex flex-col items-center gap-3">
          <AlertCircle className="w-8 h-8 text-glowRose" />
          <span className="text-glowRose font-semibold text-sm">Không thể kết nối tới Inference API</span>
          <span className="text-slate-500 text-xs text-center max-w-md">{error}</span>
          <button
            onClick={loadDashboard}
            className="mt-2 px-4 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs border border-darkBorder hover:bg-slate-700 transition-all"
          >
            Thử lại
          </button>
        </section>
      )}

      {/* Stats Cards Section */}
      {!error && (
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {loading
            ? Array.from({ length: 4 }).map((_, idx) => (
                <div key={idx} className="glass-card p-6 rounded-xl border border-darkBorder h-36 animate-pulse space-y-4">
                  <div className="h-3 w-24 bg-slate-800 rounded" />
                  <div className="h-8 w-16 bg-slate-800 rounded" />
                  <div className="h-3 w-32 bg-slate-800 rounded" />
                </div>
              ))
            : stats.map((stat, idx) => {
                const Icon = stat.icon;
                return (
                  <div key={idx} className="glass-card p-6 rounded-xl border border-darkBorder flex flex-col justify-between h-36">
                    <div className="flex justify-between items-start">
                      <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{stat.label}</span>
                      <Icon className={`w-5 h-5 ${stat.color}`} />
                    </div>
                    <div className="mt-2">
                      <span className="text-3xl font-bold tracking-tight text-slate-100">{stat.value}</span>
                      <p className="text-slate-500 text-xs mt-1 truncate" title={stat.description}>{stat.description}</p>
                    </div>
                  </div>
                );
              })}
        </section>
      )}

      {/* Symbols Table list */}
      {!error && (
        <section className="space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-xl md:text-2xl font-bold tracking-tight text-slate-200">Danh Sách Mã Giá Giám Sát</h2>
            <Link href="/symbols" className="text-glowIndigo hover:text-glowIndigo/80 text-sm flex items-center gap-1">
              Xem tất cả <ArrowUpRight className="w-4 h-4" />
            </Link>
          </div>

          <div className="glass-panel rounded-xl border border-darkBorder overflow-hidden">
            {loading || quotesLoading ? (
              <div className="p-12 flex flex-col items-center justify-center gap-3">
                <Loader2 className="w-8 h-8 text-glowIndigo animate-spin" />
                <span className="text-slate-400 text-sm">Đang tải dữ liệu giá mới nhất...</span>
              </div>
            ) : quotes.length === 0 ? (
              <div className="p-12 flex flex-col items-center gap-3">
                <Database className="w-8 h-8 text-slate-600" />
                <span className="text-slate-500 text-sm">Chưa có mã tài sản nào trong hệ thống.</span>
                <span className="text-slate-600 text-xs">Hãy chạy ingestion service để đăng ký và thu thập dữ liệu.</span>
              </div>
            ) : (
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-darkBorder bg-slate-900/40 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                    <th className="py-4 px-6">Mã Tài Sản</th>
                    <th className="py-4 px-6">Tên</th>
                    <th className="py-4 px-6">Loại</th>
                    <th className="py-4 px-6">Sàn Giao Dịch</th>
                    <th className="py-4 px-6">Giá Đóng Cửa Gần Nhất</th>
                    <th className="py-4 px-6 text-right">Biến Động Phiên Gần Nhất</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-darkBorder/40">
                  {quotes.map((sym) => (
                    <tr key={sym.ticker} className="hover:bg-slate-800/25 transition-all text-sm text-slate-300">
                      <td className="py-4 px-6 font-bold text-glowIndigo">{sym.ticker}</td>
                      <td className="py-4 px-6 text-slate-400">{sym.company_name || "—"}</td>
                      <td className="py-4 px-6">
                        <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                          sym.asset_class === "crypto"
                            ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                            : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                        }`}>
                          {sym.asset_class === "crypto" ? "Crypto" : "Stock"}
                        </span>
                      </td>
                      <td className="py-4 px-6 text-xs text-slate-500">{sym.exchange_code}</td>
                      <td className="py-4 px-6 font-semibold">{formatPrice(sym)}</td>
                      <td
                        className={`py-4 px-6 text-right font-semibold ${
                          sym.changePct === null
                            ? "text-slate-500"
                            : sym.changePct >= 0
                              ? "text-glowEmerald"
                              : "text-glowRose"
                        }`}
                      >
                        {sym.changePct === null ? "—" : `${sym.changePct >= 0 ? "+" : ""}${formatNum(sym.changePct)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
