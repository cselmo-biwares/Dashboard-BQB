import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { VolumeTrendPoint } from "../types";

const SEGMENTS = [
  { key: "resolved", color: "var(--status-good)", label: "Resuelto" },
  { key: "partial", color: "var(--status-warning)", label: "Parcial" },
  { key: "unresolved", color: "var(--status-critical)", label: "No resuelto" },
  { key: "unknown", color: "var(--status-unknown)", label: "Desconocido" },
] as const;

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit" });
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload || payload.length === 0) return null;
  const total = payload.reduce((sum: number, p: any) => sum + (p.value ?? 0), 0);
  return (
    <div className="card" style={{ padding: "10px 14px" }}>
      <strong style={{ fontSize: 13 }}>{formatDate(label)}</strong>
      <div style={{ fontSize: 12.5, marginTop: 4 }}>
        {payload.map((p: any) => (
          <div key={p.dataKey} style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
            <span style={{ color: p.color }}>{p.name}</span>
            <span>{p.value}</span>
          </div>
        ))}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 16,
            marginTop: 4,
            borderTop: "1px solid var(--gridline)",
            paddingTop: 4,
          }}
        >
          <span className="muted">Total</span>
          <span>{total}</span>
        </div>
      </div>
      <div className="muted" style={{ marginTop: 6, fontSize: 11 }}>
        Click para filtrar el detalle a este período
      </div>
    </div>
  );
}

/** Stacked bar chart (single axis: conversation count) with a status-colored breakdown per bar.
 * Clicking a bar selects/deselects that period (toggle) via onSelectPeriod. */
export function VolumeChart({
  points,
  selectedPeriodStart,
  onSelectPeriod,
}: {
  points: VolumeTrendPoint[];
  selectedPeriodStart: string | null;
  onSelectPeriod: (point: VolumeTrendPoint) => void;
}) {
  if (points.length === 0) {
    return <div className="empty-state">No hay datos en el período seleccionado.</div>;
  }

  function handleClick(data: any) {
    const point: VolumeTrendPoint | undefined = data?.payload ?? data;
    if (point?.period_start) onSelectPeriod(point);
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={points} margin={{ top: 20, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--gridline)" vertical={false} />
        <XAxis
          dataKey="period_start"
          tickFormatter={formatDate}
          tick={{ fill: "var(--text-muted)", fontSize: 12 }}
          axisLine={{ stroke: "var(--baseline)" }}
          tickLine={false}
        />
        <YAxis allowDecimals={false} tick={{ fill: "var(--text-muted)", fontSize: 12 }} axisLine={false} tickLine={false} />
        <Tooltip
          content={<ChartTooltip />}
          cursor={{ fill: "color-mix(in srgb, var(--series-1) 8%, transparent)" }}
        />
        <Legend formatter={(value) => <span style={{ color: "var(--text-secondary)", fontSize: 12 }}>{value}</span>} />
        {SEGMENTS.map(({ key, color, label }, i) => (
          <Bar
            key={key}
            dataKey={key}
            name={label}
            stackId="volume"
            fill={color}
            radius={i === SEGMENTS.length - 1 ? [4, 4, 0, 0] : 0}
            onClick={handleClick}
            style={{ cursor: "pointer" }}
          >
            {points.map((p) => (
              <Cell
                key={p.period_start}
                fillOpacity={!selectedPeriodStart || p.period_start === selectedPeriodStart ? 1 : 0.3}
              />
            ))}
          </Bar>
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
