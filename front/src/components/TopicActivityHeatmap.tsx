import type { ActivityHeatmapCell } from "../types";

const DAY_LABELS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const HOURS = Array.from({ length: 24 }, (_, h) => h);

function cellColor(intensity: number): string {
  if (intensity <= 0) return "var(--gridline)";
  return `color-mix(in srgb, var(--series-1) ${Math.round(10 + intensity * 90)}%, var(--surface-1))`;
}

export function TopicActivityHeatmap({ cells }: { cells: ActivityHeatmapCell[] }) {
  const byCell = new Map<string, ActivityHeatmapCell>();
  for (const c of cells) byCell.set(`${c.day_of_week}-${c.hour}`, c);
  const maxAverage = Math.max(0, ...cells.map((c) => c.average));

  return (
    <div style={{ overflowX: "auto" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `36px repeat(24, 20px)`,
          gap: 2,
          width: "max-content",
        }}
      >
        <div />
        {HOURS.map((h) => (
          <div key={h} className="muted" style={{ fontSize: 9, textAlign: "center" }}>
            {h % 3 === 0 ? h : ""}
          </div>
        ))}
        {DAY_LABELS.map((label, dow) => (
          <div key={dow} style={{ display: "contents" }}>
            <div className="muted" style={{ fontSize: 11, alignSelf: "center" }}>
              {label}
            </div>
            {HOURS.map((hour) => {
              const cell = byCell.get(`${dow}-${hour}`);
              const intensity = cell && maxAverage > 0 ? cell.average / maxAverage : 0;
              return (
                <div
                  key={hour}
                  title={
                    cell
                      ? `${label} ${hour}:00 — promedio ${cell.average.toFixed(1)} (total ${cell.total})`
                      : undefined
                  }
                  style={{
                    width: 20,
                    height: 16,
                    borderRadius: 3,
                    background: cellColor(intensity),
                  }}
                />
              );
            })}
          </div>
        ))}
      </div>
      <div className="row" style={{ marginTop: 8, gap: 6 }}>
        <span className="muted" style={{ fontSize: 11 }}>
          Menos
        </span>
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <div key={v} style={{ width: 14, height: 14, borderRadius: 3, background: cellColor(v) }} />
        ))}
        <span className="muted" style={{ fontSize: 11 }}>
          Más
        </span>
      </div>
    </div>
  );
}
