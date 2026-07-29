import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { login as apiLogin, setAuthToken, setUnauthorizedHandler } from "../api";
import type { Role } from "../types";

const STORAGE_KEY = "dashboard-bqb-auth";

interface StoredSession {
  token: string;
  username: string;
  role: Role;
}

interface AuthContextValue {
  username: string | null;
  role: Role | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function loadSession(): StoredSession | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredSession;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Set synchronously during the lazy initializer (i.e. before any child renders/mounts),
  // not in a useEffect: effects fire child-first on mount, so a page that fetches on mount
  // (e.g. Overview) could otherwise run its request before the token was actually applied.
  const [session, setSession] = useState<StoredSession | null>(() => {
    const initial = loadSession();
    setAuthToken(initial?.token ?? null);
    return initial;
  });

  useEffect(() => {
    setUnauthorizedHandler(() => {
      localStorage.removeItem(STORAGE_KEY);
      setAuthToken(null);
      setSession(null);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      username: session?.username ?? null,
      role: session?.role ?? null,
      async login(username: string, password: string) {
        const result = await apiLogin(username, password);
        const next: StoredSession = { token: result.access_token, username: result.username, role: result.role };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        setAuthToken(next.token);
        setSession(next);
      },
      logout() {
        localStorage.removeItem(STORAGE_KEY);
        setAuthToken(null);
        setSession(null);
      },
    }),
    [session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
