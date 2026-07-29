import { useEffect, useState } from "react";
import { ApiError, listPrompts, resetPrompt, updatePrompt } from "../api";
import type { PromptKey, PromptOut } from "../types";
import { ErrorBanner } from "../components/ErrorBanner";
import { Markdown } from "../components/Markdown";

const LABELS: Record<PromptKey, string> = {
  classify_conversation: "Clasificar conversación (con resolución)",
  classify_document: "Clasificar documento",
  restructure: "Reestructurar árbol",
  root_cause: "Análisis de causa (parciales/no resueltos)",
};

function PromptCard({ prompt, onChanged }: { prompt: PromptOut; onChanged: (p: PromptOut) => void }) {
  const [content, setContent] = useState(prompt.content);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(true);

  useEffect(() => setContent(prompt.content), [prompt.content]);

  const dirty = content !== prompt.content;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updatePrompt(prompt.key, content);
      onChanged(updated);
      setPreviewing(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    setSaving(true);
    setError(null);
    try {
      const updated = await resetPrompt(prompt.key);
      onChanged(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo restaurar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>{LABELS[prompt.key]}</h2>
        <div className="row">
          {prompt.is_default ? (
            <span className="pill unknown">Default</span>
          ) : (
            <span className="pill resolved">Editado</span>
          )}
          <button
            className="btn"
            onClick={() => {
              if (!previewing) setContent(prompt.content);
              setPreviewing((p) => !p);
            }}
          >
            {previewing ? "Editar" : "Vista previa"}
          </button>
        </div>
      </div>
      {error && <ErrorBanner message={error} />}
      {previewing ? (
        <div className="card" style={{ background: "var(--page-plane)" }}>
          <Markdown>{content}</Markdown>
        </div>
      ) : (
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          style={{ minHeight: 260, fontFamily: "ui-monospace, monospace", fontSize: 12.5 }}
        />
      )}
      <div className="row" style={{ marginTop: 10, justifyContent: "space-between" }}>
        <span className="muted">
          {prompt.is_default ? "Usando el default del código." : `Editado ${prompt.updated_at ? new Date(prompt.updated_at).toLocaleString("es-AR") : ""}`}
        </span>
        {!previewing && (
          <div className="row">
            <button className="btn" onClick={handleReset} disabled={saving || prompt.is_default}>
              Restaurar default
            </button>
            <button className="btn primary" onClick={handleSave} disabled={saving || !dirty}>
              {saving ? "Guardando…" : "Guardar"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export function Prompts() {
  const [prompts, setPrompts] = useState<PromptOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    listPrompts()
      .then(setPrompts)
      .catch((e) => setError(e instanceof ApiError ? e.message : "No se pudieron cargar los prompts"));
  }

  useEffect(reload, []);

  function handleChanged(updated: PromptOut) {
    setPrompts((prev) => (prev ? prev.map((p) => (p.key === updated.key ? updated : p)) : prev));
  }

  return (
    <div>
      <p className="muted" style={{ marginBottom: 16 }}>
        Los cambios se aplican al toque — el próximo llamado al LLM ya usa el prompt guardado, no hace falta reiniciar la API.
      </p>
      {error && <ErrorBanner message={error} />}
      {prompts?.map((p) => <PromptCard key={p.key} prompt={p} onChanged={handleChanged} />)}
    </div>
  );
}
