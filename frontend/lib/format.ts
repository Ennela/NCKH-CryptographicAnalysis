/**
 * Display formatters shared by every page (Vietnamese locale, VN time zone).
 */

const VN_TZ = "Asia/Ho_Chi_Minh";

/** Number with fixed decimals and thousands grouping; "—" for missing values. */
export function formatNum(value: number | null | undefined, decimals: number = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("vi-VN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** Price with a unit per asset class (stock prices are in thousand VND). */
export function formatPrice(value: number | null | undefined, assetClass: string): string {
  if (value === null || value === undefined) return "—";
  return assetClass === "crypto" ? `$${formatNum(value, 2)}` : formatNum(value, 2);
}

/** Signed percentage, e.g. "+3,21%". */
export function formatPct(value: number | null | undefined, decimals: number = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${formatNum(value, decimals)}%`;
}

/** Large volumes compacted: 1,2 Tr / 3,4 Tỷ. */
export function formatVolume(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) >= 1e9) return `${formatNum(value / 1e9, 2)} Tỷ`;
  if (Math.abs(value) >= 1e6) return `${formatNum(value / 1e6, 2)} Tr`;
  if (Math.abs(value) >= 1e3) return `${formatNum(value / 1e3, 1)} N`;
  return formatNum(value, 2);
}

/** Date (and hour for intraday data) in Vietnam time. */
export function formatDate(iso: string | null | undefined, withTime: boolean = false): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("vi-VN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
    timeZone: VN_TZ,
  });
}

/** Compact axis label for charts: dd/mm/yy, or dd/mm hh:mm for 1h bars. */
export function formatAxisTime(iso: string, timeframe: string): string {
  const opts: Intl.DateTimeFormatOptions =
    timeframe === "1h"
      ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: VN_TZ }
      : { day: "2-digit", month: "2-digit", year: "2-digit", timeZone: VN_TZ };
  return new Date(iso).toLocaleString("vi-VN", opts);
}

/** Timeframe label shown to users. */
export function timeframeLabel(timeframe: string): string {
  return timeframe === "1h" ? "1 giờ" : "1 ngày";
}
