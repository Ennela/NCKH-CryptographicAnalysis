"use client";

import { useState, useEffect, useCallback } from "react";
import { Calendar, ArrowDownWideNarrow, Loader2, AlertCircle, Database } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "generate_a_secure_long_random_string_here";

interface SymbolInfo {
  ticker: string;
  asset_class: string;
  exchange_code: string;
  company_name: string | null;
}

interface CandleRow {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export default function SymbolsPage() {
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>("");
  const [candles, setCandles] = useState<CandleRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [symbolsLoading, setSymbolsLoading] = useState(true);

  // Fetch symbol list on mount
  useEffect(() => {
    async function fetchSymbols() {
      try {
        const res = await fetch(`${API_URL}/api/v1/symbols`, {
          headers: { "X-API-Key": API_KEY },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: SymbolInfo[] = await res.json();
        setSymbols(data);
        if (data.length > 0) {
          setSelectedSymbol(data[0].ticker);
        }
      } catch (err) {
        console.error("Failed to load symbols:", err);
        // Fallback to hardcoded list when API is unavailable
        const fallback: SymbolInfo[] = [
          { ticker: "BTCUSDT", asset_class: "crypto", exchange_code: "BINANCE", company_name: null },
          { ticker: "FPT", asset_class: "stock", exchange_code: "HOSE", company_name: "Công ty Cổ phần FPT" },
        ];
        setSymbols(fallback);
        setSelectedSymbol(fallback[0].ticker);
      } finally {
        setSymbolsLoading(false);
      }
    }
    fetchSymbols();
  }, []);

  // Fetch OHLCV when selected symbol changes
  const fetchOHLCV = useCallback(async (ticker: string) => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    setCandles([]);

    // Determine timeframe from asset class
    const sym = symbols.find((s) => s.ticker === ticker);
    const timeframe = sym?.asset_class === "crypto" ? "1h" : "1d";

    try {
      const params = new URLSearchParams({
        ticker,
        timeframe,
        limit: "50",
      });
      const res = await fetch(`${API_URL}/api/v1/ohlcv?${params}`, {
        headers: { "X-API-Key": API_KEY },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const data: CandleRow[] = await res.json();
      setCandles(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Lỗi kết nối API";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [symbols]);

  useEffect(() => {
    if (selectedSymbol && symbols.length > 0) {
      fetchOHLCV(selectedSymbol);
    }
  }, [selectedSymbol, symbols, fetchOHLCV]);

  /**
   * Format timestamp for display.
   * Trims ISO string to readable local format.
   */
  function formatTs(isoStr: string): string {
    const d = new Date(isoStr);
    return d.toLocaleString("vi-VN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Ho_Chi_Minh",
    });
  }

  /** Format number with locale grouping. */
  function formatNum(val: number, decimals: number = 2): string {
    return val.toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-200">Truy Vấn Lịch Sử Nến Giá</h1>
        <p className="text-slate-500 text-sm mt-1">
          Dữ liệu giá OHLCV thô thu thập định kỳ từ thư viện vnstock và API CCXT/Binance.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        {/* Sidebar Selector */}
        <div className="lg:col-span-1 space-y-4">
          <div className="glass-panel p-4 rounded-xl border border-darkBorder space-y-4">
            <h3 className="text-sm font-semibold uppercase text-slate-400 tracking-wider">Danh Sách Mã</h3>
            <div className="space-y-1">
              {symbolsLoading ? (
                <div className="flex items-center gap-2 text-slate-500 text-sm py-4 justify-center">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Đang tải...</span>
                </div>
              ) : (
                symbols.map((sym) => (
                  <button
                    key={sym.ticker}
                    onClick={() => setSelectedSymbol(sym.ticker)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-all ${selectedSymbol === sym.ticker
                        ? "bg-glowIndigo/15 text-glowIndigo border border-glowIndigo/20"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 border border-transparent"
                      }`}
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-bold">{sym.ticker}</span>
                      <span className="text-[10px] uppercase font-semibold text-slate-500">{sym.asset_class}</span>
                    </div>
                    <span className="text-xs text-slate-500 block truncate">
                      {sym.company_name || `${sym.exchange_code}`}
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>

        {/* History Table */}
        <div className="lg:col-span-3 space-y-4">
          <div className="flex flex-col sm:flex-row gap-4 justify-between items-start sm:items-center">
            <h3 className="text-lg font-bold tracking-tight text-slate-300">Dữ Liệu OHLCV: {selectedSymbol}</h3>

            <div className="flex gap-2">
              <span className="text-xs px-2.5 py-1 rounded bg-slate-800 text-slate-400 border border-darkBorder flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5" /> UTC Time
              </span>
              <span className="text-xs px-2.5 py-1 rounded bg-slate-800 text-slate-400 border border-darkBorder flex items-center gap-1">
                <ArrowDownWideNarrow className="w-3.5 h-3.5" /> Mới Nhất
              </span>
              {candles.length > 0 && (
                <span className="text-xs px-2.5 py-1 rounded bg-glowIndigo/10 text-glowIndigo border border-glowIndigo/20 flex items-center gap-1">
                  <Database className="w-3.5 h-3.5" /> {candles.length} nến
                </span>
              )}
            </div>
          </div>

          {/* Loading State */}
          {loading && (
            <div className="glass-panel rounded-xl border border-darkBorder p-12 flex flex-col items-center justify-center gap-3">
              <Loader2 className="w-8 h-8 text-glowIndigo animate-spin" />
              <span className="text-slate-400 text-sm">Đang truy vấn dữ liệu {selectedSymbol}...</span>
            </div>
          )}

          {/* Error State */}
          {error && !loading && (
            <div className="glass-panel rounded-xl border border-red-500/20 p-8 flex flex-col items-center gap-3">
              <AlertCircle className="w-8 h-8 text-glowRose" />
              <span className="text-glowRose font-semibold text-sm">Không thể tải dữ liệu</span>
              <span className="text-slate-500 text-xs text-center max-w-md">{error}</span>
              <button
                onClick={() => fetchOHLCV(selectedSymbol)}
                className="mt-2 px-4 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs border border-darkBorder hover:bg-slate-700 transition-all"
              >
                Thử lại
              </button>
            </div>
          )}

          {/* Empty State */}
          {!loading && !error && candles.length === 0 && (
            <div className="glass-panel rounded-xl border border-darkBorder p-12 flex flex-col items-center gap-3">
              <Database className="w-8 h-8 text-slate-600" />
              <span className="text-slate-500 text-sm">Chưa có dữ liệu OHLCV cho mã {selectedSymbol}.</span>
              <span className="text-slate-600 text-xs">Hãy chạy ingestion service để thu thập dữ liệu.</span>
            </div>
          )}

          {/* Data Table */}
          {!loading && !error && candles.length > 0 && (
            <div className="glass-panel rounded-xl border border-darkBorder overflow-hidden">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-darkBorder bg-slate-900/40 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                    <th className="py-3 px-4">Thời Gian</th>
                    <th className="py-3 px-4">Giá Mở cửa (O)</th>
                    <th className="py-3 px-4">Giá Cao nhất (H)</th>
                    <th className="py-3 px-4">Giá Thấp nhất (L)</th>
                    <th className="py-3 px-4">Giá Đóng cửa (C)</th>
                    <th className="py-3 px-4 text-right">Khối lượng giao dịch (V)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-darkBorder/30">
                  {candles.map((candle, idx) => {
                    const isUp = candle.close >= candle.open;
                    return (
                      <tr key={idx} className="hover:bg-slate-800/10 text-sm text-slate-300">
                        <td className="py-3 px-4 text-slate-500 font-mono text-xs">{formatTs(candle.ts)}</td>
                        <td className="py-3 px-4">{formatNum(candle.open)}</td>
                        <td className="py-3 px-4 text-glowEmerald">{formatNum(candle.high)}</td>
                        <td className="py-3 px-4 text-glowRose">{formatNum(candle.low)}</td>
                        <td className={`py-3 px-4 font-semibold ${isUp ? "text-glowEmerald" : "text-glowRose"}`}>
                          {formatNum(candle.close)}
                        </td>
                        <td className="py-3 px-4 text-right text-slate-400 font-mono text-xs">
                          {formatNum(candle.volume, 4)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
