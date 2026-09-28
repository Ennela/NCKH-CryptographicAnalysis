/**
 * Rule-based reading of technical indicators, shown next to the charts.
 * Deliberately simple and explainable: each sentence maps to one textbook rule.
 */
import type { IndicatorPoint } from "@/lib/api";

export type Tone = "up" | "down" | "neutral";

export interface Insight {
  tone: Tone;
  text: string;
}

/** RSI zone per the usual 30/70 thresholds. */
export function rsiZone(rsi: number | null): { label: string; tone: Tone } {
  if (rsi === null) return { label: "chưa đủ dữ liệu", tone: "neutral" };
  if (rsi >= 70) return { label: "vùng quá mua (≥ 70)", tone: "down" };
  if (rsi <= 30) return { label: "vùng quá bán (≤ 30)", tone: "up" };
  return { label: "vùng trung tính (30–70)", tone: "neutral" };
}

/** Sentences describing trend and momentum at the latest bar. */
export function readIndicators(points: IndicatorPoint[]): Insight[] {
  const last = points[points.length - 1];
  if (!last) return [];
  const out: Insight[] = [];

  if (last.sma_20 !== null && last.sma_50 !== null) {
    if (last.close > last.sma_20 && last.sma_20 > last.sma_50) {
      out.push({ tone: "up", text: "Giá nằm trên SMA 20 và SMA 20 trên SMA 50 → xu hướng tăng ngắn hạn." });
    } else if (last.close < last.sma_20 && last.sma_20 < last.sma_50) {
      out.push({ tone: "down", text: "Giá nằm dưới SMA 20 và SMA 20 dưới SMA 50 → xu hướng giảm ngắn hạn." });
    } else {
      out.push({ tone: "neutral", text: "Giá và hai đường SMA đan xen → thị trường đi ngang / chưa rõ xu hướng." });
    }
  }

  const zone = rsiZone(last.rsi_14);
  if (last.rsi_14 !== null) {
    out.push({ tone: zone.tone, text: `RSI 14 = ${last.rsi_14.toFixed(1)}: ${zone.label}.` });
  }

  if (last.macd !== null && last.macd_signal !== null) {
    const prev = points[points.length - 2];
    const crossedUp = prev && prev.macd !== null && prev.macd_signal !== null && prev.macd <= prev.macd_signal && last.macd > last.macd_signal;
    const crossedDown = prev && prev.macd !== null && prev.macd_signal !== null && prev.macd >= prev.macd_signal && last.macd < last.macd_signal;
    if (crossedUp) out.push({ tone: "up", text: "MACD vừa cắt lên đường Signal ở nến gần nhất → tín hiệu động lượng tăng." });
    else if (crossedDown) out.push({ tone: "down", text: "MACD vừa cắt xuống đường Signal ở nến gần nhất → tín hiệu động lượng giảm." });
    else if (last.macd > last.macd_signal) out.push({ tone: "up", text: "MACD nằm trên Signal → động lượng đang nghiêng về tăng." });
    else out.push({ tone: "down", text: "MACD nằm dưới Signal → động lượng đang nghiêng về giảm." });
  }
  return out;
}

export const TONE_CLASS: Record<Tone, string> = {
  up: "text-up",
  down: "text-down",
  neutral: "text-slate-300",
};
