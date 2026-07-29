import type { ResolutionBreakdown } from "../types";

const SEGMENTS: { key: keyof ResolutionBreakdown; varName: string }[] = [
  { key: "resolved", varName: "--status-good" },
  { key: "partial", varName: "--status-warning" },
  { key: "unresolved", varName: "--status-critical" },
  { key: "unknown", varName: "--status-unknown" },
];

/** Small horizontal stacked bar showing the resolution mix for one leaf/node. */
export function BreakdownBar({ breakdown }: { breakdown: ResolutionBreakdown }) {
  const total = breakdown.resolved + breakdown.partial + breakdown.unresolved + breakdown.unknown;
  if (total === 0) {
    return <div className="breakdown-bar" title="Sin conversaciones" />;
  }
  return (
    <div className="breakdown-bar" title={`${breakdown.resolved} resueltas / ${total} total`}>
      {SEGMENTS.map(({ key, varName }) => {
        const pct = (breakdown[key] / total) * 100;
        if (pct === 0) return null;
        return <span key={key} style={{ width: `${pct}%`, background: `var(${varName})` }} />;
      })}
    </div>
  );
}
