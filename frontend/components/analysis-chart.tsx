"use client";

import EChart, { CHART_THEME } from "@/components/echart";
import type { IndicatorPoint } from "@/lib/api";
import { formatAxisTime } from "@/lib/format";

/**
 * Four stacked panes sharing one time axis and one zoom:
 * 1) candlesticks + SMA 20/50, 2) volume, 3) RSI 14 with 30/70 bands,
 * 4) MACD line, signal line and histogram.
 */
export default function AnalysisChart({ points, timeframe }: { points: IndicatorPoint[]; timeframe: string }) {
  const labels = points.map((p) => formatAxisTime(p.ts, timeframe));
  const candles = points.map((p) => [p.open, p.close, p.low, p.high]);
  const volumes = points.map((p) => ({
    value: p.volume,
    itemStyle: { color: p.close >= p.open ? "rgba(16,185,129,0.55)" : "rgba(244,63,94,0.55)" },
  }));
  const hist = points.map((p) => ({
    value: p.macd_hist,
    itemStyle: { color: (p.macd_hist ?? 0) >= 0 ? "#10B981" : "#F43F5E" },
  }));

  // Pane layout (percent of height): price 0–46, volume 50–60, RSI 65–78, MACD 83–94.
  const grids = [
    { left: 64, right: 24, top: "4%", height: "42%" },
    { left: 64, right: 24, top: "50%", height: "10%" },
    { left: 64, right: 24, top: "65%", height: "13%" },
    { left: 64, right: 24, top: "83%", height: "11%" },
  ];
  const xAxes = grids.map((_, index) => ({
    type: "category",
    gridIndex: index,
    data: labels,
    boundaryGap: true,
    axisLine: CHART_THEME.axisLine,
    axisLabel: { ...CHART_THEME.axisLabel, show: index === grids.length - 1 },
    axisTick: { show: false },
  }));
  const yAxis = (gridIndex: number, name: string, extra: object = {}) => ({
    type: "value",
    gridIndex,
    scale: true,
    name,
    nameTextStyle: { color: "#94A3B8", fontSize: 11, align: "left" },
    splitNumber: 2,
    axisLine: CHART_THEME.axisLine,
    axisLabel: CHART_THEME.axisLabel,
    splitLine: CHART_THEME.splitLine,
    ...extra,
  });

  const option = {
    backgroundColor: "transparent",
    animation: false,
    legend: {
      top: 0,
      right: 24,
      textStyle: { color: "#CBD5E1", fontSize: 11 },
      data: ["Nến OHLC", "SMA 20", "SMA 50", "RSI 14", "MACD", "Signal"],
    },
    tooltip: { trigger: "axis", axisPointer: { type: "cross" }, ...CHART_THEME.tooltip },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: grids,
    xAxis: xAxes,
    yAxis: [
      yAxis(0, "Giá"),
      yAxis(1, "KL", { axisLabel: { ...CHART_THEME.axisLabel, formatter: (v: number) => compact(v) } }),
      yAxis(2, "RSI", { min: 0, max: 100, scale: false }),
      yAxis(3, "MACD"),
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1, 2, 3], start: 40, end: 100 },
      { type: "slider", xAxisIndex: [0, 1, 2, 3], start: 40, end: 100, bottom: 0, height: 18, borderColor: "#475569", textStyle: { color: "#94A3B8" } },
    ],
    series: [
      {
        name: "Nến OHLC",
        type: "candlestick",
        data: candles,
        itemStyle: { color: "#10B981", color0: "#F43F5E", borderColor: "#10B981", borderColor0: "#F43F5E" },
      },
      line("SMA 20", points.map((p) => p.sma_20), "#3B82F6", 0),
      line("SMA 50", points.map((p) => p.sma_50), "#F59E0B", 0),
      { name: "Khối lượng", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: volumes },
      {
        ...line("RSI 14", points.map((p) => p.rsi_14), "#A78BFA", 2),
        markLine: {
          silent: true,
          symbol: "none",
          label: { color: "#94A3B8", fontSize: 10 },
          lineStyle: { color: "#64748B", type: "dashed" },
          data: [{ yAxis: 70 }, { yAxis: 30 }],
        },
      },
      { name: "Histogram", type: "bar", xAxisIndex: 3, yAxisIndex: 3, data: hist },
      line("MACD", points.map((p) => p.macd), "#3B82F6", 3),
      line("Signal", points.map((p) => p.macd_signal), "#F59E0B", 3),
    ],
  };

  return <EChart option={option} notMerge style={{ height: "100%", width: "100%" }} />;
}

function line(name: string, data: (number | null)[], color: string, pane: number) {
  return {
    name,
    type: "line",
    xAxisIndex: pane,
    yAxisIndex: pane,
    data,
    showSymbol: false,
    connectNulls: false,
    lineStyle: { color, width: 1.5 },
    itemStyle: { color },
  };
}

function compact(value: number): string {
  if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(0)}K`;
  return String(value);
}
