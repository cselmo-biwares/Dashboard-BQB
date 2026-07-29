import { useEffect, useState } from "react";
import { getStatsBySource } from "../api";
import { DateRangePicker } from "./DateRangePicker";

export interface GlobalFilters {
  source: string;
  from: string;
  to: string;
}

export const EMPTY_FILTERS: GlobalFilters = { source: "", from: "", to: "" };

export function GlobalFilterBar({ value, onChange }: { value: GlobalFilters; onChange: (next: GlobalFilters) => void }) {
  const [sources, setSources] = useState<string[]>([]);
  const active = value.source || value.from || value.to;

  useEffect(() => {
    getStatsBySource()
      .then((rows) => setSources(rows.map((r) => r.source).sort()))
      .catch(() => setSources([]));
  }, []);

  return (
    <div className="row filter-bar">
      <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>
        Filtros:
      </span>
      <DateRangePicker from={value.from} to={value.to} onChange={(from, to) => onChange({ ...value, from, to })} />
      <div className="field" style={{ marginBottom: 0, width: 200 }}>
        <select value={value.source} onChange={(e) => onChange({ ...value, source: e.target.value })}>
          <option value="">Todos los canales</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      {active && (
        <button className="btn" onClick={() => onChange(EMPTY_FILTERS)}>
          Limpiar
        </button>
      )}
    </div>
  );
}
