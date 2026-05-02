import { api } from "./client";
import type {
  CronJob,
  CronRun,
  DoctorReport,
  DreamLog,
  Entity,
  FutureQueueItem,
  GoogleAccount,
  GoogleConnectResponse,
  Message,
  Metrics,
  NoteIndexItem,
  PaginatedResponse,
  Session,
  SessionEmbedding,
  SimilarityResult,
  SystemStateItem,
  Task,
  User,
  UUID,
  AgentInfo,
} from "@/types/api";

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export const authApi = {
  login: (username: string, password: string) =>
    api.post<{ token: string; user: User }>("/api/auth/login/", {
      username,
      password,
    }),
  logout: () => api.post<{ status: string }>("/api/auth/logout/"),
  me: () => api.get<User>("/api/auth/me/"),
};

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------
export const systemApi = {
  doctor: () => api.get<DoctorReport>("/api/doctor/"),
  health: () => api.get<{ status: string }>("/api/health/"),
  metrics: () => api.get<Metrics>("/api/metrics/"),
  systemState: () =>
    api.get<PaginatedResponse<SystemStateItem>>("/api/system-state/"),
  agents: () => api.get<{ agents: AgentInfo[] }>("/api/agents/"),
};

// ---------------------------------------------------------------------------
// Sessions / messages / tasks
// ---------------------------------------------------------------------------
export const sessionsApi = {
  list: (params?: { is_active?: boolean; source?: string; limit?: number }) =>
    api.get<PaginatedResponse<Session>>("/api/sessions/", { query: params }),
  retrieve: (id: UUID) => api.get<Session>(`/api/sessions/${id}/`),
  messages: (id: UUID, limit = 200) =>
    api.get<PaginatedResponse<Message> | Message[]>(
      `/api/sessions/${id}/messages/`,
      { query: { limit } },
    ),
};

export const tasksApi = {
  list: (params?: { status?: string; source?: string; limit?: number }) =>
    api.get<PaginatedResponse<Task>>("/api/tasks/", { query: params }),
};

// ---------------------------------------------------------------------------
// Cron jobs / runs / future queue
// ---------------------------------------------------------------------------
export const cronJobsApi = {
  list: (params?: { status?: string; limit?: number }) =>
    api.get<PaginatedResponse<CronJob>>("/api/cron-jobs/", { query: params }),
  retrieve: (id: UUID) => api.get<CronJob>(`/api/cron-jobs/${id}/`),
  runs: (id: UUID, limit = 25) =>
    api.get<PaginatedResponse<CronRun> | CronRun[]>(
      `/api/cron-jobs/${id}/runs/`,
      { query: { limit } },
    ),
  trigger: (id: UUID) =>
    api.post<{ status: string; next_run_at: string }>(
      `/api/cron-jobs/${id}/trigger/`,
    ),
  pause: (id: UUID) =>
    api.patch<CronJob>(`/api/cron-jobs/${id}/`, { status: "paused" }),
  resume: (id: UUID) =>
    api.patch<CronJob>(`/api/cron-jobs/${id}/`, { status: "active" }),
};

export const futureQueueApi = {
  list: (params?: { status?: string; limit?: number }) =>
    api.get<PaginatedResponse<FutureQueueItem>>("/api/future-queue/", {
      query: params,
    }),
  cancel: (id: UUID) => api.delete<void>(`/api/future-queue/${id}/`),
};

// ---------------------------------------------------------------------------
// Memory
// ---------------------------------------------------------------------------
export const memoryApi = {
  entities: (params?: { entity_type?: string; limit?: number }) =>
    api.get<PaginatedResponse<Entity>>("/api/memory/entities/", {
      query: params,
    }),
  notes: (params?: { limit?: number }) =>
    api.get<PaginatedResponse<NoteIndexItem>>("/api/memory/notes/", {
      query: params,
    }),
  sessionEmbeddings: (params?: { limit?: number }) =>
    api.get<PaginatedResponse<SessionEmbedding>>(
      "/api/memory/session-embeddings/",
      { query: params },
    ),
  search: (
    query: string,
    target: "notes" | "entities" | "sessions" = "notes",
    limit = 5,
  ) =>
    api.post<SimilarityResult>("/api/memory/search/", {
      query,
      target,
      limit,
    }),
  dreamLogs: (params?: { limit?: number }) =>
    api.get<PaginatedResponse<DreamLog>>("/api/dream-logs/", {
      query: params,
    }),
};

// ---------------------------------------------------------------------------
// Google accounts
// ---------------------------------------------------------------------------
export const googleApi = {
  list: () => api.get<GoogleAccount[]>("/api/google/accounts/"),
  connect: (label: string) =>
    api.post<GoogleConnectResponse>(
      `/api/google/accounts/${encodeURIComponent(label)}/connect/`,
    ),
  disconnect: (label: string) =>
    api.delete<{ status: string }>(
      `/api/google/accounts/${encodeURIComponent(label)}/`,
    ),
};
