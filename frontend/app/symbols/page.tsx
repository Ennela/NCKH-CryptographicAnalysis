"use client";

import { useState } from "react";
import { Search, Sliders, Calendar, ArrowDownWideNarrow } from "lucide-react";

export default function SymbolsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState("BTC/USDT");

  const symbols = [
    { id: "BTC/USDT", name: "Bitcoin / Tether", type: "crypto", exchange: "Binance" },
    { id: "ETH/USDT", name: "Ethereum / Tether", type: "crypto", exchange: "Binance" },
    { id: "FPT", name: "Công ty Cổ phần FPT", type: "stock", exchange: "HOSE" },
    { id: "VCB", name: "Ngân hàng Vietcombank", type: "stock", exchange: "HOSE" },
    { id: "MSN", name: "Tập đoàn Masan", type: "stock", exchange: "HOSE" },
  ];

  // Mock historical data candles based on selection
  const mockCandles = [
    { time: "2026-06-03 14:00", open: 68120.5, high: 68350.0, low: 68080.0, close: 68250.0, volume: 1540.2 },
    { time: "2026-06-03 13:00", open: 68290.0, high: 68410.0, low: 68050.0, close: 68120.5, volume: 1220.5 },
    { time: "2026-06-03 12:00", open: 67980.2, high: 68340.0, low: 67900.0, close: 68290.0, volume: 2110.8 },
    { time: "2026-06-03 11:00", open: 68050.0, high: 68150.0, low: 67880.0, close: 67980.2, volume: 980.4 },
    { time: "2026-06-03 10:00", open: 68200.4, high: 68400.0, low: 68010.5, close: 68050.0, volume: 1730.1 },
    { time: "2026-06-03 09:00", open: 68100.0, high: 68380.0, low: 68000.0, close: 68200.4, volume: 1450.9 },
  ];

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
              {symbols.map((sym) => (
                <button
                  key={sym.id}
                  onClick={() => setSelectedSymbol(sym.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                    selectedSymbol === sym.id
                      ? "bg-glowIndigo/15 text-glowIndigo border border-glowIndigo/20"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 border border-transparent"
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <span className="font-bold">{sym.id}</span>
                    <span className="text-[10px] uppercase font-semibold text-slate-500">{sym.type}</span>
                  </div>
                  <span className="text-xs text-slate-500 block truncate">{sym.name}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* History Table logs */}
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
            </div>
          </div>

          <div className="glass-panel rounded-xl border border-darkBorder overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-darkBorder bg-slate-900/40 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Thời Gian</th>
                  <th className="py-3 px-4">Open</th>
                  <th className="py-3 px-4">High</th>
                  <th className="py-3 px-4">Low</th>
                  <th className="py-3 px-4">Close</th>
                  <th className="py-3 px-4 text-right">Volume</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-darkBorder/30">
                {mockCandles.map((candle, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/10 text-sm text-slate-300">
                    <td className="py-3 px-4 text-slate-500 font-mono text-xs">{candle.time}</td>
                    <td className="py-3 px-4">{candle.open.toLocaleString()}</td>
                    <td className="py-3 px-4 text-glowEmerald">{candle.high.toLocaleString()}</td>
                    <td className="py-3 px-4 text-glowRose">{candle.low.toLocaleString()}</td>
                    <td className="py-3 px-4 font-semibold">{candle.close.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right text-slate-400 font-mono text-xs">{candle.volume.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
