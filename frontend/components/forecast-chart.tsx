"use client";

import EChart, { CHART_THEME } from "@/components/echart";

export interface PricePoint {
  label: string;
  value: number;
}

/**
 * "Biểu đồ dự đoán" from the mockup: actual close as a solid blue line and
 * the model forecast as a dashed amber line that starts at the last close.
 */
export default function ForecastChart({ history, forecast }: { history: PricePoint[]; forecast: PricePoint[] }) {
  const labels = [...history.map((p) => p.label), ...forecast.map((p) => p.label)];
  const actual = [...history.map((p) => p.value), ...forecast.map(() => null)];
  const predicted: (number | null)[] = history.map(() => null);
  if (history.length > 0 && forecast.length > 0) {
    predicted[history.length - 1] = history[history.length - 1].value;
  }
  predicted.push(...forecast.map((p) => p.value));

  const option = {
    backgroundColor: "transparent",
    animationDuration: 400,
    tooltip: { trigger: "axis", ...CHART_THEME.tooltip },
    grid: { left: 60, right: 24, top: 20, bottom: 70 },
    xAxis: {
      type: "category",
      data: labels,
      boundaryGap: false,
      axisLine: CHART_THEME.axisLine,
      axisLabel: CHART_THEME.axisLabel,
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLine: CHART_THEME.axisLine,
      axisLabel: CHART_THEME.axisLabel,
      splitLine: CHART_THEME.splitLine,
    },
    dataZoom: [
      { type: "inside", start: 55, end: 100 },
      { type: "slider", start: 55, end: 100, bottom: 16, height: 22, textStyle: { color: "#94A3B8" }, borderColor: "#475569" },
    ],
    series: [
      {
        name: "Giá thực tế",
        type: "line",
        data: actual,
        showSymbol: false,
        lineStyle: { color: "#3B82F6", width: 2 },
        itemStyle: { color: "#3B82F6" },
        areaStyle: { color: "rgba(59,130,246,0.08)" },
      },
      {
        name: "Giá AI dự báo",
        type: "line",
        data: predicted,
        showSymbol: true,
        symbolSize: 6,
        connectNulls: false,
        lineStyle: { color: "#F59E0B", width: 2.5, type: "dashed" },
        itemStyle: { color: "#F59E0B" },
      },
    ],
  };

  return <EChart option={option} notMerge style={{ height: "100%", width: "100%" }} />;
}

/** HTML legend identical to the mockup's `.legend` block. */
export function ForecastLegend() {
  return (
    <div className="flex w-fit items-center gap-5 rounded-lg bg-inset px-4 py-3 text-sm text-slate-300">
      <span className="flex items-center gap-2">
        <span className="inline-block h-[3px] w-7 rounded bg-accentSoft" /> Giá thực tế
      </span>
      <span className="flex items-center gap-2">
        <span className="inline-block w-7 border-t-[3px] border-dashed border-forecast" /> Giá AI dự báo
      </span>
    </div>
  );
}
