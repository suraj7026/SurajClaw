import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { sessionsApi, systemApi, tasksApi } from "@/api/endpoints";
import { useApi } from "@/hooks/useApi";
import { Panel } from "@/components/shared/Panel";
import { MetricCard } from "@/components/shared/MetricCard";
import { ProgressBar } from "@/components/shared/ProgressBar";
import { StatusIndicator } from "@/components/shared/StatusIndicator";
import { LogEntry } from "@/components/shared/LogEntry";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  formatDateTime,
  formatNumber,
  formatPercent,
  formatRelative,
  truncate,
} from "@/lib/format";
import type {
  DoctorCheck,
  DoctorStatus,
  PaginatedResponse,
  Session,
  Task,
} from "@/types/api";

interface FeedItem {
  id: string;
  ts: string;
  tag: string;
  message: string;
  tone: "info" | "ok" | "warn" | "error" | "muted" | "primary";
}

const STATUS_LABEL: Record<DoctorStatus, string> = {
  ok: "All Systems Operational",
  warn: "Degraded Performance",
  error: "Critical Alert",
};

const STATUS_TONE: Record<DoctorStatus, "ok" | "warn" | "error"> = {
  ok: "ok",
  warn: "warn",
  error: "error",
};

function checkIcon(name: string): string {
  if (name.includes("database")) return "database";
  if (name.includes("pgvector")) return "memory";
  if (name.includes("redis")) return "bolt";
  if (name.includes("gemini")) return "auto_awesome";
  if (name.includes("celery") || name.includes("beat")) return "schedule";
  if (name.includes("owner") || name.includes("auth")) return "shield";
  if (name.includes("filesystem") || name.includes("workspace")) return "folder";
  return "monitor_heart";
}

function tasksToFeed(tasks: Task[]): FeedItem[] {
  return tasks.slice(0, 12).map((t) => ({
    id: t.id,
    ts: t.created_at,
    tag: `TASK·${t.source}`,
    message: truncate(t.request, 100),
    tone:
      t.status === "done"
        ? "ok"
        : t.status === "failed"
          ? "error"
          : t.status === "running"
            ? "primary"
            : "info",
  }));
}

export default function Dashboard() {
  const { data: doctor } = useApi(() => systemApi.doctor(), [], { pollMs: 30_000 });
  const { data: metrics } = useApi(() => systemApi.metrics(), [], {
    pollMs: 15_000,
  });
  const { data: sessions } = useApi(
    () => sessionsApi.list({ is_active: true, limit: 6 }),
    [],
    { pollMs: 20_000 },
  );
  const { data: tasks } = useApi(() => tasksApi.list({ limit: 12 }), [], {
    pollMs: 20_000,
  });

  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const feedItems = useMemo<FeedItem[]>(() => {
    const taskFeed = tasksToFeed(tasks?.results ?? []);
    const dreamItems: FeedItem[] = metrics?.last_dream_at
      ? [
          {
            id: "dream",
            ts: metrics.last_dream_at,
            tag: "DREAM",
            message: "Memory consolidation cycle completed",
            tone: "primary",
          },
        ]
      : [];
    return [...taskFeed, ...dreamItems].sort(
      (a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime(),
    );
  }, [tasks, metrics]);

  const subsystemChecks: DoctorCheck[] = doctor?.checks ?? [];

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="SURAJCLAW | Health & Observability"
        subtitle="Global latency, traffic distribution, and live telemetry."
        icon="monitoring"
      />

      {/* Global Health Status Banner */}
      <div className="mb-6 p-4 flex items-center justify-between border-l-4 border-tertiary bg-bg-surface rounded-lg">
        <div className="flex items-center gap-4">
          <div className="relative">
            <span className="block w-3 h-3 bg-tertiary rounded-full animate-pulse" />
            <span className="absolute top-0 left-0 w-3 h-3 bg-tertiary rounded-full animate-ping" />
          </div>
          <div>
            <p className="text-[10px] font-display text-ink-mute tracking-widest uppercase">
              System Diagnosis
            </p>
            <h2 className="text-xl font-display font-bold text-tertiary">
              {doctor ? STATUS_LABEL[doctor.status] : "Initializing..."}
            </h2>
          </div>
        </div>
        <div className="hidden sm:flex gap-8">
          <div className="text-right">
            <p className="text-[10px] font-display text-ink-mute uppercase tracking-widest">
              Active Requests
            </p>
            <p className="text-primary font-display font-bold">
              {formatNumber(metrics?.active_sessions ?? 0)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] font-display text-ink-mute uppercase tracking-widest">
              UTC Time
            </p>
            <p className="text-primary font-display font-bold font-mono text-sm">
              {now.toISOString().slice(11, 19)}
            </p>
          </div>
        </div>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
        <MetricCard
          label="Active Sessions"
          value={formatNumber(metrics?.active_sessions ?? 0)}
          tone="primary"
          icon="forum"
          hint="Live conversations"
        />
        <MetricCard
          label="Active Cron Jobs"
          value={formatNumber(metrics?.active_jobs ?? 0)}
          tone="secondary"
          icon="schedule"
          hint="Scheduled handlers"
        />
        <MetricCard
          label="Pending Queue"
          value={formatNumber(metrics?.pending_queue ?? 0)}
          tone="tertiary"
          icon="queue"
          hint="Future intentions"
        />
        <MetricCard
          label="Success Rate"
          value={formatPercent(metrics?.success_rate ?? 0, 1)}
          tone={
            (metrics?.success_rate ?? 100) >= 95
              ? "tertiary"
              : (metrics?.success_rate ?? 0) >= 85
                ? "secondary"
                : "danger"
          }
          icon="task_alt"
          hint={`${formatNumber(metrics?.total_tasks ?? 0)} tasks total`}
        />
        <MetricCard
          label="Tokens 24h"
          value={formatNumber(metrics?.token_throughput ?? 0)}
          tone="primary"
          icon="bolt"
          hint="Throughput last 24h"
        />
      </div>

      {/* 3-column grid */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Subsystem matrix */}
        <section className="md:col-span-4 lg:col-span-3 space-y-6">
          <Panel title="Subsystem Matrix" icon="analytics">
            {subsystemChecks.length === 0 ? (
              <EmptyState icon="hourglass_top" title="Doctor reporting..." />
            ) : (
              <div className="space-y-3">
                {subsystemChecks.map((c) => (
                  <div
                    key={c.name}
                    className="flex items-center justify-between p-3 bg-bg-raised rounded"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="material-symbols-outlined text-primary"
                        style={{ fontSize: "16px" }}
                      >
                        {checkIcon(c.name)}
                      </span>
                      <span className="text-xs font-display">{c.name.replace(/_/g, " ")}</span>
                    </div>
                    <StatusIndicator status={STATUS_TONE[c.status]} pulse={false} />
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Resource Allocation" icon="speed">
            <div className="space-y-4">
              <ProgressBar
                label="Memory Density"
                hint={`${formatNumber(metrics?.total_entities ?? 0)} entities`}
                value={Math.min(100, ((metrics?.total_entities ?? 0) / 200) * 100)}
                tone="primary"
              />
              <ProgressBar
                label="Notes Indexed"
                hint={`${formatNumber(metrics?.total_notes ?? 0)} notes`}
                value={Math.min(100, ((metrics?.total_notes ?? 0) / 100) * 100)}
                tone="tertiary"
              />
              <ProgressBar
                label="Conversation Volume"
                hint={`${formatNumber(metrics?.total_messages ?? 0)} msgs`}
                value={Math.min(100, ((metrics?.total_messages ?? 0) / 1000) * 100)}
                tone="secondary"
              />
              <div className="border-t border-border pt-3">
                <p className="label-mono mb-1">Last Dream Cycle</p>
                <p className="text-xs text-ink-dim">
                  {metrics?.last_dream_at
                    ? `${formatRelative(metrics.last_dream_at)} · ${formatDateTime(metrics.last_dream_at)}`
                    : "No consolidation runs recorded yet"}
                </p>
              </div>
            </div>
          </Panel>
        </section>

        {/* Real-time state stream */}
        <section className="md:col-span-8 lg:col-span-6">
          <Panel
            title="Real Time State Stream"
            icon="terminal"
            bodyClassName="p-0"
            className="h-full flex flex-col"
            actions={
              <span className="text-[10px] font-display text-tertiary bg-tertiary/10 px-2 py-0.5 rounded">
                LIVE_FEED
              </span>
            }
          >
            <div className="flex-1 bg-bg-lowest p-4 font-mono text-sm space-y-2 overflow-y-auto max-h-[600px] scroll-thin">
              {feedItems.length === 0 ? (
                <EmptyState
                  icon="radar"
                  title="No recent activity"
                  description="Tasks will stream in as the agent processes requests."
                />
              ) : (
                feedItems.map((item) => (
                  <LogEntry
                    key={item.id}
                    timestamp={item.ts}
                    tag={item.tag}
                    message={item.message}
                    tone={item.tone}
                  />
                ))
              )}
            </div>
            <div className="p-3 border-t border-border bg-bg-raised/50 flex items-center gap-3">
              <span className="text-primary font-bold font-display text-xs uppercase">
                CMD &gt;
              </span>
              <input
                className="bg-transparent border-none focus:ring-0 text-xs w-full text-primary placeholder-primary/30 font-display"
                placeholder="Awaiting direct operator override..."
                type="text"
                readOnly
              />
            </div>
          </Panel>
        </section>

        {/* Right column */}
        <section className="md:col-span-12 lg:col-span-3 space-y-6">
          {/* Core Metrics */}
          <Panel title="Core Metrics" icon="analytics" bodyClassName="p-0">
            <div className="divide-y divide-border">
              <div className="p-4">
                <p className="text-[10px] font-display text-ink-mute uppercase mb-1">
                  Token Throughput
                </p>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-display font-bold">
                    {formatNumber(metrics?.token_throughput ?? 0)}
                  </span>
                  <span className="text-[10px] text-tertiary">/24h</span>
                </div>
              </div>
              <div className="p-4">
                <p className="text-[10px] font-display text-ink-mute uppercase mb-1">
                  Success Rate
                </p>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-display font-bold">
                    {formatPercent(metrics?.success_rate ?? 0, 1)}
                  </span>
                </div>
              </div>
              <div className="p-4">
                <p className="text-[10px] font-display text-ink-mute uppercase mb-1">
                  Total Tasks
                </p>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-display font-bold">
                    {formatNumber(metrics?.total_tasks ?? 0)}
                  </span>
                </div>
              </div>
            </div>
          </Panel>

          <ActiveSessionsCard sessions={sessions} />
        </section>
      </div>
    </div>
  );
}

function ActiveSessionsCard({
  sessions,
}: {
  sessions: PaginatedResponse<Session> | null;
}) {
  return (
    <Panel
      title="Active Session Map"
      icon="forum"
      actions={
        <Link to="/chat" className="btn text-[10px]">
          View All Active
        </Link>
      }
    >
      {!sessions || sessions.results.length === 0 ? (
        <EmptyState
          icon="hub"
          title="No live sessions"
          description="Active conversations will appear here."
        />
      ) : (
        <div className="space-y-3">
          {sessions.results.map((s) => (
            <div
              key={s.id}
              className="flex items-center gap-3 p-2 hover:bg-bg-raised rounded transition-colors"
            >
              <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center text-primary">
                <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                  person
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-display truncate">{s.source}</p>
                <p className="text-[10px] text-ink-mute">
                  {s.summary || "In progress..."}
                </p>
              </div>
              <span className="w-1.5 h-1.5 bg-tertiary rounded-full" />
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
