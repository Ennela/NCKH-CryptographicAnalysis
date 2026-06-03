"use client";

import { useEffect, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";

interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface ForecastData {
  time: string;
  value: number;
}

interface ChartProps {
  symbol: string;
  history: CandleData[];
  forecasts: ForecastData[];
}

export default function TechnicalChart({ symbol, history, forecasts }: ChartProps) {
  const [domLoaded, setDomLoaded] = useState(false);

  useEffect(() => {
    setDomLoaded(true);
  }, []);

  if (!domLoaded) {
    return <div className="h-[450px] w-full flex items-center justify-center bg-slate-900/50 rounded-xl">Loading chart canvas...</div>;
  }

  // Process data for ECharts candlestick format
  // Format: [open, close, lowest, highest]
  const dates = history.map(c => c.time);
  const data = history.map(c => [c.open, c.close, c.low, c.high]);

  // Handle forecast line drawing
  // We append forecast dates to the dates array
  const allDates = [...dates];
  const forecastSeriesData: (number | null)[] = history.map(() => null);
  
  // Make the last history close price connect to the first forecast price
  if (history.length > 0) {
    forecastSeriesData[history.length - 1] = history[history.length - 1].close;
  }

  forecasts.forEach(f => {
    allDates.push(f.time);
    forecastSeriesData.push(f.value);
  });

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "cross"
      },
      backgroundColor: "#151b2c",
      borderColor: "#1e293b",
      textStyle: {
        color: "#cbd5e1"
      }
    },
    legend: {
      data: ["Lịch sử nến giá (OHLC)", "Dự báo mô hình (Forecast)"],
      textStyle: {
        color: "#94a3b8"
      },
      top: 10
    },
    grid: {
      left: "5%",
      right: "5%",
      bottom: "15%",
      top: "12%"
    },
    xAxis: {
      type: "category",
      data: allDates,
      scale: true,
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#334155" } },
      axisLabel: { color: "#94a3b8" },
      splitLine: { show: false }
    },
    yAxis: {
      scale: true,
      axisLine: { lineStyle: { color: "#334155" } },
      axisLabel: { color: "#94a3b8" },
      splitLine: { lineStyle: { color: "#1e293b", type: "dashed" } }
    },
    dataZoom: [
      {
        type: "inside",
        start: 70,
        end: 100
      },
      {
        show: true,
        type: "slider",
        top: "90%",
        start: 70,
        end: 100,
        textStyle: {
          color: "#94a3b8"
        }
      }
    ],
    series: [
      {
        name: "Lịch sử nến giá (OHLC)",
        type: "candlestick",
        data: data,
        itemStyle: {
          color: "#10b981",       // green for up
          color0: "#f43f5e",      // red for down
          borderColor: "#10b981",
          borderColor0: "#f43f5e"
        }
      },
      {
        name: "Dự báo mô hình (Forecast)",
        type: "line",
        data: forecastSeriesData,
        smooth: true,
        showSymbol: true,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: {
          color: "#6366f1",
          width: 3,
          type: "dashed"
        },
        itemStyle: {
          color: "#6366f1"
        }
      }
    ]
  };

  return (
    <div className="w-full glass-card p-6 rounded-xl border border-darkBorder">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold tracking-wide text-slate-200">Biểu Đồ Phân Tích Kỹ Thuật: {symbol}</h3>
        <span className="text-xs font-semibold px-2.5 py-1 rounded bg-indigo-500/10 text-glowIndigo border border-indigo-500/20">ECharts Engine</span>
      </div>
      <ReactECharts option={option} style={{ height: "450px", width: "100%" }} />
    </div>
  );
}
