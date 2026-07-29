import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  createNote,
  getActivityHeatmap,
  getResolutionSummary,
  getRootCause,
  getTopicConversations,
  getTopicDocuments,
  getTopicTree,
  getWholeTreeActivityHeatmap,
  restructureTree,
  unassignDocument,
} from "../api";
import type {
  ActivityHeatmapResult,
  ConversationTopicOut,
  DocumentOut,
  ResolutionSummaryRow,
  RootCauseResult,
  TopicNode,
} from "../types";
import { TopicArboristTree } from "../components/TopicArboristTree";
import { TopicActivityHeatmap } from "../components/TopicActivityHeatmap";
import { ResolutionPill } from "../components/ResolutionPill";
import { BreakdownBar } from "../components/BreakdownBar";
import { ErrorBanner } from "../components/ErrorBanner";
import { Modal } from "../components/Modal";
import type { GlobalFilters } from "../components/GlobalFilterBar";
import { dateInputToFrom, dateInputToTo } from "../period";

type SortKey = "resolution_rate" | "total_conversations" | "resolved" | "partial" | "unresolved" | "unknown";

const CONVERSATIONS_PAGE_SIZE = 20;

function findTopicNodeById(node: TopicNode, id: number): TopicNode | null {
  if (node.id === id) return node;
  for (const child of node.children) {
    const found = findTopicNodeById(child, id);
    if (found) return found;
  }
  return null;
}

export function Topics({
  onOpenConversation,
  canRestructure,
  filters,
}: {
  onOpenConversation: (id: number) => void;
  canRestructure: boolean;
  filters: GlobalFilters;
}) {
  const source = filters.source || undefined;
  const from = dateInputToFrom(filters.from);
  const to = dateInputToTo(filters.to);

  const [tree, setTree] = useState<TopicNode | null>(null);
  const [rows, setRows] = useState<ResolutionSummaryRow[] | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("resolution_rate");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [error, setError] = useState<string | null>(null);

  const [selectedNode, setSelectedNode] = useState<TopicNode | null>(null);
  const [nodeDocs, setNodeDocs] = useState<DocumentOut[] | null>(null);
  const [conversations, setConversations] = useState<ConversationTopicOut[] | null>(null);
  const [conversationsTotal, setConversationsTotal] = useState(0);
  const [conversationsOffset, setConversationsOffset] = useState(0);

  const [heatmap, setHeatmap] = useState<ActivityHeatmapResult | null>(null);
  const [heatmapLoading, setHeatmapLoading] = useState(false);

  const [rootCause, setRootCause] = useState<RootCauseResult | null>(null);
  const [rootCauseLoading, setRootCauseLoading] = useState(false);
  const [rootCauseError, setRootCauseError] = useState<string | null>(null);
  const [rootCauseOpen, setRootCauseOpen] = useState(false);
  const [rootCauseSaving, setRootCauseSaving] = useState(false);
  const [rootCauseSaved, setRootCauseSaved] = useState(false);
  const [rootCauseFilters, setRootCauseFilters] = useState<{ source?: string; from?: string; to?: string }>({});

  const [instruction, setInstruction] = useState("");
  const [restructuring, setRestructuring] = useState(false);
  const [restructureMsg, setRestructureMsg] = useState<string | null>(null);

  const reloadTree = useCallback(() => {
    getTopicTree({ source, from, to })
      .then(setTree)
      .catch((e) => setError(e instanceof ApiError ? e.message : "No se pudo cargar el árbol"));
  }, [source, from, to]);

  const reloadSummary = useCallback(() => {
    getResolutionSummary({ source, from, to, order_by: sortKey, dir: sortDir })
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : "No se pudo cargar el ranking"));
  }, [source, from, to, sortKey, sortDir]);

  useEffect(reloadTree, [reloadTree]);
  useEffect(reloadSummary, [reloadSummary]);

  const loadConversationsPage = useCallback(
    (topicId: number, offset: number) => {
      getTopicConversations(topicId, CONVERSATIONS_PAGE_SIZE, offset, { source, from, to }).then((page) => {
        setConversations(page.items);
        setConversationsTotal(page.total);
        setConversationsOffset(offset);
      });
    },
    [source, from, to],
  );

  // A selected node can be pruned away entirely once the filter bar narrows the tree (zero
  // matching conversations under the new filter), which left the detail card showing a
  // node that no longer exists. Simplest robust fix: reset the whole card back to its
  // empty state on any filter change, rather than trying to carry the selection across it.
  useEffect(() => {
    setSelectedNode(null);
    setNodeDocs(null);
    setConversations(null);
    setConversationsTotal(0);
    setConversationsOffset(0);
    setHeatmap(null);
  }, [source, from, to]);

  function selectNode(node: TopicNode) {
    setSelectedNode(node);
    setNodeDocs(null);
    setConversations(null);
    setConversationsTotal(0);
    setConversationsOffset(0);
    setHeatmap(null);
    setHeatmapLoading(true);
    const heatmapRequest =
      node.id == null ? getWholeTreeActivityHeatmap({ source, from, to }) : getActivityHeatmap(node.id, { source, from, to });
    heatmapRequest
      .then(setHeatmap)
      .catch(() => setHeatmap(null))
      .finally(() => setHeatmapLoading(false));
    // The root has no topic id: it aggregates everything already (via `node` itself), but
    // there's no single topic to fetch documents/conversations for.
    if (node.id == null) return;
    getTopicDocuments(node.id).then(setNodeDocs);
    loadConversationsPage(node.id, 0);
  }

  function selectRowTopic(topicId: number) {
    if (!tree) return;
    const node = findTopicNodeById(tree, topicId);
    if (node) selectNode(node);
  }

  function handleTreeSelect(topicId: number | null) {
    if (topicId == null) {
      if (tree) selectNode(tree);
      return;
    }
    selectRowTopic(topicId);
  }

  function handleTreeChanged() {
    reloadTree();
    reloadSummary();
  }

  async function openRootCause(topicId: number, resolution: "partial" | "unresolved") {
    setRootCauseOpen(true);
    setRootCauseLoading(true);
    setRootCauseError(null);
    setRootCause(null);
    setRootCauseSaved(false);
    setRootCauseFilters({ source, from, to });
    try {
      const result = await getRootCause(topicId, resolution, { source, from, to });
      setRootCause(result);
    } catch (e) {
      setRootCauseError(e instanceof ApiError ? e.message : "No se pudo analizar la causa");
    } finally {
      setRootCauseLoading(false);
    }
  }

  async function saveRootCauseAsNote() {
    if (!rootCause) return;
    setRootCauseSaving(true);
    setRootCauseError(null);
    try {
      const content = [
        rootCause.explanation,
        rootCause.secondary_causes.length > 0
          ? `Causas secundarias:\n${rootCause.secondary_causes.map((c) => `- ${c}`).join("\n")}`
          : null,
      ]
        .filter(Boolean)
        .join("\n\n");
      await createNote({
        title: rootCause.main_cause,
        content,
        topic_id: rootCause.topic_id,
        leaf_path: rootCause.leaf_path,
        resolution: rootCause.resolution,
        filter_source: rootCauseFilters.source || null,
        filter_from: rootCauseFilters.from || null,
        filter_to: rootCauseFilters.to || null,
      });
      setRootCauseSaved(true);
    } catch (e) {
      setRootCauseError(e instanceof ApiError ? e.message : "No se pudo guardar la nota");
    } finally {
      setRootCauseSaving(false);
    }
  }

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  async function handleUnassign(documentId: number) {
    if (selectedNode?.id == null) return;
    await unassignDocument(selectedNode.id, documentId);
    getTopicDocuments(selectedNode.id).then(setNodeDocs);
    reloadTree();
  }

  async function handleRestructure() {
    setRestructuring(true);
    setRestructureMsg(null);
    setError(null);
    try {
      const result = await restructureTree(instruction || undefined);
      setRestructureMsg(`Listo — ${result.leaves_kept} hojas preservadas.`);
      setInstruction("");
      reloadTree();
      reloadSummary();
    } catch (e) {
      setError(e instanceof ApiError ? `No se pudo reestructurar: ${e.message}` : "No se pudo reestructurar");
    } finally {
      setRestructuring(false);
    }
  }

  const conversationsPageStart = conversationsTotal === 0 ? 0 : conversationsOffset + 1;
  const conversationsPageEnd = Math.min(conversationsOffset + CONVERSATIONS_PAGE_SIZE, conversationsTotal);

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div className="grid cols-2">
        <div className="card">
          <h2>Árbol de temas</h2>
          {tree ? (
            <TopicArboristTree
              tree={tree}
              canEdit={canRestructure}
              onSelect={handleTreeSelect}
              selectedTopicId={selectedNode ? (selectedNode.id ?? "root") : null}
              onChanged={handleTreeChanged}
            />
          ) : (
            <p className="muted">Cargando…</p>
          )}

          {canRestructure && (
            <>
              <h3 style={{ marginTop: 20 }}>Reestructurar (solo nodos, las hojas no cambian)</h3>
              <div className="field">
                <textarea
                  placeholder="Instrucción opcional, ej: 'agrupá todo lo de pagos bajo un mismo nodo'"
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  style={{ minHeight: 70 }}
                />
              </div>
              <button className="btn" onClick={handleRestructure} disabled={restructuring}>
                {restructuring ? "Reestructurando…" : "Reestructurar"}
              </button>
              {restructureMsg && <p className="muted" style={{ marginTop: 8 }}>{restructureMsg}</p>}
            </>
          )}
        </div>

        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>{selectedNode ? (selectedNode.id == null ? "Todos los temas" : selectedNode.name) : "Detalle del nodo"}</h2>
            {selectedNode && (
              <span className="pill unknown">
                {selectedNode.id == null ? "General" : selectedNode.type === "leaf" ? "Hoja" : "Nodo"}
              </span>
            )}
          </div>
          {!selectedNode && (
            <p className="empty-state">Elegí un nodo u hoja del árbol para ver el detalle agregado.</p>
          )}

          {selectedNode && (
            <>
              {/* Aggregated stats come straight from the tree payload already loaded above —
                  no extra request needed, and it scales to any subtree size since it's just counts. */}
              <div className="grid cols-2" style={{ marginBottom: 4 }}>
                <div className="stat-tile">
                  <div className="label">Documentos</div>
                  <div className="value">{selectedNode.document_count}</div>
                </div>
                <div className="stat-tile">
                  <div className="label">Conversaciones</div>
                  <div className="value">{selectedNode.conversation_count}</div>
                </div>
              </div>
              <div className="row" style={{ margin: "10px 0 18px" }}>
                <BreakdownBar breakdown={selectedNode.resolution_breakdown} />
                <span className="muted">
                  {selectedNode.resolution_breakdown.resolved} resueltas · {selectedNode.resolution_breakdown.partial}{" "}
                  parciales · {selectedNode.resolution_breakdown.unresolved} no resueltas ·{" "}
                  {selectedNode.resolution_breakdown.unknown} desconocidas
                </span>
              </div>

              <h3>Actividad por hora y día (hora Argentina)</h3>
              {heatmapLoading && <p className="muted">Cargando…</p>}
              {!heatmapLoading && heatmap && heatmap.total_conversations === 0 && (
                <p className="muted">Sin conversaciones en el período.</p>
              )}
              {!heatmapLoading && heatmap && heatmap.total_conversations > 0 && (
                <TopicActivityHeatmap cells={heatmap.cells} />
              )}
              {!heatmapLoading && !heatmap && <p className="muted">Sin datos suficientes.</p>}

              {selectedNode.id == null && (
                <p className="muted" style={{ marginTop: 18 }}>
                  Elegí un nodo o una hoja puntual para ver documentos y conversaciones.
                </p>
              )}

              {selectedNode.id != null && (
                <>
                <h3 style={{ marginTop: 18 }}>Documentos ({nodeDocs?.length ?? 0})</h3>
                {nodeDocs && nodeDocs.length === 0 && <p className="muted">Sin documentos asignados.</p>}
                {nodeDocs && nodeDocs.length > 0 && (
                  <div className="scroll-list">
                    {nodeDocs.map((doc) => (
                      <div key={doc.id} className="scroll-list-row">
                        <span className="name" title={doc.name}>
                          {doc.name}
                        </span>
                        {canRestructure && selectedNode.type === "leaf" && (
                          <button className="btn danger" onClick={() => handleUnassign(doc.id)}>
                            Desasignar
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <h3 style={{ marginTop: 18 }}>Conversaciones ({conversationsTotal})</h3>
                {conversations && conversations.length === 0 && <p className="muted">Sin conversaciones.</p>}
                {conversations && conversations.length > 0 && (
                  <div className="scroll-list">
                    {conversations.map((c) => (
                      <div key={c.conversation_id} className="scroll-list-row">
                        <span className="row">
                          #{c.conversation_id} <ResolutionPill resolution={c.resolution} />
                        </span>
                        <button className="btn" onClick={() => onOpenConversation(c.conversation_id)}>
                          Ver
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {conversationsTotal > CONVERSATIONS_PAGE_SIZE && selectedNode.id != null && (
                  <div className="row" style={{ justifyContent: "space-between", marginTop: 10 }}>
                    <span className="muted">
                      Mostrando {conversationsPageStart}–{conversationsPageEnd} de {conversationsTotal}
                    </span>
                    <div className="row">
                      <button
                        className="btn"
                        disabled={conversationsOffset === 0}
                        onClick={() => loadConversationsPage(selectedNode.id!, Math.max(0, conversationsOffset - CONVERSATIONS_PAGE_SIZE))}
                      >
                        Anterior
                      </button>
                      <button
                        className="btn"
                        disabled={conversationsPageEnd >= conversationsTotal}
                        onClick={() => loadConversationsPage(selectedNode.id!, conversationsOffset + CONVERSATIONS_PAGE_SIZE)}
                      >
                        Siguiente
                      </button>
                    </div>
                  </div>
                )}
                </>
              )}
            </>
          )}
        </div>
      </div>

      <div className="card">
        <h2>Ranking de resolución (peor primero)</h2>
        {rows && rows.length === 0 && <p className="empty-state">Todavía no hay conversaciones clasificadas.</p>}
        {rows && rows.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Tema</th>
                  {(
                    [
                      ["total_conversations", "Total"],
                      ["resolved", "Resueltos"],
                      ["partial", "Parciales"],
                      ["unresolved", "No resueltos"],
                      ["unknown", "Desconocidos"],
                      ["resolution_rate", "Tasa resolución"],
                    ] as [SortKey, string][]
                  ).map(([key, label]) => (
                    <th key={key} className="sortable" onClick={() => toggleSort(key)}>
                      {label} {sortKey === key ? (sortDir === "asc" ? "↑" : "↓") : ""}
                    </th>
                  ))}
                  <th>Documentación</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.topic_id}
                    onClick={() => selectRowTopic(row.topic_id)}
                    style={{
                      cursor: "pointer",
                      background:
                        selectedNode?.id === row.topic_id
                          ? "color-mix(in srgb, var(--series-1) 10%, transparent)"
                          : undefined,
                    }}
                  >
                    <td>{row.leaf_path}</td>
                    <td>{row.total_conversations}</td>
                    <td style={{ color: "var(--status-good)" }}>{row.resolved}</td>
                    <td
                      className={row.partial > 0 ? "clickable" : undefined}
                      style={{ color: "var(--status-warning)" }}
                      title={row.partial > 0 ? "Ver por qué" : undefined}
                      onClick={(e) => {
                        if (row.partial === 0) return;
                        e.stopPropagation();
                        openRootCause(row.topic_id, "partial");
                      }}
                    >
                      {row.partial}
                    </td>
                    <td
                      className={row.unresolved > 0 ? "clickable" : undefined}
                      style={{ color: "var(--status-critical)" }}
                      title={row.unresolved > 0 ? "Ver por qué" : undefined}
                      onClick={(e) => {
                        if (row.unresolved === 0) return;
                        e.stopPropagation();
                        openRootCause(row.topic_id, "unresolved");
                      }}
                    >
                      {row.unresolved}
                    </td>
                    <td style={{ color: "var(--status-unknown)" }}>{row.unknown}</td>
                    <td>{(row.resolution_rate * 100).toFixed(0)}%</td>
                    <td>{row.has_documentation ? "✓" : <span className="gap-flag">⚠ sin docs</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {rootCauseOpen && (
        <Modal title="Análisis de causa" onClose={() => setRootCauseOpen(false)}>
          {rootCauseLoading && <p className="muted">Analizando con el LLM…</p>}
          {rootCauseError && <ErrorBanner message={rootCauseError} />}
          {rootCause && (
            <div>
              <p className="muted" style={{ marginBottom: 12 }}>
                {rootCause.leaf_path} · {rootCause.resolution === "partial" ? "Parciales" : "No resueltos"} ·{" "}
                {rootCause.sample_size} de {rootCause.total_matching} analizadas
              </p>
              <h3 style={{ marginBottom: 4 }}>{rootCause.main_cause}</h3>
              <p>{rootCause.explanation}</p>
              {rootCause.secondary_causes.length > 0 && (
                <>
                  <h3 style={{ marginTop: 16, marginBottom: 4 }}>Causas secundarias</h3>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {rootCause.secondary_causes.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </>
              )}
              <div className="row" style={{ marginTop: 16 }}>
                <button className="btn primary" onClick={saveRootCauseAsNote} disabled={rootCauseSaving || rootCauseSaved}>
                  {rootCauseSaved ? "Guardada ✓" : rootCauseSaving ? "Guardando…" : "Guardar como nota"}
                </button>
                {rootCauseSaved && <span className="muted">Podés verla en la pestaña "Notas del Analista".</span>}
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
