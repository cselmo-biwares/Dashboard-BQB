import type {
  ActivityHeatmapResult,
  AuditLogOut,
  ConversationDetailOut,
  ConversationTopicPage,
  DocumentClassifyResult,
  DocumentOut,
  IngestionRunOut,
  IngestionUpdateAccepted,
  IngestionUpdateRequest,
  LoginResponse,
  NoteOut,
  PromptKey,
  PromptOut,
  ResolutionSummaryRow,
  RestructureResult,
  RootCauseResult,
  SourceBreakdownRow,
  StatsOverview,
  TopicNode,
  TopicOut,
  UnprocessRequest,
  UnprocessResult,
  UserOut,
  UserRole,
  VolumeTrendPoint,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_URL;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}

export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      onUnauthorized?.();
    }
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // response had no JSON body
    }
    throw new ApiError(response.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// --- Auth ---

export const login = (username: string, password: string) =>
  request<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });

// --- Users (admin only) ---

export const listUsers = () => request<UserOut[]>("/users");

export const createUser = (username: string, password: string, role: UserRole) =>
  request<UserOut>("/users", { method: "POST", body: JSON.stringify({ username, password, role }) });

export const updateUser = (userId: number, payload: { password?: string; role?: UserRole }) =>
  request<UserOut>(`/users/${userId}`, { method: "PUT", body: JSON.stringify(payload) });

export const deleteUser = (userId: number) => request<void>(`/users/${userId}`, { method: "DELETE" });

// --- Audit log (admin only) ---

export const listAuditLog = (params: { username?: string; action?: string; limit?: number; offset?: number } = {}) =>
  request<AuditLogOut[]>(`/audit${qs(params)}`);

function qs(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
}

// --- Topics ---

export const getTopicTree = (params: { from?: string; to?: string; source?: string } = {}) =>
  request<TopicNode>(`/topics/tree${qs(params)}`);

export const getResolutionSummary = (params: {
  source?: string;
  from?: string;
  to?: string;
  order_by?: "resolution_rate" | "total_conversations" | "resolved" | "partial" | "unresolved" | "unknown";
  dir?: "asc" | "desc";
  limit?: number;
}) => request<ResolutionSummaryRow[]>(`/topics/resolution-summary${qs(params)}`);

export const getTopicDocuments = (topicId: number) => request<DocumentOut[]>(`/topics/${topicId}/documents`);

export const unassignDocument = (topicId: number, documentId: number) =>
  request<void>(`/topics/${topicId}/documents/${documentId}`, { method: "DELETE" });

export const getTopicConversations = (
  topicId: number,
  limit = 20,
  offset = 0,
  params: { source?: string; from?: string; to?: string } = {},
) => request<ConversationTopicPage>(`/topics/${topicId}/conversations${qs({ ...params, limit, offset })}`);

export const restructureTree = (instruction?: string) =>
  request<RestructureResult>("/topics/restructure", {
    method: "POST",
    body: JSON.stringify({ instruction: instruction || null }),
  });

export const createTopic = (parentId: number | null, name: string, type: "node" | "leaf") =>
  request<TopicOut>("/topics", { method: "POST", body: JSON.stringify({ parent_id: parentId, name, type }) });

export const renameTopic = (topicId: number, name: string) =>
  request<TopicOut>(`/topics/${topicId}`, { method: "PATCH", body: JSON.stringify({ name }) });

export const moveTopic = (topicId: number, parentId: number | null) =>
  request<TopicOut>(`/topics/${topicId}/move`, { method: "PATCH", body: JSON.stringify({ parent_id: parentId }) });

export const deleteTopic = (topicId: number) => request<void>(`/topics/${topicId}`, { method: "DELETE" });

export const getRootCause = (
  topicId: number,
  resolution: "partial" | "unresolved",
  params: { source?: string; from?: string; to?: string } = {},
) => request<RootCauseResult>(`/topics/${topicId}/root-cause${qs({ resolution, ...params })}`);

export const getActivityHeatmap = (
  topicId: number,
  params: { source?: string; from?: string; to?: string } = {},
) => request<ActivityHeatmapResult>(`/topics/${topicId}/activity-heatmap${qs(params)}`);

export const getWholeTreeActivityHeatmap = (params: { source?: string; from?: string; to?: string } = {}) =>
  request<ActivityHeatmapResult>(`/topics/activity-heatmap${qs(params)}`);

// --- Analyst notes ---

export const listNotes = (topicId?: number) => request<NoteOut[]>(`/notes${qs({ topic_id: topicId })}`);

export const createNote = (payload: {
  title: string;
  content: string;
  topic_id?: number | null;
  leaf_path?: string | null;
  resolution?: "partial" | "unresolved" | null;
  filter_source?: string | null;
  filter_from?: string | null;
  filter_to?: string | null;
}) => request<NoteOut>("/notes", { method: "POST", body: JSON.stringify(payload) });

export const updateNote = (noteId: number, title: string, content: string) =>
  request<NoteOut>(`/notes/${noteId}`, { method: "PUT", body: JSON.stringify({ title, content }) });

export const deleteNote = (noteId: number) => request<void>(`/notes/${noteId}`, { method: "DELETE" });

// --- Documents ---

export const listDocuments = () => request<DocumentOut[]>("/documents");

export const createDocument = (name: string, content: string) =>
  request<DocumentClassifyResult>("/documents", { method: "POST", body: JSON.stringify({ name, content }) });

export const deleteDocument = (documentId: number) => request<void>(`/documents/${documentId}`, { method: "DELETE" });

// --- Ingestion ---

export const triggerIngestionUpdate = (filters?: IngestionUpdateRequest) =>
  request<IngestionUpdateAccepted>("/ingestion/update", {
    method: "POST",
    body: filters && Object.keys(filters).length > 0 ? JSON.stringify(filters) : undefined,
  });

export const unprocessConversations = (filters: UnprocessRequest) =>
  request<UnprocessResult>("/ingestion/unprocess", { method: "POST", body: JSON.stringify(filters) });

export const getLatestIngestionRun = () => request<IngestionRunOut>("/ingestion/runs/latest");

export const getIngestionRun = (runId: number) => request<IngestionRunOut>(`/ingestion/runs/${runId}`);

// --- Stats ---

export const getStatsOverview = (params: { source?: string; from?: string; to?: string } = {}) =>
  request<StatsOverview>(`/stats/overview${qs(params)}`);

export const getVolumeTrend = (
  params: { source?: string; interval?: "day" | "week" | "month"; from?: string; to?: string } = {},
) => request<VolumeTrendPoint[]>(`/stats/volume-trend${qs(params)}`);

export const getStatsBySource = (params: { from?: string; to?: string } = {}) =>
  request<SourceBreakdownRow[]>(`/stats/by-source${qs(params)}`);

// --- Conversations ---

export const getConversation = (conversationId: number) =>
  request<ConversationDetailOut>(`/conversations/${conversationId}`);

// --- Prompts ---

export const listPrompts = () => request<PromptOut[]>("/prompts");

export const updatePrompt = (key: PromptKey, content: string) =>
  request<PromptOut>(`/prompts/${key}`, { method: "PUT", body: JSON.stringify({ content }) });

export const resetPrompt = (key: PromptKey) => request<PromptOut>(`/prompts/${key}/reset`, { method: "POST" });
