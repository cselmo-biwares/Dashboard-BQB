import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, createNote, deleteNote, listNotes, updateNote } from "../api";
import type { NoteOut } from "../types";
import { ErrorBanner } from "../components/ErrorBanner";
import { Markdown } from "../components/Markdown";

function NewNoteForm({ onCreated }: { onCreated: (n: NoteOut) => void }) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const created = await createNote({ title, content });
      onCreated(created);
      setTitle("");
      setContent("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear la nota");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2>Nueva nota</h2>
      {error && <ErrorBanner message={error} />}
      <div className="field">
        <label htmlFor="note-title">Título</label>
        <input id="note-title" value={title} onChange={(e) => setTitle(e.target.value)} required />
      </div>
      <div className="field">
        <label htmlFor="note-content">Contenido (admite markdown)</label>
        <textarea
          id="note-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          style={{ minHeight: 90 }}
          required
        />
      </div>
      <button className="btn primary" type="submit" disabled={saving}>
        {saving ? "Guardando…" : "Crear nota"}
      </button>
    </form>
  );
}

function formatFilterSnapshot(note: NoteOut): string | null {
  const parts: string[] = [];
  if (note.filter_source) parts.push(`canal: ${note.filter_source}`);
  if (note.filter_from || note.filter_to) {
    const from = note.filter_from ? new Date(note.filter_from).toLocaleDateString("es-AR") : "…";
    const to = note.filter_to ? new Date(note.filter_to).toLocaleDateString("es-AR") : "…";
    parts.push(`${from} – ${to}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

function NoteCard({ note, onChanged, onDeleted }: { note: NoteOut; onChanged: (n: NoteOut) => void; onDeleted: (id: number) => void }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(note.title);
  const [content, setContent] = useState(note.content);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSave() {
    setError(null);
    setBusy(true);
    try {
      const updated = await updateNote(note.id, title, content);
      onChanged(updated);
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm(`¿Borrar la nota "${note.title}"?`)) return;
    setError(null);
    setBusy(true);
    try {
      await deleteNote(note.id);
      onDeleted(note.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo borrar");
      setBusy(false);
    }
  }

  return (
    <div className="card">
      {error && <ErrorBanner message={error} />}
      {editing ? (
        <>
          <div className="field">
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="field">
            <textarea value={content} onChange={(e) => setContent(e.target.value)} style={{ minHeight: 90 }} />
          </div>
          <div className="row">
            <button className="btn primary" onClick={handleSave} disabled={busy}>
              Guardar
            </button>
            <button
              className="btn"
              onClick={() => {
                setTitle(note.title);
                setContent(note.content);
                setEditing(false);
              }}
              disabled={busy}
            >
              Cancelar
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>{note.title}</h2>
            {note.resolution && (
              <span className={`pill ${note.resolution === "unresolved" ? "unresolved" : "partial"}`}>
                {note.resolution === "unresolved" ? "No resuelto" : "Parcial"}
              </span>
            )}
          </div>
          {note.leaf_path && <p className="muted" style={{ marginTop: 2 }}>{note.leaf_path}</p>}
          {formatFilterSnapshot(note) && (
            <p className="muted" style={{ marginTop: 2, fontSize: 11.5 }}>
              Filtro al guardar: {formatFilterSnapshot(note)}
            </p>
          )}
          <Markdown>{note.content}</Markdown>
          <div className="row" style={{ justifyContent: "space-between", marginTop: 8 }}>
            <span className="muted">
              {note.created_by} · {new Date(note.created_at).toLocaleString("es-AR")}
              {note.updated_by !== note.created_by || note.updated_at !== note.created_at
                ? ` · editado por ${note.updated_by}`
                : ""}
            </span>
            <div className="row">
              <button className="btn" onClick={() => setEditing(true)} disabled={busy}>
                Editar
              </button>
              <button className="btn danger" onClick={handleDelete} disabled={busy}>
                Borrar
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function Notes() {
  const [notes, setNotes] = useState<NoteOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    listNotes()
      .then(setNotes)
      .catch((e) => setError(e instanceof ApiError ? e.message : "No se pudieron cargar las notas"));
  }

  useEffect(reload, []);

  return (
    <div>
      <NewNoteForm onCreated={(n) => setNotes((prev) => (prev ? [n, ...prev] : [n]))} />
      {error && <ErrorBanner message={error} />}
      {notes && notes.length === 0 && <p className="empty-state">Todavía no hay notas.</p>}
      {notes?.map((n) => (
        <NoteCard
          key={n.id}
          note={n}
          onChanged={(updated) => setNotes((prev) => prev!.map((x) => (x.id === updated.id ? updated : x)))}
          onDeleted={(id) => setNotes((prev) => prev!.filter((x) => x.id !== id))}
        />
      ))}
    </div>
  );
}
