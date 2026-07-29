import { useState } from "react";
import logo from "./assets/logo.webp";
import { Overview } from "./pages/Overview";
import { Topics } from "./pages/Topics";
import { Documents } from "./pages/Documents";
import { Ingestion } from "./pages/Ingestion";
import { ConversationDetail } from "./pages/ConversationDetail";
import { Prompts } from "./pages/Prompts";
import { Users } from "./pages/Users";
import { Audit } from "./pages/Audit";
import { Notes } from "./pages/Notes";
import { Login } from "./pages/Login";
import { useAuth } from "./auth/AuthContext";
import type { Role } from "./types";
import { EMPTY_FILTERS, GlobalFilterBar, type GlobalFilters } from "./components/GlobalFilterBar";

type Tab =
  | "overview"
  | "topics"
  | "documents"
  | "ingestion"
  | "conversation"
  | "prompts"
  | "notes"
  | "users"
  | "audit";

const TABS: { key: Tab; label: string; roles: Role[] }[] = [
  { key: "overview", label: "Overview", roles: ["admin", "editor", "analyst"] },
  { key: "topics", label: "Temas", roles: ["admin", "editor", "analyst"] },
  { key: "conversation", label: "Conversación", roles: ["admin", "editor", "analyst"] },
  { key: "notes", label: "Notas del Analista", roles: ["admin", "editor", "analyst"] },
  { key: "documents", label: "Documentos", roles: ["admin", "editor"] },
  { key: "ingestion", label: "Ingesta", roles: ["admin", "editor"] },
  { key: "prompts", label: "Prompts", roles: ["admin", "editor"] },
  { key: "users", label: "Usuarios", roles: ["admin"] },
  { key: "audit", label: "Auditoría", roles: ["admin"] },
];

export default function App() {
  const { username, role, logout } = useAuth();
  const [tab, setTab] = useState<Tab>("overview");
  const [requestedConversationId, setRequestedConversationId] = useState<number | null>(null);
  const [filters, setFilters] = useState<GlobalFilters>(EMPTY_FILTERS);

  function openConversation(id: number) {
    setRequestedConversationId(id);
    setTab("conversation");
  }

  if (!role) {
    return (
      <div className="app-shell">
        <div className="topbar">
          <div className="row" style={{ gap: 12 }}>
            <img src={logo} alt="Biwares" width={36} height={36} style={{ borderRadius: 8 }} />
            <h1>Dashboard BQB</h1>
          </div>
        </div>
        <Login />
      </div>
    );
  }

  const visibleTabs = TABS.filter((t) => t.roles.includes(role));
  const activeTab = visibleTabs.some((t) => t.key === tab) ? tab : visibleTabs[0].key;

  return (
    <div className="app-shell">
      <div className="topbar">
        <div className="row" style={{ gap: 12 }}>
          <img src={logo} alt="Biwares" width={36} height={36} style={{ borderRadius: 8 }} />
          <div>
            <h1>Dashboard BQB</h1>
            <div className="subtitle">API: {import.meta.env.VITE_API_URL}</div>
          </div>
        </div>
        <div className="row" style={{ gap: 12 }}>
          <span className="muted">
            {username} ({role})
          </span>
          <button className="btn" onClick={logout}>
            Salir
          </button>
        </div>
      </div>

      {(activeTab === "overview" || activeTab === "topics") && (
        <GlobalFilterBar value={filters} onChange={setFilters} />
      )}

      <nav className="tabs">
        {visibleTabs.map((t) => (
          <button key={t.key} className={activeTab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </nav>

      {activeTab === "overview" && <Overview filters={filters} />}
      {activeTab === "topics" && (
        <Topics onOpenConversation={openConversation} canRestructure={role !== "analyst"} filters={filters} />
      )}
      {activeTab === "documents" && <Documents />}
      {activeTab === "ingestion" && <Ingestion />}
      {activeTab === "conversation" && <ConversationDetail requestedId={requestedConversationId} />}
      {activeTab === "notes" && <Notes />}
      {activeTab === "prompts" && <Prompts />}
      {activeTab === "users" && <Users />}
      {activeTab === "audit" && <Audit />}
    </div>
  );
}
