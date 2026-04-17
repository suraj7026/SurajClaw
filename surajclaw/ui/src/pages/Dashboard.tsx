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
  ok: "NOMINAL",
  warn: "DEGRADED",
  error: "CRITICAL",
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
  if (name.includes("ollama")) return "smart_toy";
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
    <div className="p-4 sm:p-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="Mission Control"
        subtitle="Real-time operator overview of every SurajClaw subsystem."
        icon="dashboard"
        actions={
          <div className="flex items-center gap-3">
            <StatusIndicator
              status={doctor ? STATUS_TONE[doctor.status] : "idle"}
              label={
                doctor ? `STATUS · ${STATUS_LABEL[doctor.status]}` : "AWAITING DOCTOR"
              }
            />
            <span className="font-mono text-xs text-ink-mute hidden sm:inline">
              {now.toISOString().slice(11, 19)} UTC
            </span>
          </div>
        }
      />

      {/* Health banner */}
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
          label="Tokens · 24h"
          value={formatNumber(metrics?.token_throughput ?? 0)}
          tone="primary"
          icon="bolt"
          hint="Throughput last 24h"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Subsystem matrix */}
        <Panel
          title="Subsystem Matrix"
          subtitle="Self-check probes from /api/doctor"
          icon="grid_view"
          className="lg:col-span-2"
        >
          {subsystemChecks.length === 0 ? (
            <EmptyState icon="hourglass_top" title="Doctor reporting…" />
          ) : (
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {subsystemChecks.map((c) => (
                <li
                  key={c.name}
                  className="border border-border rounded-md p-3 bg-bg-base/40 hover:border-primary/40 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className="material-symbols-outlined text-primary"
                        style={{ fontSize: "16px" }}
                      >
                        {checkIcon(c.name)}
                      </span>
                      <span className="font-display text-xs uppercase tracking-wider truncate">
                        {c.name.replace(/_/g, " ")}
                      </span>
                    </div>
                    <StatusIndicator status={STATUS_TONE[c.status]} pulse={false} />
                  </div>
                  <p className="text-[11px] text-ink-dim font-mono leading-relaxed line-clamp-2">
                    {c.detail || "—"}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* Resource HUD */}
        <Panel title="Resource HUD" icon="speed">
          <div className="space-y-4">
            <ProgressBar
              label="Memory Density"
              hint={`${formatNumber(metrics?.total_entities ?? 0)} entities`}
              value={Math.min(
                100,
                ((metrics?.total_entities ?? 0) / 200) * 100,
              )}
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
              hint={`${formatNumber(metrics?.total_messages ?? 0)} messages`}
              value={Math.min(
                100,
                ((metrics?.total_messages ?? 0) / 1000) * 100,
              )}
              tone="secondary"
            />
            <div className="border-t border-border pt-3">
              <p className="label-mono mb-1">Last Dream Cycle</p>
              <p className="text-xs text-ink-dim">
                {metrics?.last_dream_at
                  ? `${formatRelative(metrics.last_dream_at)} · ${formatDateTime(
                      metrics.last_dream_at,
                    )}`
                  : "No consolidation runs recorded yet"}
              </p>
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
        {/* Real-time feed */}
        <Panel
          title="State Stream"
          subtitle="Recent agent activity"
          icon="bolt"
          className="lg:col-span-2"
          bodyClassName="p-0"
          actions={<StatusIndicator status="info" label="LIVE" />}
        >
          <div className="max-h-96 overflow-y-auto scroll-thin">
            {feedItems.length === 0 ? (
              <EmptyState
                icon="radar"
                title="No recent activity"
                description="Tasks will stream in as the agent processes requests."
              />
            ) : (
              <ul className="divide-y divide-border">
                {feedItems.map((item) => (
                  <li key={item.id} className="px-4 py-2 hover:bg-bg-raised/40">
                    <LogEntry
                      timestamp={item.ts}
                      tag={item.tag}
                      message={item.message}
                      tone={item.tone}
                    />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>

        {/* Active sessions */}
        <ActiveSessionsCard sessions={sessions} />
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
      title="Active Sessions"
      icon="forum"
      actions={
        <Link to="/chat" className="btn">
          <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>
            chat
          </span>
          New
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
        <ul className="space-y-2">
          {sessions.results.map((s) => (
            <li
              key={s.id}
              className="border border-border rounded-md p-3 bg-bg-base/40"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="label-mono text-primary">{s.source}</span>
                <span className="text-[10px] text-ink-mute font-mono">
                  {formatRelative(s.started_at)}
                </span>
              </div>
              <p className="text-xs text-ink-dim line-clamp-2">
                {s.summary || "No summary yet — conversation in progress."}
              </p>
              {s.message_count !== undefined && (
                <p className="text-[10px] text-ink-mute mt-1 font-mono">
                  {s.message_count} messages
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
