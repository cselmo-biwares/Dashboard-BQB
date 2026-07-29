import { useEffect, useState, type FormEvent } from "react";
import { ApiError, createDocument, deleteDocument, listDocuments } from "../api";
import type { DocumentOut } from "../types";
import { ErrorBanner } from "../components/ErrorBanner";
import { Markdown } from "../components/Markdown";
import { Modal } from "../components/Modal";

export function Documents() {
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string | null>(null);
  const [viewing, setViewing] = useState<DocumentOut | null>(null);

  function reload() {
    listDocuments()
      .then(setDocuments)
      .catch((e) => setError(e instanceof ApiError ? e.message : "No se pudieron cargar los documentos"));
  }

  useEffect(reload, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || !content.trim()) return;
    setSubmitting(true);
    setError(null);
    setLastResult(null);
    try {
      const result = await createDocument(name.trim(), content);
      setLastResult(
        result.assigned_leaf_paths.length > 0
          ? `Asignado a: ${result.assigned_leaf_paths.join(", ")}`
          : "Clasificado, pero sin hojas asignadas (revisá el árbol).",
      );
      setName("");
      setContent("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? `No se pudo clasificar el documento: ${err.message}` : "Error inesperado");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id: number) {
    await deleteDocument(id);
    reload();
  }

  return (
    <div className="grid cols-2">
      <div className="card">
        <h2>Cargar documento</h2>
        {error && <ErrorBanner message={error} />}
        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="doc-name">Nombre</label>
            <input id="doc-name" type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="tarifas.md" />
          </div>
          <div className="field">
            <label htmlFor="doc-content">Contenido</label>
            <textarea id="doc-content" value={content} onChange={(e) => setContent(e.target.value)} placeholder="Contenido del documento…" />
          </div>
          <button className="btn primary" type="submit" disabled={submitting}>
            {submitting ? "Clasificando…" : "Cargar y clasificar"}
          </button>
        </form>
        {lastResult && <p className="muted" style={{ marginTop: 10 }}>{lastResult}</p>}
      </div>

      <div className="card">
        <h2>Documentos ({documents?.length ?? 0})</h2>
        {documents && documents.length === 0 && <p className="empty-state">Todavía no cargaste ningún documento.</p>}
        {documents?.map((doc) => (
          <div key={doc.id} className="row" style={{ justifyContent: "space-between", marginBottom: 8, paddingBottom: 8, borderBottom: "1px solid var(--gridline)" }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13.5 }}>{doc.name}</div>
              <div className="muted">{doc.content.slice(0, 80)}{doc.content.length > 80 ? "…" : ""}</div>
            </div>
            <div className="row">
              <button className="btn" onClick={() => setViewing(doc)}>
                Ver
              </button>
              <button className="btn danger" onClick={() => handleDelete(doc.id)}>
                Borrar
              </button>
            </div>
          </div>
        ))}
      </div>

      {viewing && (
        <Modal title={viewing.name} onClose={() => setViewing(null)}>
          <Markdown>{viewing.content}</Markdown>
        </Modal>
      )}
    </div>
  );
}
