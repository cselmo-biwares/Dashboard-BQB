import { useEffect, useState, type FormEvent } from "react";
import { ApiError, getConversation } from "../api";
import type { ConversationDetailOut } from "../types";
import { ResolutionPill } from "../components/ResolutionPill";
import { ErrorBanner } from "../components/ErrorBanner";

export function ConversationDetail({ requestedId }: { requestedId: number | null }) {
  const [idInput, setIdInput] = useState("");
  const [conversation, setConversation] = useState<ConversationDetailOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search(id: number) {
    setLoading(true);
    setError(null);
    setConversation(null);
    try {
      const result = await getConversation(id);
      setConversation(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo cargar la conversación");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (requestedId != null) {
      setIdInput(String(requestedId));
      search(requestedId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedId]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const id = Number(idInput);
    if (!Number.isFinite(id) || id <= 0) return;
    search(id);
  }

  return (
    <div className="card">
      <h2>Detalle de conversación</h2>
      <form onSubmit={handleSubmit} className="row" style={{ marginBottom: 16 }}>
        <input
          type="number"
          placeholder="ID de conversación"
          value={idInput}
          onChange={(e) => setIdInput(e.target.value)}
          style={{ width: 180 }}
        />
        <button className="btn primary" type="submit" disabled={loading}>
          {loading ? "Buscando…" : "Buscar"}
        </button>
      </form>

      {error && <ErrorBanner message={error} />}

      {conversation && (
        <div className="grid cols-2">
          <div>
            <h3>Metadata</h3>
            <table>
              <tbody>
                <tr>
                  <td className="muted">Canal</td>
                  <td>{conversation.source}</td>
                </tr>
                <tr>
                  <td className="muted">Estado</td>
                  <td>{conversation.status}</td>
                </tr>
                <tr>
                  <td className="muted">Facturable</td>
                  <td>{conversation.billable ? "Sí" : "No"}</td>
                </tr>
                <tr>
                  <td className="muted">Creada</td>
                  <td>{new Date(conversation.created_at).toLocaleString("es-AR")}</td>
                </tr>
                <tr>
                  <td className="muted">Cerrada</td>
                  <td>{conversation.closed_at ? new Date(conversation.closed_at).toLocaleString("es-AR") : "—"}</td>
                </tr>
              </tbody>
            </table>

            <h3 style={{ marginTop: 18 }}>Temas clasificados</h3>
            {conversation.topics.length === 0 && <p className="muted">Sin temas identificados.</p>}
            {conversation.topics.map((t) => (
              <div key={t.leaf_path} style={{ marginBottom: 10 }}>
                <div className="row">
                  <strong style={{ fontSize: 13 }}>{t.leaf_path}</strong>
                  <ResolutionPill resolution={t.resolution} />
                </div>
                <div className="muted">{t.reasoning}</div>
              </div>
            ))}
          </div>

          <div>
            <h3>Transcripción</h3>
            <div style={{ maxHeight: 480, overflowY: "auto" }}>
              {conversation.messages.map((m) => (
                <div key={m.id} className={`message-bubble ${m.role === "assistant" ? "assistant" : "user"}`}>
                  <div className="role">{m.role}</div>
                  <div>{m.content ?? <em className="muted">(sin contenido de texto)</em>}</div>
                  <div className="timestamp">{new Date(m.timestamp).toLocaleString("es-AR")}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
