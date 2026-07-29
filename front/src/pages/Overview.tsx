import { useEffect, useState } from "react";
import {
  ApiError,
  getResolutionSummary,
  getStatsBySource,
  getStatsOverview,
  getTopicTree,
  getVolumeTrend,
} from "../api";
import type { ResolutionSummaryRow, SourceBreakdownRow, StatsOverview, TopicNode, VolumeTrendPoint } from "../types";
import { DeltaStat } from "../components/DeltaStat";
import { StatTile } from "../components/StatTile";
import { VolumeChart } from "../components/VolumeChart";
import { TopicTreeView } from "../components/TopicTreeView";
import { ErrorBanner } from "../components/ErrorBanner";
import { dateInputToFrom, dateInputToTo, formatPeriodLabel, periodBounds, previousPeriodBounds, type Interval } from "../period";
import type { GlobalFilters } from "../components/GlobalFilterBar";

const noopSelectNode = () => {};

export function Overview({ filters }: { filters: GlobalFilters }) {
  const source = filters.source;
  const globalFrom = dateInputToFrom(filters.from);
  const globalTo = dateInputToTo(filters.to);
  const [interval, setInterval_] = useState<Interval>("day");
  const [overview, setOverview] = useState<StatsOverview | null>(null);
  const [trend, setTrend] = useState<VolumeTrendPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [selectedPoint, setSelectedPoint] = useState<VolumeTrendPoint | null>(null);
  const [scopedOverview, setScopedOverview] = useState<StatsOverview | null>(null);
  const [previousOverview, setPreviousOverview] = useState<StatsOverview | null>(null);
  const [prunedTree, setPrunedTree] = useState<TopicNode | null>(null);

  const [rows, setRows] = useState<ResolutionSummaryRow[] | null>(null);
  const [bySource, setBySource] = useState<SourceBreakdownRow[] | null>(null);

  // Global KPIs + chart data — depends on the filter bar (source/from/to) and interval, not
  // on the selected bar (that's a further drill-down within whatever this already covers).
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      getStatsOverview({ source: source || undefined, from: globalFrom, to: globalTo }),
      getVolumeTrend({ source: source || undefined, interval, from: globalFrom, to: globalTo }),
    ])
      .then(([o, t]) => {
        if (cancelled) return;
        setOverview(o);
        setTrend(t);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "No se pudo cargar /stats");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [source, globalFrom, globalTo, interval]);

  // Changing the interval reshapes the buckets, so a previously selected bar no longer applies.
  useEffect(() => {
    setSelectedPoint(null);
  }, [interval]);

  // Scoped data: resolution ranking + channel breakdown always (the filter bar's range when
  // nothing's selected), plus the pruned tree and period-vs-previous-period KPIs only when a
  // bar is selected (that further narrows down to just that bucket).
  useEffect(() => {
    let cancelled = false;
    const scope = selectedPoint ? periodBounds(selectedPoint, interval) : { from: globalFrom, to: globalTo };

    Promise.all([
      getResolutionSummary({ source: source || undefined, ...scope, order_by: "total_conversations", dir: "desc" }),
      getStatsBySource(scope),
    ])
      .then(([r, b]) => {
        if (cancelled) return;
        setRows(r);
        setBySource(b);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "No se pudo cargar el detalle del período");
      });

    if (selectedPoint) {
      getTopicTree({ source: source || undefined, ...scope }).then((t) => !cancelled && setPrunedTree(t));
      getStatsOverview({ source: source || undefined, ...scope }).then((o) => !cancelled && setScopedOverview(o));
      const prevScope = previousPeriodBounds(selectedPoint, interval);
      getStatsOverview({ source: source || undefined, ...prevScope }).then((o) => !cancelled && setPreviousOverview(o));
    } else {
      setPrunedTree(null);
      setScopedOverview(null);
      setPreviousOverview(null);
    }

    return () => {
      cancelled = true;
    };
  }, [source, globalFrom, globalTo, selectedPoint, interval]);

  function handleSelectPeriod(point: VolumeTrendPoint) {
    setSelectedPoint((current) => (current?.period_start === point.period_start ? null : point));
  }

  const activeOverview = selectedPoint ? scopedOverview : overview;
  const worstResolution = rows ? [...rows].sort((a, b) => a.resolution_rate - b.resolution_rate).slice(0, 5) : [];
  const topByVolume = rows ? rows.slice(0, 5) : [];
  const documentationGaps = rows ? rows.filter((r) => !r.has_documentation).slice(0, 5) : [];

  return (
    <div>
      <div className="card">
        <h2 style={{ margin: 0 }}>{selectedPoint ? `KPIs — ${formatPeriodLabel(selectedPoint, interval)}` : "KPIs"}</h2>

        {error && <ErrorBanner message={error} />}
        {loading && <p className="muted">Cargando…</p>}

        {activeOverview && (
          <div className="grid cols-4" style={{ marginTop: 12 }}>
            {selectedPoint ? (
              <>
                <DeltaStat
                  label="Conversaciones procesadas"
                  value={activeOverview.total_conversations}
                  previousValue={previousOverview?.total_conversations ?? null}
                />
                <DeltaStat
                  label="Tasa de resolución"
                  value={Math.round(activeOverview.overall_resolution_rate * 100)}
                  suffix="%"
                  previousValue={
                    previousOverview ? Math.round(previousOverview.overall_resolution_rate * 100) : null
                  }
                  goodDirection="up"
                  tone={
                    activeOverview.overall_resolution_rate >= 0.6
                      ? "good"
                      : activeOverview.overall_resolution_rate < 0.3
                        ? "critical"
                        : undefined
                  }
                />
                <DeltaStat
                  label="Resueltas"
                  value={activeOverview.resolved}
                  previousValue={previousOverview?.resolved ?? null}
                  goodDirection="up"
                />
                <DeltaStat
                  label="No resueltas"
                  value={activeOverview.unresolved}
                  previousValue={previousOverview?.unresolved ?? null}
                  goodDirection="down"
                />
              </>
            ) : (
              <>
                <StatTile label="Conversaciones procesadas" value={String(activeOverview.total_conversations)} />
                <StatTile
                  label="Tasa de resolución"
                  value={`${(activeOverview.overall_resolution_rate * 100).toFixed(0)}%`}
                  tone={
                    activeOverview.overall_resolution_rate >= 0.6
                      ? "good"
                      : activeOverview.overall_resolution_rate < 0.3
                        ? "critical"
                        : undefined
                  }
                />
                <StatTile label="Resueltas" value={String(activeOverview.resolved)} />
                <StatTile label="No resueltas" value={String(activeOverview.unresolved)} />
              </>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Volumen de conversaciones</h2>
          <select value={interval} onChange={(e) => setInterval_(e.target.value as Interval)} style={{ width: 140 }}>
            <option value="day">Por día</option>
            <option value="week">Por semana</option>
            <option value="month">Por mes</option>
          </select>
        </div>
        {trend && (
          <VolumeChart points={trend} selectedPeriodStart={selectedPoint?.period_start ?? null} onSelectPeriod={handleSelectPeriod} />
        )}
        {selectedPoint && (
          <p className="muted" style={{ marginTop: 8 }}>
            Mostrando detalle de <strong>{formatPeriodLabel(selectedPoint, interval)}</strong> — clickeá la misma barra
            de nuevo para volver a la vista global.
          </p>
        )}
      </div>

      {selectedPoint && (
        <div className="grid cols-2">
          <div className="card">
            <h2>Árbol de temas — {formatPeriodLabel(selectedPoint, interval)}</h2>
            {prunedTree ? (
              <TopicTreeView root={prunedTree} onSelectNode={noopSelectNode} selectedTopicId={null} />
            ) : (
              <p className="muted">Cargando…</p>
            )}
          </div>

          <div className="card">
            <h3>Peor tasa de resolución en el período</h3>
            <RankingMiniTable rows={worstResolution} metric="rate" />
            <h3 style={{ marginTop: 18 }}>Más consultados en el período</h3>
            <RankingMiniTable rows={topByVolume} metric="total" />
          </div>
        </div>
      )}

      <div className="grid cols-2">
        <div className="card">
          <h2>Gap de documentación{selectedPoint ? ` — ${formatPeriodLabel(selectedPoint, interval)}` : ""}</h2>
          <p className="muted" style={{ marginTop: -6, marginBottom: 12 }}>
            Temas con conversaciones pero sin ningún documento asignado — orden por volumen.
          </p>
          {documentationGaps.length === 0 && <p className="empty-state">Sin gaps de documentación 🎉</p>}
          {documentationGaps.map((row) => (
            <div key={row.topic_id} className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
              <span>{row.leaf_path}</span>
              <span className="gap-flag">{row.total_conversations} conv. sin doc</span>
            </div>
          ))}
        </div>

        <div className="card">
          <h2>Desglose por canal{selectedPoint ? ` — ${formatPeriodLabel(selectedPoint, interval)}` : ""}</h2>
          {bySource && bySource.length === 0 && <p className="empty-state">Sin datos.</p>}
          {bySource && bySource.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Canal</th>
                  <th>Conversaciones</th>
                  <th>Tasa resolución</th>
                </tr>
              </thead>
              <tbody>
                {bySource.map((row) => (
                  <tr key={row.source}>
                    <td>{row.source}</td>
                    <td>{row.total_conversations}</td>
                    <td>{(row.overall_resolution_rate * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function RankingMiniTable({ rows, metric }: { rows: ResolutionSummaryRow[]; metric: "rate" | "total" }) {
  if (rows.length === 0) return <p className="muted">Sin datos.</p>;
  return (
    <table>
      <tbody>
        {rows.map((row) => (
          <tr key={row.topic_id}>
            <td>{row.leaf_path}</td>
            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
              {metric === "rate" ? `${(row.resolution_rate * 100).toFixed(0)}%` : `${row.total_conversations} conv.`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
