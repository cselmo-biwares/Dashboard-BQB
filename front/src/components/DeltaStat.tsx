import type { ReactNode } from "react";

/** A stat tile value plus a delta vs. a previous value — neutral by default, colored
 * when the metric direction has an obvious good/bad reading (e.g. resolution rate). */
export function DeltaStat({
  label,
  value,
  suffix = "",
  previousValue,
  tone,
  goodDirection,
}: {
  label: string;
  value: number;
  suffix?: string;
  previousValue: number | null;
  tone?: "good" | "critical";
  goodDirection?: "up" | "down";
}) {
  let deltaNode: ReactNode = null;
  if (previousValue !== null) {
    if (previousValue === 0 && value === 0) {
      deltaNode = <span className="muted">sin cambios</span>;
    } else if (previousValue === 0) {
      deltaNode = <span className="muted">nuevo</span>;
    } else {
      const pct = ((value - previousValue) / previousValue) * 100;
      const up = pct >= 0;
      let deltaTone: "good" | "critical" | undefined;
      if (goodDirection) {
        deltaTone = (up && goodDirection === "up") || (!up && goodDirection === "down") ? "good" : "critical";
      }
      const color =
        deltaTone === "good" ? "var(--status-good)" : deltaTone === "critical" ? "var(--status-critical)" : undefined;
      deltaNode = (
        <span style={{ color: color ?? "var(--text-muted)" }}>
          {up ? "↑" : "↓"} {Math.abs(pct).toFixed(0)}% vs. período anterior
        </span>
      );
    }
  }

  return (
    <div className="stat-tile">
      <div className="label">{label}</div>
      <div className={`value${tone ? ` ${tone}` : ""}`}>
        {value}
        {suffix}
      </div>
      {deltaNode && <div style={{ fontSize: 11.5, marginTop: 4 }}>{deltaNode}</div>}
    </div>
  );
}
