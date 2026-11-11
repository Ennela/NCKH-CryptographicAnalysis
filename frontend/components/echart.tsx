"use client";

import dynamic from "next/dynamic";

/**
 * ECharts renders into a canvas that only exists in the browser, so the
 * component is loaded client-side only (avoids hydration mismatches).
 */
const EChart = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse rounded bg-inset" />,
});

export default EChart;

/** Shared axis/tooltip styling matching the slate palette. */
export const CHART_THEME = {
  axisLine: { lineStyle: { color: "#475569" } },
  axisLabel: { color: "#94A3B8", fontSize: 11 },
  splitLine: { lineStyle: { color: "#334155", type: "dashed" as const } },
  tooltip: {
    backgroundColor: "#0F172A",
    borderColor: "#475569",
    textStyle: { color: "#E2E8F0", fontSize: 12 },
  },
};
