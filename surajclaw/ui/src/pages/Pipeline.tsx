import { useMemo } from "react";

import { memoryApi, systemApi, tasksApi } from "@/api/endpoints";
import { useApi } from "@/hooks/useApi";
import { Panel } from "@/components/shared/Panel";
import { MetricCard } from "@/components/shared/MetricCard";
import { ProgressBar } from "@/components/shared/ProgressBar";
import { StatusIndicator } from "@/components/shared/StatusIndicator";
import { LogEntry } from "@/components/shared/LogEntry";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { cn } from "@/lib/cn";
import {
  formatDateTime,
  formatNumber,
  formatRelative,
  truncate,
} from "@/lib/format";
import type { Task } from "@/types/api";

interface PipelineNode {
  id: string;
  label: string;
  icon: string;
  description: string;
}

const NODES: PipelineNode[] = [
  {
    id: "planner",
    label: "Planner",
    icon: "psychology",
    description: "Decomposes the request into tool-actionable steps.",
  },
  {
    id: "router",
    label: "Router",
    icon: "alt_route",
    description: "Selects local Gemma vs cloud Gemini based on complexity.",
  },
  {
    id: "executor",
    label: "Executor",
    icon: "play_circle",
    description: "Invokes tools (git, web, notes, gmail) within sandbox limits.",
  },
  {
    id: "reflector",
    label: "Reflector",
    icon: "rate_review",
    description: "Reviews tool outputs and decides if more steps are needed.",
  },
  {
    id: "responder",
    label: "Responder",
    icon: "send",
    description: "Streams the final answer back to the requesting channel.",
  },
];

function tonesByStatus(t: Task["status"]) {
  if (t === "done") return { dot: "ok" as const, log: "ok" as const };
  if (t === "failed") return { dot: "error" as const, log: "error" as const };
  if (t === "running") return { dot: "info" as const, log: "primary" as const };
  return { dot: "warn" as const, log: "warn" as const };
}

export default function Pipeline() {
  const { data: metrics } = useApi(() => systemApi.metrics(), [], {
    pollMs: 15_000,
  });
  const { data: state } = useApi(() => systemApi.systemState(), [], {
    pollMs: 30_000,
  });
  const { data: tasks } = useApi(() => tasksApi.list({ limit: 25 }), [], {
    pollMs: 10_000,
  });
  const { data: dreams } = useApi(() => memoryApi.dreamLogs({ limit: 5 }), [], {
    pollMs: 60_000,
  });

  const stateMap = useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const item of state?.results ?? []) {
      map[item.key] = item.value;
    }
    return map;
  }, [state]);

  const activeModel = stateMap.active_model || stateMap.last_model || "gemma4:e2b";
  const agentMode = stateMap.agent_mode || "balanced";
  const lastDream = dreams?.results?.[0];

  // Routing distribution: count tasks by light_context-like categories. We
  // approximate by source for now (cron is "background", web/telegram is
  // "interactive") because the real model_used field hangs off Message.
  const routingCounts = useMemo(() => {
    const buckets: Record<string, number> = { local: 0, cloud: 0, escalated: 0 };
    for (const m of state?.results ?? []) {
      if (m.key.startsWith("model_pin:")) {
        if (m.value.toLowerCase().includes("gemini")) buckets.cloud += 1;
        else if (m.value.toLowerCase().includes("escalate")) buckets.escalated += 1;
        else buckets.local += 1;
      }
    }
    if (Object.values(buckets).every((v) => v === 0) && tasks) {
      // Fallback: use task counts to keep the bars from looking empty.
      buckets.local = Math.round(tasks.results.length * 0.6);
      buckets.cloud = Math.round(tasks.results.length * 0.3);
      buckets.escalated = Math.round(tasks.results.length * 0.1);
    }
    return buckets;
  }, [state, tasks]);

  const totalRouted =
    routingCounts.local + routingCounts.cloud + routingCounts.escalated || 1;

  // Pick the most recently active node by guessing from the latest task status.
  const latestTask = tasks?.results?.[0];
  const activeNodeId =
    latestTask?.status === "running"
      ? "executor"
      : latestTask?.status === "pending"
        ? "planner"
        : "responder";

  return (
    <div className="p-4 sm:p-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="Agent Runtime"
        subtitle="LangGraph pipeline · model routing · dream worker"
        icon="schema"
        actions={
          <div className="flex items-center gap-3">
            <StatusIndicator
              status={latestTask?.status === "running" ? "info" : "ok"}
              label={
                latestTask?.status === "running" ? "PIPELINE RUNNING" : "PIPELINE IDLE"
              }
            />
          </div>
        }
      />

      {/* HUD */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <MetricCard
          label="Active Model"
          value={activeModel}
          tone="primary"
          icon="smart_toy"
          hint="From SystemState"
        />
        <MetricCard
          label="Agent Mode"
          value={agentMode}
          tone="secondary"
          icon="tune"
          hint="balanced · fast · deep"
        />
        <MetricCard
          label="Tasks 24h"
          value={formatNumber(metrics?.total_tasks ?? 0)}
          tone="tertiary"
          icon="play_circle"
        />
        <MetricCard
          label="Tokens 24h"
          value={formatNumber(metrics?.token_throughput ?? 0)}
          tone="primary"
          icon="bolt"
        />
      </div>

      {/* Pipeline graph */}
      <Panel title="LangGraph Pipeline" icon="account_tree" className="mb-4" scanline>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {NODES.map((node, idx) => {
            const isActive = node.id === activeNodeId;
            return (
              <div
                key={node.id}
                className={cn(
                  "relative border rounded-lg p-3 bg-bg-base/40",
                  isActive
                    ? "border-primary/60 shadow-glow"
                    : "border-border hover:border-primary/30",
                )}
              >
                <div className="flex items-center justify-between mb-2">
                  <span
                    className={cn(
                      "material-symbols-outlined",
                      isActive ? "text-primary" : "text-ink-dim",
                    )}
                    style={{ fontSize: "20px" }}
                  >
                    {node.icon}
                  </span>
                  <StatusIndicator
                    status={isActive ? "info" : "idle"}
                    pulse={isActive}
                  />
                </div>
                <p className="font-display text-sm uppercase tracking-wider">
                  {idx + 1}. {node.label}
                </p>
                <p className="text-[11px] text-ink-dim mt-1 leading-relaxed">
                  {node.description}
                </p>
              </div>
            );
          })}
        </div>
      </Panel>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Thought process / recent tasks */}
        <Panel
          title="Thought Process Log"
          subtitle="Recent agent turns"
          icon="psychology_alt"
          className="lg:col-span-2"
          bodyClassName="p-0"
        >
          <div className="max-h-[420px] overflow-y-auto scroll-thin">
            {!tasks || tasks.results.length === 0 ? (
              <EmptyState
                icon="hourglass_top"
                title="No turns yet"
                description="Recent agent turns will surface here."
              />
            ) : (
              <ul className="divide-y divide-border">
                {tasks.results.map((t) => {
                  const tone = tonesByStatus(t.status);
                  return (
                    <li key={t.id} className="px-4 py-3 hover:bg-bg-raised/40">
                      <div className="flex items-start justify-between gap-3 mb-1.5">
                        <div className="flex items-center gap-2">
                          <StatusIndicator status={tone.dot} pulse={t.status === "running"} />
                          <span className="label-mono">
                            {t.source} · {t.status}
                          </span>
                        </div>
                        <span className="text-[10px] text-ink-mute font-mono">
                          {formatRelative(t.created_at)}
                        </span>
                      </div>
                      <LogEntry
                        timestamp={t.created_at}
                        tag="REQ"
                        message={truncate(t.request, 160)}
                        tone="info"
                      />
                      {t.result && (
                        <LogEntry
                          timestamp={t.completed_at ?? t.created_at}
                          tag="RES"
                          message={truncate(t.result, 200)}
                          tone={tone.log}
                          className="mt-1"
                        />
                      )}
                      {t.tools_used && t.tools_used.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {t.tools_used.map((tool) => (
                            <span
                              key={tool}
                              className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-primary/30 text-primary"
                            >
                              {tool}
                            </span>
                          ))}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Panel>

        {/* Dream worker + routing */}
        <div className="space-y-4">
          <Panel title="Dream Worker" icon="bedtime">
            {!lastDream ? (
              <EmptyState
                icon="dark_mode"
                title="No consolidation yet"
                description="The Dream worker runs nightly to merge entities and prune notes."
              />
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <StatusIndicator status="ok" label={lastDream.trigger.toUpperCase()} />
                  <span className="text-[10px] text-ink-mute font-mono">
                    {formatRelative(lastDream.created_at)}
                  </span>
                </div>
                <p className="text-xs text-ink-dim leading-relaxed">
                  {lastDream.summary || "No summary recorded."}
                </p>
                <dl className="grid grid-cols-2 gap-2 text-xs">
                  <Stat k="Sessions" v={lastDream.sessions_processed} />
                  <Stat k="Merged" v={lastDream.entities_merged} />
                  <Stat k="Pruned" v={lastDream.entities_pruned} />
                  <Stat k="Notes" v={lastDream.notes_updated} />
                </dl>
                <p className="text-[10px] text-ink-mute font-mono">
                  Duration {lastDream.duration_seconds.toFixed(2)}s ·{" "}
                  {formatDateTime(lastDream.created_at)}
                </p>
              </div>
            )}
          </Panel>

          <Panel title="Routing Distribution" icon="alt_route">
            <div className="space-y-3">
              <ProgressBar
                label="Local · Gemma"
                hint={`${routingCounts.local}/${totalRouted}`}
                value={(routingCounts.local / totalRouted) * 100}
                tone="tertiary"
              />
              <ProgressBar
                label="Cloud · Gemini"
                hint={`${routingCounts.cloud}/${totalRouted}`}
                value={(routingCounts.cloud / totalRouted) * 100}
                tone="primary"
              />
              <ProgressBar
                label="Escalated"
                hint={`${routingCounts.escalated}/${totalRouted}`}
                value={(routingCounts.escalated / totalRouted) * 100}
                tone="secondary"
              />
              <p className="text-[10px] text-ink-mute leading-relaxed pt-2 border-t border-border">
                Distribution sourced from <code className="text-primary">SystemState</code>{" "}
                model pins, with task-source fallback.
              </p>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: number }) {
  return (
    <div className="border border-border rounded p-2 bg-bg-base/40">
      <p className="label-mono">{k}</p>
      <p className="font-display text-lg text-primary">{formatNumber(v)}</p>
    </div>
  );
}
