import { useCallback, useState } from "react";

import { cronJobsApi, futureQueueApi, systemApi } from "@/api/endpoints";
import { useApi } from "@/hooks/useApi";
import { Panel } from "@/components/shared/Panel";
import { MetricCard } from "@/components/shared/MetricCard";
import { StatusIndicator } from "@/components/shared/StatusIndicator";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/cn";
import {
  formatDateTime,
  formatNumber,
  formatRelative,
  truncate,
} from "@/lib/format";
import type {
  CronJob,
  CronJobStatus,
  CronRun,
  FutureQueueItem,
  PaginatedResponse,
  UUID,
} from "@/types/api";

const STATUS_LABEL: Record<CronJobStatus, string> = {
  active: "READY",
  paused: "PAUSED",
  disabled: "DISABLED",
};

export default function Tasks() {
  const { data: metrics } = useApi(() => systemApi.metrics(), [], { pollMs: 15_000 });
  const { data: jobs, reload: reloadJobs } = useApi(() => cronJobsApi.list({ limit: 50 }), [], { pollMs: 20_000 });
  const { data: queue, reload: reloadQueue } = useApi(() => futureQueueApi.list({ limit: 50 }), [], { pollMs: 20_000 });

  const [actionError, setActionError] = useState<string | null>(null);
  const [actionInflight, setActionInflight] = useState<string | null>(null);

  const handleAction = useCallback(async (key: string, fn: () => Promise<unknown>) => {
    setActionInflight(key);
    setActionError(null);
    try {
      await fn();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "action failed");
    } finally {
      setActionInflight(null);
    }
  }, []);

  return (
    <div className="p-6 max-w-[1600px] mx-auto">
      <PageHeader title="SURAJCLAW | Tasks & Automation" subtitle="Manage cron schedules, queue depth, and operational execution integrity." icon="assignment"
        actions={
          <div className="flex gap-3">
            <button type="button" className="btn">
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>refresh</span>
              Refresh System
            </button>
            <button type="button" className="btn-solid">
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>add</span>
              New Job
            </button>
          </div>
        }
      />

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <MetricCard label="Active Jobs" value={formatNumber(metrics?.active_jobs ?? 0)} icon="speed" tone="primary" hint="Operational Status: Nominal" />
        <MetricCard label="Pending Queue" value={formatNumber(metrics?.pending_queue ?? 0)} icon="hourglass_empty" tone="secondary" hint="Estimated processing: 1.2s" />
        <MetricCard label="Success Rate" value={`${(metrics?.success_rate ?? 0).toFixed(1)}%`} icon="check_circle" tone="tertiary" hint="Last 24 hours" />
        <MetricCard label="Total Executions" value={formatNumber(metrics?.total_tasks ?? 0)} icon="terminal" tone="neutral" hint="Current session total" />
      </div>

      {actionError && (
        <div className="text-xs text-danger border border-danger/30 bg-danger/10 px-3 py-2 rounded mb-4">{actionError}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left column: CronJobs + Queue */}
        <div className="lg:col-span-2 space-y-8">
          {/* Cron jobs */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <span className="material-symbols-outlined text-primary text-lg">event_repeat</span>
              <h2 className="text-lg font-display font-semibold tracking-tight uppercase">Scheduled CronJobs</h2>
            </div>
            {!jobs || jobs.results.length === 0 ? (
              <EmptyState icon="schedule_send" title="No cron jobs configured" description="Add CronJob rows via the Django admin." />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {jobs.results.map((job) => (
                  <CronJobCard key={job.id} job={job} inflight={actionInflight}
                    onTrigger={() => handleAction(`trigger:${job.id}`, async () => { await cronJobsApi.trigger(job.id); await reloadJobs(); })}
                    onPause={() => handleAction(`pause:${job.id}`, async () => { await cronJobsApi.pause(job.id); await reloadJobs(); })}
                    onResume={() => handleAction(`resume:${job.id}`, async () => { await cronJobsApi.resume(job.id); await reloadJobs(); })}
                  />
                ))}
              </div>
            )}
          </section>

          {/* Future queue */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <span className="material-symbols-outlined text-secondary text-lg">data_usage</span>
              <h2 className="text-lg font-display font-semibold tracking-tight uppercase">Future Queue</h2>
            </div>
            <Panel bodyClassName="p-0">
              {!queue || queue.results.length === 0 ? (
                <EmptyState icon="hourglass_top" title="Queue empty" />
              ) : (
                <FutureQueueTable items={queue.results} inflight={actionInflight}
                  onCancel={(id) => handleAction(`cancel:${id}`, async () => { await futureQueueApi.cancel(id); await reloadQueue(); })}
                />
              )}
            </Panel>
          </section>
        </div>

        {/* Right column: Run logs + Controls */}
        <div className="space-y-8">
          <RecentRunsPanel jobs={jobs} />

          <Panel title="Manual Controls" icon="tune">
            <div className="space-y-2">
              {[
                { icon: "play_arrow", label: "REBOOT_ALL_WORKERS", color: "text-primary" },
                { icon: "cleaning_services", label: "CLEAR_STUCK_QUEUES", color: "text-secondary" },
                { icon: "history", label: "WIPE_RUN_LOGS", color: "text-danger" },
              ].map((ctrl) => (
                <button key={ctrl.label} type="button"
                  className="w-full flex items-center justify-between p-3 bg-bg-raised rounded hover:bg-bg-overlay transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <span className={cn("material-symbols-outlined", ctrl.color)}>{ctrl.icon}</span>
                    <span className="font-display text-xs">{ctrl.label}</span>
                  </div>
                  <span className="material-symbols-outlined text-ink-mute group-hover:text-primary text-sm">chevron_right</span>
                </button>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function CronJobCard({ job, inflight, onTrigger, onPause, onResume }: {
  job: CronJob; inflight: string | null;
  onTrigger: () => void; onPause: () => void; onResume: () => void;
}) {
  const isPaused = job.status === "paused";
  const isDisabled = job.status === "disabled";
  const isFailed = job.last_run_status === "error" || job.last_run_status === "timeout";

  return (
    <div className="panel p-5 hover:border-primary/30 transition-all duration-300">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="font-display text-sm text-primary font-bold">{job.name}</h3>
          <p className="text-[10px] text-ink-mute font-display tracking-wider">{job.schedule_kind}: {job.schedule_value}</p>
        </div>
        <span className={cn("px-2 py-0.5 text-[10px] font-display rounded-full border",
          job.status === "active" ? "bg-tertiary/10 text-tertiary border-tertiary/20" :
          job.status === "paused" ? "bg-secondary/10 text-secondary border-secondary/20" :
          "bg-danger/10 text-danger border-danger/20"
        )}>{STATUS_LABEL[job.status]}</span>
      </div>
      <div className="space-y-2 mb-4">
        <Field label="Frequency" value={job.schedule_value} />
        <Field label="Next run" value={formatRelative(job.next_run_at)} />
        <Field label="Last run" value={job.last_run_at ? formatRelative(job.last_run_at) : "Never"} />
      </div>
      <div className="flex gap-2">
        {isFailed ? (
          <button type="button" onClick={onTrigger} disabled={inflight === `trigger:${job.id}`} className="btn-solid flex-1 justify-center">Retry Job</button>
        ) : (
          <button type="button" onClick={onTrigger} disabled={inflight === `trigger:${job.id}` || isDisabled} className="btn flex-1 justify-center">Manual Trigger</button>
        )}
        {isPaused ? (
          <button type="button" onClick={onResume} disabled={inflight === `resume:${job.id}`} className="btn">Resume</button>
        ) : (
          <button type="button" onClick={onPause} disabled={inflight === `pause:${job.id}` || isDisabled} className="btn-danger">
            <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>stop</span>
          </button>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-[11px]">
      <span className="text-ink-mute">{label}:</span>
      <span className="text-ink">{value}</span>
    </div>
  );
}

function FutureQueueTable({ items, inflight, onCancel }: {
  items: FutureQueueItem[]; inflight: string | null; onCancel: (id: UUID) => void;
}) {
  return (
    <div className="overflow-x-auto scroll-thin">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="bg-bg-raised text-[10px] font-display text-ink-mute uppercase tracking-[0.1em]">
            <th className="px-6 py-4 font-normal">Job_ID</th>
            <th className="px-6 py-4 font-normal">Process_Name</th>
            <th className="px-6 py-4 font-normal">Estimated_Start</th>
            <th className="px-6 py-4 font-normal">Priority</th>
            <th className="px-6 py-4 font-normal text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((item) => (
            <tr key={item.id} className="hover:bg-bg-raised transition-colors">
              <td className="px-6 py-4 font-mono text-[11px] text-ink-dim">{item.id.slice(0, 8)}</td>
              <td className="px-6 py-4 font-display text-xs text-primary font-bold">{truncate(item.intent, 30)}</td>
              <td className="px-6 py-4 font-display text-[11px]">{formatRelative(item.due_at)}</td>
              <td className="px-6 py-4">
                <StatusIndicator
                  status={item.status === "pending" ? "warn" : item.status === "fired" ? "ok" : "idle"}
                  label={item.status.toUpperCase()} pulse={false}
                />
              </td>
              <td className="px-6 py-4 text-right">
                {item.status === "pending" ? (
                  <button type="button" onClick={() => onCancel(item.id)} disabled={inflight === `cancel:${item.id}`} className="btn-danger">
                    <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>delete</span>
                  </button>
                ) : <span className="text-ink-mute font-mono text-[10px]">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecentRunsPanel({ jobs }: { jobs: PaginatedResponse<CronJob> | null }) {
  const jobId = jobs?.results?.[0]?.id ?? null;
  const { data: runs } = useApi(
    () => (jobId ? cronJobsApi.runs(jobId, 20) : Promise.resolve(null)),
    [jobId],
    { pollMs: 20_000 },
  );
  const list: CronRun[] = Array.isArray(runs)
    ? (runs as CronRun[])
    : runs && "results" in runs
      ? (runs as PaginatedResponse<CronRun>).results
      : [];
  const jobName = jobs?.results?.[0]?.name ?? "—";

  return (
    <Panel title="CronRun Logs" subtitle={jobId ? `Job: ${jobName}` : "Select a job"} icon="list_alt" bodyClassName="p-0"
      className="h-[500px] flex flex-col"
    >
      {list.length === 0 ? (
        <EmptyState icon="history_toggle_off" title="No run history" description="Run history will appear after the next firing." />
      ) : (
        <div className="flex-1 overflow-y-auto scroll-thin space-y-3 p-4">
          {list.map((run) => (
            <div key={run.id} className={cn("p-3 bg-bg-surface rounded-sm border-l",
              run.status === "ok" ? "border-l-tertiary/40" : "border-l-danger/40"
            )}>
              <div className="flex justify-between mb-1">
                <span className={cn("font-display text-xs", run.status === "ok" ? "text-tertiary" : "text-danger")}>
                  {run.status === "ok" ? "SUCCESS" : "FAILURE"}
                </span>
                <span className="text-[10px] text-ink-mute">{formatDateTime(run.started_at)}</span>
              </div>
              <p className="text-xs text-ink-dim">{run.summary || run.error_text || "(no summary)"}</p>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
