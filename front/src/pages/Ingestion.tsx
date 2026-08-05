import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  getIngestionRun,
  getLatestIngestionRun,
  getStatsBySource,
  triggerIngestionUpdate,
  unprocessConversations,
} from "../api";
import type { ConversationStatus, IngestionRunOut, IngestionUpdateRequest, UnprocessResult } from "../types";
import { ErrorBanner } from "../components/ErrorBanner";
import { DateRangePicker } from "../components/DateRangePicker";
import { ChannelSelect } from "../components/ChannelSelect";
import { dateInputToFrom, dateInputToTo } from "../period";

const STATUS_LABEL: Record<IngestionRunOut["status"], string> = {
  running: "Corriendo…",
  success: "Éxito",
  failed: "Falló",
};

const STATUS_CLASS: Record<IngestionRunOut["status"], string> = {
  running: "unknown",
  success: "resolved",
  failed: "unresolved",
};

const CONVERSATION_STATUSES: ConversationStatus[] = [
  "in_progress",
  "closed_timeout",
  "closed_assistant",
  "closed_operator",
  "redirected",
];

type BillableFilter = "" | "true" | "false";

function UnprocessPanel() {
  const [source, setSource] = useState("");
  const [knownSources, setKnownSources] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UnprocessResult | null>(null);

  useEffect(() => {
    getStatsBySource()
      .then((rows) => setKnownSources(rows.map((r) => r.source).sort()))
      .catch(() => setKnownSources([]));
  }, []);

  const hasFilter = source.trim() || dateFrom || dateTo;

  async function handleUnprocess() {
    if (!hasFilter) return;
    if (
      !confirm(
        "Esto va a borrar el procesamiento local (clasificación de temas) de las conversaciones que matcheen el filtro. No se puede deshacer. ¿Continuar?",
      )
    ) {
      return;
    }
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const r = await unprocessConversations({
        source: source.trim() || undefined,
        created_date_from: dateInputToFrom(dateFrom),
        created_date_to: dateInputToTo(dateTo),
      });
      setResult(r);
    } catch (e) {
      setError(e instanceof ApiError ? `No se pudo deshacer el procesamiento: ${e.message}` : "Error inesperado");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Deshacer procesamiento</h2>
        <button className="btn danger" onClick={handleUnprocess} disabled={running || !hasFilter}>
          {running ? "Procesando…" : "Deshacer procesamiento"}
        </button>
      </div>
      <p className="muted" style={{ marginTop: -4, marginBottom: 12 }}>
        Elimina la clasificación local de las conversaciones que matcheen el filtro, como si nunca se hubieran
        procesado. No borra nada en el sistema origen — para volver a clasificarlas, disparalas de nuevo desde el
        Panel de ingesta con el mismo rango de fechas.
      </p>

      <div className="row" style={{ gap: 16 }}>
        <div className="field" style={{ marginBottom: 0, minWidth: 200 }}>
          <label htmlFor="unprocess-source">Canal (source)</label>
          <ChannelSelect id="unprocess-source" value={source} knownSources={knownSources} onChange={setSource} />
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label>Rango (created_at)</label>
          <DateRangePicker from={dateFrom} to={dateTo} onChange={(f, t) => { setDateFrom(f); setDateTo(t); }} />
        </div>
      </div>

      {!hasFilter && <p className="muted" style={{ marginTop: 10 }}>Elegí al menos un filtro (canal o rango de fechas).</p>}
      {error && <ErrorBanner message={error} />}
      {result && (
        <p className="muted" style={{ marginTop: 10 }}>
          {result.conversations_affected === 0
            ? "No había conversaciones procesadas que coincidan con el filtro."
            : `${result.conversations_affected} conversaciones des-procesadas, ${result.topic_assignments_removed} asignaciones de tema eliminadas.`}
        </p>
      )}
    </div>
  );
}

export function Ingestion() {
  const [run, setRun] = useState<IngestionRunOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<number | null>(null);

  const [source, setSource] = useState("");
  const [knownSources, setKnownSources] = useState<string[]>([]);
  const [status, setStatus] = useState<ConversationStatus | "">("");
  const [billable, setBillable] = useState<BillableFilter>("");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [minAgeHours, setMinAgeHours] = useState("");
  const [pageSize, setPageSize] = useState("");

  function stopPolling() {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function pollRun(runId: number) {
    stopPolling();
    const startedAt = Date.now();
    const MAX_POLL_MS = 10 * 60 * 1000; // safety net: stop polling after 10min regardless
    pollRef.current = window.setInterval(async () => {
      if (Date.now() - startedAt > MAX_POLL_MS) {
        stopPolling();
        return;
      }
      try {
        const updated = await getIngestionRun(runId);
        setRun(updated);
        if (updated.status !== "running") stopPolling();
      } catch {
        stopPolling();
      }
    }, 1500);
  }

  useEffect(() => {
    getStatsBySource()
      .then((rows) => setKnownSources(rows.map((r) => r.source).sort()))
      .catch(() => setKnownSources([]));
  }, []);

  useEffect(() => {
    getLatestIngestionRun()
      .then((r) => {
        setRun(r);
        if (r.status === "running") pollRun(r.id);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) return; // no runs yet
        setError(e instanceof ApiError ? e.message : "No se pudo cargar el estado de ingesta");
      });
    return stopPolling;
  }, []);

  function buildFilters(): IngestionUpdateRequest {
    const filters: IngestionUpdateRequest = {};
    if (source.trim()) filters.source = source.trim();
    if (status) filters.status = status;
    if (billable) filters.billable = billable === "true";
    const from = dateInputToFrom(createdFrom);
    if (from) filters.created_date_from = new Date(from).toISOString();
    const to = dateInputToTo(createdTo);
    if (to) filters.created_date_to = new Date(to).toISOString();
    if (minAgeHours) filters.min_age_hours = Number(minAgeHours);
    if (pageSize) filters.page_size = Number(pageSize);
    return filters;
  }

  async function handleTrigger() {
    setTriggering(true);
    setError(null);
    try {
      const { run_id } = await triggerIngestionUpdate(buildFilters());
      const initial = await getIngestionRun(run_id);
      setRun(initial);
      if (initial.status === "running") pollRun(run_id);
    } catch (e) {
      setError(e instanceof ApiError ? `No se pudo disparar la ingesta: ${e.message}` : "Error inesperado");
    } finally {
      setTriggering(false);
    }
  }

  return (
    <div>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Panel de ingesta</h2>
          <button className="btn primary" onClick={handleTrigger} disabled={triggering || run?.status === "running"}>
            {run?.status === "running" ? "Corriendo…" : "Disparar /ingestion/update"}
          </button>
        </div>

        <h3 style={{ marginTop: 16 }}>Filtros (opcionales — vacío = ventana automática)</h3>
        <div className="grid cols-2">
          <div className="field">
            <label htmlFor="filter-source">Canal (source)</label>
            <ChannelSelect id="filter-source" value={source} knownSources={knownSources} onChange={setSource} />
          </div>
          <div className="field">
            <label htmlFor="filter-status">Estado</label>
            <select id="filter-status" value={status} onChange={(e) => setStatus(e.target.value as ConversationStatus | "")}>
              <option value="">Cualquiera</option>
              {CONVERSATION_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="filter-billable">Facturable</label>
            <select id="filter-billable" value={billable} onChange={(e) => setBillable(e.target.value as BillableFilter)}>
              <option value="">Cualquiera</option>
              <option value="true">Sí</option>
              <option value="false">No</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="filter-page-size">Conversaciones por página (1–50)</label>
            <input
              id="filter-page-size"
              type="number"
              min={1}
              max={50}
              placeholder="50 (default)"
              value={pageSize}
              onChange={(e) => setPageSize(e.target.value)}
            />
          </div>
          <div className="field">
            <label>Rango (created_at)</label>
            <DateRangePicker from={createdFrom} to={createdTo} onChange={(from, to) => { setCreatedFrom(from); setCreatedTo(to); }} />
          </div>
          <div className="field">
            <label htmlFor="filter-min-age">Antigüedad mínima en horas</label>
            <input
              id="filter-min-age"
              type="number"
              min={1}
              placeholder="2 (default)"
              value={minAgeHours}
              onChange={(e) => setMinAgeHours(e.target.value)}
            />
            <span className="muted">Se ignora si completaste "Hasta".</span>
          </div>
        </div>

        {error && <ErrorBanner message={error} />}

        {!run && !error && <p className="muted">No hay corridas todavía.</p>}

        {run && (
          <div style={{ marginTop: 12 }}>
            <div className="row" style={{ marginBottom: 10 }}>
              <span className={`pill ${STATUS_CLASS[run.status]}`}>{STATUS_LABEL[run.status]}</span>
              <span className="muted">run #{run.id}</span>
            </div>
            <div className="grid cols-4">
              <div className="stat-tile">
                <div className="label">Procesadas</div>
                <div className="value">{run.conversations_processed}</div>
              </div>
              <div className="stat-tile">
                <div className="label">Fallidas</div>
                <div className="value">{run.conversations_failed}</div>
              </div>
              <div className="stat-tile">
                <div className="label">Empezó</div>
                <div className="value" style={{ fontSize: 13 }}>
                  {new Date(run.started_at).toLocaleString("es-AR")}
                </div>
              </div>
              <div className="stat-tile">
                <div className="label">Terminó</div>
                <div className="value" style={{ fontSize: 13 }}>
                  {run.finished_at ? new Date(run.finished_at).toLocaleString("es-AR") : "—"}
                </div>
              </div>
            </div>
            {run.error && <ErrorBanner message={run.error} />}
          </div>
        )}
      </div>

      <UnprocessPanel />
    </div>
  );
}
