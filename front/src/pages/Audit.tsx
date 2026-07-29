import { useEffect, useState } from "react";
import { ApiError, listAuditLog } from "../api";
import type { AuditLogOut } from "../types";
import { ErrorBanner } from "../components/ErrorBanner";

export function Audit() {
  const [entries, setEntries] = useState<AuditLogOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [usernameFilter, setUsernameFilter] = useState("");

  function reload() {
    listAuditLog({ username: usernameFilter || undefined, limit: 200 })
      .then(setEntries)
      .catch((e) => setError(e instanceof ApiError ? e.message : "No se pudo cargar la auditoría"));
  }

  useEffect(reload, [usernameFilter]);

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Auditoría (logins y operaciones)</h2>
        <div className="field" style={{ marginBottom: 0, width: 220 }}>
          <input
            type="text"
            placeholder="Filtrar por usuario"
            value={usernameFilter}
            onChange={(e) => setUsernameFilter(e.target.value)}
          />
        </div>
      </div>
      {error && <ErrorBanner message={error} />}
      {entries && entries.length === 0 && <p className="muted">Sin actividad registrada.</p>}
      {entries && entries.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Usuario</th>
              <th>Rol</th>
              <th>Acción</th>
              <th>Detalle</th>
              <th>IP</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td className="muted">{new Date(e.created_at).toLocaleString("es-AR")}</td>
                <td>{e.username}</td>
                <td>{e.role}</td>
                <td>
                  <span className={e.action === "login_failed" ? "pill unresolved" : "pill resolved"}>
                    {e.action}
                  </span>
                </td>
                <td>{e.detail ?? ""}</td>
                <td className="muted">{e.ip_address ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
