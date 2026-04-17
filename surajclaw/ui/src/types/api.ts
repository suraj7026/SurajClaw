// API DTOs — keep aligned with surajclaw/api/serializers.py.

export type UUID = string;
export type ISODateString = string;

export interface User {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_superuser: boolean;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ---------------------------------------------------------------------------
// Sessions / messages / tasks
// ---------------------------------------------------------------------------
export type SessionSource = "telegram" | "web" | "cron" | "trigger";
export type MessageRole = "user" | "assistant" | "system" | "tool";
export type TaskStatus = "pending" | "running" | "done" | "failed";

export interface Session {
  id: UUID;
  source: SessionSource;
  started_at: ISODateString;
  ended_at: ISODateString | null;
  summary: string | null;
  is_active: boolean;
  message_count?: number;
}

export interface Message {
  id: UUID;
  session: UUID;
  role: MessageRole;
  content: string;
  model_used: string | null;
  tokens_used: number | null;
  created_at: ISODateString;
}

export interface Task {
  id: UUID;
  session: UUID | null;
  source: SessionSource;
  request: string;
  result: string | null;
  tools_used: string[];
  tokens_used: number | null;
  status: TaskStatus;
  created_at: ISODateString;
  completed_at: ISODateString | null;
}

// ---------------------------------------------------------------------------
// Cron jobs / runs / future queue
// ---------------------------------------------------------------------------
export type CronJobStatus = "active" | "paused" | "disabled";
export type CronJobScheduleKind = "at" | "every" | "cron";
export type CronJobDeliveryMode = "none" | "announce" | "webhook";

export interface CronJob {
  id: UUID;
  name: string;
  description: string;
  schedule_kind: CronJobScheduleKind;
  schedule_value: string;
  timezone: string;
  stagger_seconds: number;
  prompt: string;
  light_context: boolean;
  tools_allow: string[];
  delivery_mode: CronJobDeliveryMode;
  delivery_channel: string;
  delivery_to: string;
  delivery_webhook_url: string;
  fail_alert_after: number;
  fail_alert_cooldown_seconds: number;
  consecutive_failures: number;
  status: CronJobStatus;
  next_run_at: ISODateString | null;
  last_run_at: ISODateString | null;
  last_run_status: string;
  running_since: ISODateString | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export type CronRunStatus = "ok" | "error" | "skipped" | "timeout";

export interface CronRun {
  id: UUID;
  job: UUID;
  status: CronRunStatus;
  started_at: ISODateString;
  finished_at: ISODateString | null;
  duration_ms: number | null;
  model_used: string;
  provider_used: string;
  input_tokens: number | null;
  output_tokens: number | null;
  summary: string;
  error_text: string;
  delivery_status: string;
}

export type FutureQueueStatus = "pending" | "fired" | "cancelled";
export type FutureQueueTriggerType = "time" | "event" | "manual";

export interface FutureQueueItem {
  id: UUID;
  intent: string;
  due_at: ISODateString | null;
  trigger_type: FutureQueueTriggerType;
  status: FutureQueueStatus;
  source_session: UUID | null;
  created_at: ISODateString;
}

// ---------------------------------------------------------------------------
// Memory
// ---------------------------------------------------------------------------
export type EntityType = "person" | "project" | "company" | "preference";

export interface Entity {
  id: UUID;
  entity_type: EntityType;
  name: string;
  attributes: Record<string, unknown>;
  source_session: UUID | null;
  last_updated: ISODateString;
}

export interface NoteIndexItem {
  id: UUID;
  title: string;
  filename: string;
  content_preview: string;
  source_session: UUID | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export interface SessionEmbedding {
  id: UUID;
  session: UUID;
  summary_text: string;
  created_at: ISODateString;
}

export interface SimilarityHit {
  id: UUID;
  title: string;
  snippet: string;
  distance: number;
  kind: string;
}

export interface SimilarityResult {
  target: "entities" | "notes" | "sessions";
  query: string;
  hits: SimilarityHit[];
}

// ---------------------------------------------------------------------------
// System state, dream logs, metrics
// ---------------------------------------------------------------------------
export interface SystemStateItem {
  key: string;
  value: string;
  updated_at: ISODateString;
}

export interface DreamLog {
  id: UUID;
  trigger: "auto" | "manual";
  sessions_processed: number;
  entities_merged: number;
  entities_pruned: number;
  notes_updated: number;
  duration_seconds: number;
  summary: string;
  created_at: ISODateString;
}

export interface Metrics {
  active_sessions: number;
  active_jobs: number;
  pending_queue: number;
  total_tasks: number;
  success_rate: number;
  token_throughput: number;
  total_messages: number;
  total_entities: number;
  total_notes: number;
  last_dream_at: ISODateString | null;
}

// ---------------------------------------------------------------------------
// Doctor
// ---------------------------------------------------------------------------
export type DoctorStatus = "ok" | "warn" | "error";

export interface DoctorCheck {
  name: string;
  status: DoctorStatus;
  detail: string;
  extra?: Record<string, unknown>;
}

export interface DoctorReport {
  status: DoctorStatus;
  checks: DoctorCheck[];
}

// ---------------------------------------------------------------------------
// Google accounts
// ---------------------------------------------------------------------------
export interface GoogleAccount {
  label: string;
  email: string;
  scopes: string[];
  expires_at: ISODateString | null;
  token_path: string;
}

export interface GoogleConnectResponse {
  auth_url: string;
  state: string;
  label: string;
}
