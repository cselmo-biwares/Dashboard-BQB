import { useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api";
import { ErrorBanner } from "../components/ErrorBanner";

export function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Usuario o contraseña incorrectos" : "No se pudo iniciar sesión");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: "15vh" }}>
      <form className="card" style={{ width: 320 }} onSubmit={handleSubmit}>
        <h2>Iniciar sesión</h2>
        {error && <ErrorBanner message={error} />}
        <div className="field">
          <label htmlFor="username">Usuario</label>
          <input
            id="username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Contraseña</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <button className="btn primary" type="submit" disabled={loading} style={{ width: "100%" }}>
          {loading ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </div>
  );
}
