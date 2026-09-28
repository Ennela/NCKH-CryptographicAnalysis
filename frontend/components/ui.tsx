/**
 * Small presentational building blocks shared by every page, styled after the
 * team mockup (panel / box1 / filler classes in "HTML & CSS demo/index.css").
 */
import type { ReactNode } from "react";
import { AlertCircle, Inbox, Loader2, RotateCw } from "lucide-react";

/** Page title + one-line description. */
export function PageHeader({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="text-[25px] font-bold text-white">{title}</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">{description}</p>
      </div>
      {children}
    </div>
  );
}

/** Bordered slate panel with an optional title row. */
export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
  bodyClassName = "p-5",
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            {title && <h2 className="text-base font-semibold text-white">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

/** Labeled form control, like `.item` in the mockup filter bar. */
export function Field({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={`flex min-w-[180px] flex-col gap-2 ${className}`}>
      <span className="text-sm text-muted">{label}</span>
      {children}
    </label>
  );
}

/** Horizontal filter bar (`.filler` in the mockup). */
export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="panel flex flex-wrap items-end gap-5 p-4">{children}</div>;
}

/** Loading / error / empty placeholder with an optional retry. */
export function StateBox({
  kind,
  message,
  hint,
  onRetry,
  height = "h-48",
}: {
  kind: "loading" | "error" | "empty";
  message: string;
  hint?: string;
  onRetry?: () => void;
  height?: string;
}) {
  const Icon = kind === "loading" ? Loader2 : kind === "error" ? AlertCircle : Inbox;
  const color = kind === "error" ? "text-down" : kind === "loading" ? "text-accentSoft" : "text-slate-500";
  return (
    <div className={`flex ${height} w-full flex-col items-center justify-center gap-2 px-6 text-center`}>
      <Icon className={`h-7 w-7 ${color} ${kind === "loading" ? "animate-spin" : ""}`} />
      <span className={`text-sm ${kind === "error" ? "font-semibold text-down" : "text-slate-300"}`}>{message}</span>
      {hint && <span className="max-w-lg text-xs text-slate-500">{hint}</span>}
      {onRetry && (
        <button onClick={onRetry} className="btn-secondary mt-1">
          <RotateCw className="h-3.5 w-3.5" /> Thử lại
        </button>
      )}
    </div>
  );
}

/** Colored pill. */
export function Badge({ tone, children }: { tone: "blue" | "green" | "red" | "amber" | "slate" | "purple"; children: ReactNode }) {
  const tones: Record<string, string> = {
    blue: "border-accentSoft/40 bg-accentSoft/10 text-blue-300",
    green: "border-up/40 bg-up/10 text-emerald-300",
    red: "border-down/40 bg-down/10 text-rose-300",
    amber: "border-forecast/40 bg-forecast/10 text-amber-300",
    slate: "border-line bg-page text-slate-300",
    purple: "border-purple-400/40 bg-purple-400/10 text-purple-300",
  };
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

/** Headline number card. */
export function StatCard({ label, value, hint, icon }: { label: string; value: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="panel flex flex-col justify-between gap-3 p-5">
      <div className="flex items-start justify-between text-xs font-semibold uppercase tracking-wider text-slate-400">
        <span>{label}</span>
        {icon}
      </div>
      <div>
        <div className="text-3xl font-bold text-white">{value}</div>
        {hint && <p className="mt-1 truncate text-xs text-slate-400" title={hint}>{hint}</p>}
      </div>
    </div>
  );
}

/** One metric row inside a panel (`.box1` in the mockup). */
export function MetricRow({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="metric-box">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-slate-300">{label}</span>
        <span className="font-mono text-sm font-semibold text-white">{value}</span>
      </div>
      {note && <div className="mt-1 text-xs text-slate-400">{note}</div>}
    </div>
  );
}

/** Asset class pill. */
export function AssetBadge({ assetClass }: { assetClass: string }) {
  return assetClass === "crypto" ? <Badge tone="purple">Crypto</Badge> : <Badge tone="blue">Cổ phiếu VN</Badge>;
}
