// Mirrors app/schemas/*.py exactly — keep in sync with the backend.

export type Role = "admin" | "editor" | "analyst";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  username: string;
  role: Role;
}

export type UserRole = "editor" | "analyst";

export interface UserOut {
  id: number;
  username: string;
  role: UserRole;
  created_at: string;
  updated_at: string;
}

export interface AuditLogOut {
  id: number;
  username: string;
  role: string;
  action: string;
  detail: string | null;
  ip_address: string | null;
  created_at: string;
}

export type Resolution = "resolved" | "partial" | "unresolved" | "unknown";

export type PromptKey = "classify_conversation" | "classify_document" | "restructure" | "root_cause";

export interface PromptOut {
  key: PromptKey;
  content: string;
  is_default: boolean;
  updated_at: string | null;
}

export interface ResolutionBreakdown {
  resolved: number;
  partial: number;
  unresolved: number;
  unknown: number;
}

export interface TopicNode {
  id: number | null;
  name: string;
  type: "node" | "leaf";
  document_count: number;
  conversation_count: number;
  resolution_breakdown: ResolutionBreakdown;
  children: TopicNode[];
}

export interface ResolutionSummaryRow {
  topic_id: number;
  leaf_path: string;
  total_conversations: number;
  resolved: number;
  partial: number;
  unresolved: number;
  unknown: number;
  resolution_rate: number;
  has_documentation: boolean;
}

export interface ConversationTopicOut {
  conversation_id: number;
  resolution: Resolution;
  reasoning: string;
  created_at: string;
}

export interface ConversationTopicPage {
  total: number;
  items: ConversationTopicOut[];
}

export interface RestructureResult {
  leaves_kept: number;
}

export interface TopicOut {
  id: number;
  parent_id: number | null;
  name: string;
  type: "node" | "leaf";
}

export interface NoteOut {
  id: number;
  title: string;
  content: string;
  topic_id: number | null;
  leaf_path: string | null;
  resolution: "partial" | "unresolved" | null;
  filter_source: string | null;
  filter_from: string | null;
  filter_to: string | null;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

export interface RootCauseResult {
  topic_id: number;
  leaf_path: string;
  resolution: "partial" | "unresolved";
  total_matching: number;
  sample_size: number;
  main_cause: string;
  explanation: string;
  secondary_causes: string[];
}

export interface ActivityHeatmapCell {
  day_of_week: number;
  hour: number;
  total: number;
  average: number;
}

export interface ActivityHeatmapResult {
  topic_id: number | null;
  leaf_path: string;
  total_conversations: number;
  cells: ActivityHeatmapCell[];
}

export interface DocumentOut {
  id: number;
  name: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentClassifyResult {
  document: DocumentOut;
  assigned_leaf_paths: string[];
}

export type ConversationStatus = "in_progress" | "closed_timeout" | "closed_agent" | "redirected";

export interface IngestionUpdateRequest {
  source?: string;
  status?: ConversationStatus;
  billable?: boolean;
  created_date_from?: string;
  created_date_to?: string;
  min_age_hours?: number;
  page_size?: number;
}

export interface UnprocessRequest {
  source?: string;
  created_date_from?: string;
  created_date_to?: string;
}

export interface UnprocessResult {
  conversations_affected: number;
  topic_assignments_removed: number;
}

export interface IngestionUpdateAccepted {
  run_id: number;
}

export interface IngestionRunOut {
  id: number;
  status: "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  conversations_processed: number;
  conversations_failed: number;
  error: string | null;
}

export interface StatsOverview {
  total_conversations: number;
  resolved: number;
  partial: number;
  unresolved: number;
  unknown: number;
  overall_resolution_rate: number;
}

export interface VolumeTrendPoint {
  period_start: string;
  total_conversations: number;
  resolved: number;
  partial: number;
  unresolved: number;
  unknown: number;
}

export interface SourceBreakdownRow {
  source: string;
  total_conversations: number;
  resolved: number;
  partial: number;
  unresolved: number;
  unknown: number;
  overall_resolution_rate: number;
}

export interface ConversationMessageOut {
  id: number;
  role: string;
  timestamp: string;
  content: string | null;
}

export interface ConversationTopicAssignment {
  leaf_path: string;
  resolution: Resolution;
  reasoning: string;
}

export interface ConversationDetailOut {
  id: number;
  source: string;
  status: string;
  billable: boolean;
  created_at: string;
  closed_at: string | null;
  messages: ConversationMessageOut[];
  topics: ConversationTopicAssignment[];
}
