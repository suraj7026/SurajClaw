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
  { id: "planner", label: "Planner", icon: "edit_note", description: "Decomposes intent into sub-steps." },
  { id: "router", label: "Router", icon: "alt_route", description: "Uses the configured Gemini model." },
  { id: "executor", label: "Executor", icon: "terminal", description: "Invokes tools within sandbox." },
  { id: "reflector", label: "Reflector", icon: "psychology", description: "Reviews outputs for next steps." },
  { id: "responder", label: "Responder", icon: "chat_bubble", description: "Streams final answer." },
];

function tonesByStatus(t: Task["status"]) {
  if (t === "done") return { dot: "ok" as const, log: "ok" as const };
  if (t === "failed") return { dot: "error" as const, log: "error" as const };
  if (t === "running") return { dot: "info" as const, log: "primary" as const };
  return { dot: "warn" as const, log: "warn" as const };
}

export default function Pipeline() {
  const { data: metrics } = useApi(() => systemApi.metrics(), [], { pollMs: 15_000 });
  const { data: state } = useApi(() => systemApi.systemState(), [], { pollMs: 30_000 });
  const { data: tasks } = useApi(() => tasksApi.list({ limit: 25 }), [], { pollMs: 10_000 });
  const { data: dreams } = useApi(() => memoryApi.dreamLogs({ limit: 5 }), [], { pollMs: 60_000 });

  const stateMap = useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const item of state?.results ?? []) map[item.key] = item.value;
    return map;
  }, [state]);

  const activeModel = stateMap.active_model || stateMap.last_model || "gemini-3.1-flash-lite-preview";
  const agentMode = stateMap.agent_mode || "balanced";
  const lastDream = dreams?.results?.[0];

  const routingCounts = useMemo(() => {
    const buckets: Record<string, number> = { cloud: 0, escalated: 0 };
    for (const m of state?.results ?? []) {
      if (m.key.startsWith("model_pin:")) {
        if (m.value.toLowerCase().includes("gemini")) buckets.cloud += 1;
        else if (m.value.toLowerCase().includes("escalate")) buckets.escalated += 1;
      }
    }
    if (Object.values(buckets).every((v) => v === 0) && tasks) {
      buckets.cloud = tasks.results.length;
    }
    return buckets;
  }, [state, tasks]);

  const totalRouted = routingCounts.cloud + routingCounts.escalated || 1;
  const latestTask = tasks?.results?.[0];
  const activeNodeId =
    latestTask?.status === "running"
      ? "executor"
      : latestTask?.status === "pending"
        ? "planner"
        : "responder";

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="LangGraph Execution"
        subtitle="Monitoring the linear propagation of logic across distributed agentic nodes."
        icon="account_tree"
        actions={
          <StatusIndicator
            status={latestTask?.status === "running" ? "info" : "ok"}
            label={latestTask?.status === "running" ? "PIPELINE RUNNING" : "PIPELINE IDLE"}
          />
        }
      />

      {/* Top HUD */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="panel p-4">
          <span className="text-[10px] font-display text-ink-mute uppercase tracking-widest">Active Model</span>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-primary font-display text-lg font-bold uppercase">{activeModel}</span>
            <span className="bg-primary/10 text-primary text-[10px] px-1.5 py-0.5 rounded border border-primary/20">
              ROUTED
            </span>
          </div>
        </div>
        <div className="panel p-4">
          <span className="text-[10px] font-display text-ink-mute uppercase tracking-widest">Agent Mode</span>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-secondary font-display text-lg font-bold uppercase">{agentMode}</span>
            <div className="w-2 h-2 rounded-full bg-secondary animate-pulse" />
          </div>
        </div>
        <MetricCard label="Tasks 24h" value={formatNumber(metrics?.total_tasks ?? 0)} tone="tertiary" icon="play_circle" />
        <MetricCard label="Tokens 24h" value={formatNumber(metrics?.token_throughput ?? 0)} tone="primary" icon="bolt" />
      </div>

      {/* Pipeline visualizer */}
      <div className="panel p-8 mb-6 relative overflow-hidden">
        <div className="absolute inset-0 dot-grid pointer-events-none" />
        <div className="flex justify-between items-center mb-8 relative z-10">
          <h2 className="font-display text-sm font-bold tracking-[0.2em] uppercase">LangGraph Execution</h2>
          <div className="flex gap-4">
            <span className="flex items-center gap-2 text-[10px] font-display text-ink-mute uppercase">
              <span className="w-2 h-2 rounded-full bg-primary-container" /> Processing
            </span>
            <span className="flex items-center gap-2 text-[10px] font-display text-ink-mute uppercase">
              <span className="w-2 h-2 rounded-full bg-bg-overlay" /> Idle
            </span>
          </div>
        </div>
        <div className="relative flex flex-col md:flex-row items-center justify-between gap-4 md:gap-0 py-8 z-10">
          {NODES.map((node, idx) => {
            const isActive = node.id === activeNodeId;
            return (
              <div key={node.id} className="contents">
                <div className="relative z-10">
                  <div
                    className={cn(
                      "w-36 p-4 flex flex-col items-center gap-2 rounded-lg transition-all",
                      isActive
                        ? "bg-primary-container shadow-glow-strong"
                        : "bg-bg-raised border-b-2 border-border opacity-70",
                    )}
                  >
                    <span
                      className={cn("material-symbols-outlined", isActive ? "text-bg-lowest" : "text-ink-dim")}
                      style={{ fontSize: "24px", fontVariationSettings: isActive ? "'FILL' 1" : undefined }}
                    >
                      {node.icon}
                    </span>
                    <span className={cn("font-display text-xs font-bold tracking-widest uppercase", isActive && "text-bg-lowest")}>
                      {node.label}
                    </span>
                    <span className={cn("text-[9px] font-display", isActive ? "text-bg-lowest/70" : "text-ink-mute")}>
                      {isActive ? "EXECUTING..." : "STANDBY"}
                    </span>
                    {isActive && (
                      <div className="absolute -top-1 -right-1 w-3 h-3 bg-primary-container rounded-full animate-ping opacity-75" />
                    )}
                  </div>
                </div>
                {idx < NODES.length - 1 && (
                  <div className="hidden md:block flex-1 h-px bg-border relative min-w-[24px]">
                    {isActive && (
                      <div className="absolute inset-0 bg-primary h-full w-[60%] shadow-glow" />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Thought process log */}
        <div className="lg:col-span-2">
          <Panel title="Thought Process Log" icon="data_object" bodyClassName="p-0" className="h-[400px] flex flex-col"
            actions={<span className="text-[10px] text-tertiary font-display">STREAMING ACTIVE</span>}
          >
            <div className="flex-1 overflow-y-auto scroll-thin bg-bg-lowest p-4 font-mono text-sm space-y-2">
              {!tasks || tasks.results.length === 0 ? (
                <EmptyState icon="hourglass_top" title="No turns yet" description="Recent agent turns will surface here." />
              ) : (
                tasks.results.slice(0, 10).map((t) => {
                  const tone = tonesByStatus(t.status);
                  return (
                    <div key={t.id}>
                      <LogEntry timestamp={t.created_at} tag={`${t.source}·${t.status}`} message={truncate(t.request, 160)} tone={tone.log} />
                      {t.result && (
                        <LogEntry timestamp={t.completed_at ?? t.created_at} tag="RES" message={truncate(t.result, 200)} tone={tone.log} className="ml-6 mt-1 opacity-70" />
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </Panel>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          <Panel title="Dream Worker" icon="cloud_done" glass
            actions={<span className="bg-secondary/10 text-secondary text-[10px] px-2 py-0.5 rounded uppercase font-bold">Background Sync</span>}
          >
            {!lastDream ? (
              <EmptyState icon="dark_mode" title="No consolidation yet" description="The Dream worker runs nightly to merge entities and prune notes." />
            ) : (
              <div className="space-y-4">
                <ProgressBar label="Async Reflection" hint={`${Math.min(100, Math.round((lastDream.sessions_processed / Math.max(1, lastDream.sessions_processed + 2)) * 100))}%`}
                  value={Math.min(100, Math.round((lastDream.sessions_processed / Math.max(1, lastDream.sessions_processed + 2)) * 100))} tone="secondary"
                />
                <div className="bg-bg-raised p-3 space-y-3">
                  <div className="flex items-center gap-3">
                    <span className="material-symbols-outlined text-sm text-secondary">history</span>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-tight">Recollecting {lastDream.sessions_processed} Sessions</p>
                      <p className="text-[9px] text-ink-mute">{lastDream.summary || "Optimizing weights..."}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="material-symbols-outlined text-sm text-tertiary">auto_fix_high</span>
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-tight">Self-Correction Loop</p>
                      <p className="text-[9px] text-ink-mute">Merged {lastDream.entities_merged}, pruned {lastDream.entities_pruned}</p>
                    </div>
                  </div>
                </div>
                <p className="text-[10px] text-ink-mute font-mono">
                  Duration {lastDream.duration_seconds.toFixed(2)}s · {formatDateTime(lastDream.created_at)}
                </p>
              </div>
            )}
          </Panel>

          <Panel title="Routing Distribution" icon="alt_route">
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-10 text-[10px] font-display text-primary">GEMINI</div>
                <div className="flex-1 h-2 bg-bg-overlay rounded-full overflow-hidden">
                  <div className="bg-primary h-full" style={{ width: `${(routingCounts.cloud / totalRouted) * 100}%` }} />
                </div>
                <div className="w-8 text-[10px] text-right font-display">{Math.round((routingCounts.cloud / totalRouted) * 100)}%</div>
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
