import { useEffect, useRef, useState } from "react";

function toDateInput(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function lastNDays(n: number): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - (n - 1));
  return { from: toDateInput(from), to: toDateInput(to) };
}

function monthRange(monthsAgo: number): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now.getFullYear(), now.getMonth() - monthsAgo, 1);
  const to = new Date(now.getFullYear(), now.getMonth() - monthsAgo + 1, 0);
  return { from: toDateInput(from), to: toDateInput(to) };
}

const PRESETS: { label: string; range: () => { from: string; to: string } }[] = [
  { label: "Hoy", range: () => lastNDays(1) },
  { label: "Últimos 7 días", range: () => lastNDays(7) },
  { label: "Últimos 30 días", range: () => lastNDays(30) },
  { label: "Este mes", range: () => monthRange(0) },
  { label: "Mes anterior", range: () => monthRange(1) },
];

function formatShort(value: string): string {
  const d = new Date(`${value}T00:00:00`);
  return d.toLocaleDateString("es-AR", { day: "2-digit", month: "short" });
}

export function DateRangePicker({
  from,
  to,
  onChange,
}: {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const label = from || to ? `${from ? formatShort(from) : "…"} – ${to ? formatShort(to) : "…"}` : "Todo el período";

  return (
    <div className="date-range-picker" ref={ref}>
      <button type="button" className={`btn date-range-trigger${from || to ? " active" : ""}`} onClick={() => setOpen((o) => !o)}>
        <span aria-hidden>📅</span> {label}
      </button>
      {open && (
        <div className="date-range-popover">
          <div className="date-range-presets">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                className="btn"
                onClick={() => {
                  const r = p.range();
                  onChange(r.from, r.to);
                  setOpen(false);
                }}
              >
                {p.label}
              </button>
            ))}
            <button
              className="btn"
              onClick={() => {
                onChange("", "");
                setOpen(false);
              }}
            >
              Todo el período
            </button>
          </div>
          <div className="date-range-custom">
            <div className="field" style={{ marginBottom: 0 }}>
              <label>Desde</label>
              <input type="date" value={from} onChange={(e) => onChange(e.target.value, to)} />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <label>Hasta</label>
              <input type="date" value={to} onChange={(e) => onChange(from, e.target.value)} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
