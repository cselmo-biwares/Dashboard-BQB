import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, createUser, deleteUser, listUsers, updateUser } from "../api";
import type { UserOut, UserRole } from "../types";
import { ErrorBanner } from "../components/ErrorBanner";

const ROLE_LABELS: Record<UserRole, string> = { editor: "Editor", analyst: "Analista" };

function NewUserForm({ onCreated }: { onCreated: (u: UserOut) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("editor");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const created = await createUser(username, password, role);
      onCreated(created);
      setUsername("");
      setPassword("");
      setRole("editor");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear el usuario");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2>Nuevo usuario</h2>
      {error && <ErrorBanner message={error} />}
      <div className="row" style={{ alignItems: "flex-end" }}>
        <div className="field" style={{ marginBottom: 0, flex: 1 }}>
          <label htmlFor="new-username">Usuario</label>
          <input id="new-username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div className="field" style={{ marginBottom: 0, flex: 1 }}>
          <label htmlFor="new-password">Contraseña</label>
          <input
            id="new-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="new-role">Rol</label>
          <select id="new-role" value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
            <option value="editor">Editor</option>
            <option value="analyst">Analista</option>
          </select>
        </div>
        <button className="btn primary" type="submit" disabled={saving}>
          {saving ? "Creando…" : "Crear"}
        </button>
      </div>
    </form>
  );
}

function UserRow({ user, onChanged, onDeleted }: { user: UserOut; onChanged: (u: UserOut) => void; onDeleted: (id: number) => void }) {
  const [role, setRole] = useState<UserRole>(user.role);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleUpdate() {
    setError(null);
    setBusy(true);
    try {
      const payload: { password?: string; role?: UserRole } = {};
      if (role !== user.role) payload.role = role;
      if (password) payload.password = password;
      const updated = await updateUser(user.id, payload);
      onChanged(updated);
      setPassword("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm(`¿Borrar el usuario "${user.username}"?`)) return;
    setError(null);
    setBusy(true);
    try {
      await deleteUser(user.id);
      onDeleted(user.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo borrar");
      setBusy(false);
    }
  }

  const dirty = role !== user.role || password.length > 0;

  return (
    <tr>
      <td>{user.username}</td>
      <td>
        <select value={role} onChange={(e) => setRole(e.target.value as UserRole)} disabled={busy}>
          <option value="editor">Editor</option>
          <option value="analyst">Analista</option>
        </select>
      </td>
      <td>
        <input
          type="password"
          placeholder="Nueva contraseña"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={8}
          disabled={busy}
        />
      </td>
      <td className="muted">{new Date(user.created_at).toLocaleString("es-AR")}</td>
      <td>
        <div className="row">
          <button className="btn" onClick={handleUpdate} disabled={busy || !dirty}>
            Guardar
          </button>
          <button className="btn danger" onClick={handleDelete} disabled={busy}>
            Borrar
          </button>
        </div>
        {error && <ErrorBanner message={error} />}
      </td>
    </tr>
  );
}

export function Users() {
  const [users, setUsers] = useState<UserOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    listUsers()
      .then(setUsers)
      .catch((e) => setError(e instanceof ApiError ? e.message : "No se pudieron cargar los usuarios"));
  }

  useEffect(reload, []);

  return (
    <div>
      <NewUserForm onCreated={(u) => setUsers((prev) => (prev ? [...prev, u] : [u]))} />
      <div className="card">
        <h2>
          Usuarios ({ROLE_LABELS.editor}/{ROLE_LABELS.analyst})
        </h2>
        {error && <ErrorBanner message={error} />}
        {users && users.length === 0 && <p className="muted">Todavía no hay usuarios creados.</p>}
        {users && users.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Rol</th>
                <th>Contraseña</th>
                <th>Creado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  onChanged={(updated) => setUsers((prev) => prev!.map((x) => (x.id === updated.id ? updated : x)))}
                  onDeleted={(id) => setUsers((prev) => prev!.filter((x) => x.id !== id))}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
