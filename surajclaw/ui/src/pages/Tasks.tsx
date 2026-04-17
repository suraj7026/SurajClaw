import { useCallback, useState } from "react";

import { cronJobsApi, futureQueueApi, systemApi } from "@/api/endpoints";
import { useApi } from "@/hooks/useApi";
import { Panel } from "@/components/shared/Panel";
import { MetricCard } from "@/components/shared/MetricCard";
import { StatusIndicator } from "@/components/shared/StatusIndicator";
import { LogEntry } from "@/components/shared/LogEntry";
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

const STATUS_TONE: Record<CronJobStatus, "ok" | "warn" | "error"> = {
  active: "ok",
  paused: "warn",
  disabled: "error",
};

export default function Tasks() {
  const { data: metrics } = useApi(() => systemApi.metrics(), [], {
    pollMs: 15_000,
  });
  const { data: jobs, reload: reloadJobs } = useApi(
    () => cronJobsApi.list({ limit: 50 }),
    [],
    { pollMs: 20_000 },
  );
  const { data: queue, reload: reloadQueue } = useApi(
    () => futureQueueApi.list({ limit: 50 }),
    [],
    { pollMs: 20_000 },
  );

  const [actionError, setActionError] = useState<string | null>(null);
  const [actionInflight, setActionInflight] = useState<string | null>(null);

  const handleAction = useCallback(
    async (key: string, fn: () => Promise<unknown>) => {
      setActionInflight(key);
      setActionError(null);
      try {
        await fn();
      } catch (err) {
        setActionError(
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "action failed",
        );
      } finally {
        setActionInflight(null);
      }
    },
    [],
  );

  return (
    <div className="p-4 sm:p-6 max-w-[1600px] mx-auto">
      <PageHeader
        title="Task & Automation Manager"
        subtitle="CronJobs · FutureQueue · run history"
        icon="schedule"
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <MetricCard
          label="Active Jobs"
          value={formatNumber(metrics?.active_jobs ?? 0)}
          icon="schedule"
          tone="primary"
        />
        <MetricCard
          label="Pending Queue"
          value={formatNumber(metrics?.pending_queue ?? 0)}
          icon="queue"
          tone="secondary"
        />
        <MetricCard
          label="Total Tasks"
          value={formatNumber(metrics?.total_tasks ?? 0)}
          icon="task_alt"
          tone="tertiary"
        />
        <MetricCard
          label="Success Rate"
          value={`${(metrics?.success_rate ?? 0).toFixed(1)}%`}
          icon="trending_up"
          tone={(metrics?.success_rate ?? 100) >= 95 ? "tertiary" : "secondary"}
        />
      </div>

      {actionError && (
        <div className="text-xs text-danger border border-danger/30 bg-danger/10 px-3 py-2 rounded mb-4">
          {actionError}
        </div>
      )}

      {/* Cron jobs */}
      <Panel title="Cron Jobs" icon="event_repeat" className="mb-4">
        {!jobs || jobs.results.length === 0 ? (
          <EmptyState
            icon="schedule_send"
            title="No cron jobs configured"
            description="Add CronJob rows via the Django admin."
          />
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {jobs.results.map((job) => (
              <CronJobCard
                key={job.id}
                job={job}
                inflight={actionInflight}
                onTrigger={() =>
                  handleAction(`trigger:${job.id}`, async () => {
                    await cronJobsApi.trigger(job.id);
                    await reloadJobs();
                  })
                }
                onPause={() =>
                  handleAction(`pause:${job.id}`, async () => {
                    await cronJobsApi.pause(job.id);
                    await reloadJobs();
                  })
                }
                onResume={() =>
                  handleAction(`resume:${job.id}`, async () => {
                    await cronJobsApi.resume(job.id);
                    await reloadJobs();
                  })
                }
              />
            ))}
          </ul>
        )}
      </Panel>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Future queue */}
        <Panel title="Future Queue" icon="queue" bodyClassName="p-0">
          {!queue || queue.results.length === 0 ? (
            <EmptyState icon="hourglass_top" title="Queue empty" />
          ) : (
            <FutureQueueTable
              items={queue.results}
              inflight={actionInflight}
              onCancel={(id) =>
                handleAction(`cancel:${id}`, async () => {
                  await futureQueueApi.cancel(id);
                  await reloadQueue();
                })
              }
            />
          )}
        </Panel>

        {/* Recent runs */}
        <RecentRunsPanel jobs={jobs} />
      </div>
    </div>
  );
}

interface CronJobCardProps {
  job: CronJob;
  inflight: string | null;
  onTrigger: () => Promise<void> | void;
  onPause: () => Promise<void> | void;
  onResume: () => Promise<void> | void;
}

function CronJobCard({
  job,
  inflight,
  onTrigger,
  onPause,
  onResume,
}: CronJobCardProps) {
  const isPaused = job.status === "paused";
  const isDisabled = job.status === "disabled";

  return (
    <li className="border border-border rounded-lg bg-bg-base/40 overflow-hidden">
      <header className="px-3 py-2 flex items-center justify-between border-b border-border">
        <div className="flex items-center gap-2 min-w-0">
          <StatusIndicator status={STATUS_TONE[job.status]} />
          <span className="font-display text-sm uppercase tracking-wider truncate">
            {job.name}
          </span>
        </div>
        <span className="label-mono">{job.schedule_kind}</span>
      </header>
      <div className="px-3 py-3 space-y-2">
        {job.description && (
          <p className="text-xs text-ink-dim line-clamp-2">{job.description}</p>
        )}
        <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
          <Field label="Schedule" value={job.schedule_value} />
          <Field label="Timezone" value={job.timezone} />
          <Field label="Next run" value={formatRelative(job.next_run_at)} />
          <Field label="Last run" value={formatRelative(job.last_run_at)} />
          <Field label="Failures" value={String(job.consecutive_failures)} />
          <Field label="Delivery" value={job.delivery_mode} />
        </div>
      </div>
      <footer className="px-3 py-2 border-t border-border flex items-center justify-between gap-2">
        <span className="text-[10px] text-ink-mute font-mono">
          {job.last_run_status || "—"}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onTrigger}
            disabled={inflight === `trigger:${job.id}` || isDisabled}
            className="btn-primary"
            title="Trigger now"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>
              play_arrow
            </span>
            Trigger
          </button>
          {isPaused ? (
            <button
              type="button"
              onClick={onResume}
              disabled={inflight === `resume:${job.id}`}
              className="btn"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>
                play_circle
              </span>
              Resume
            </button>
          ) : (
            <button
              type="button"
              onClick={onPause}
              disabled={inflight === `pause:${job.id}` || isDisabled}
              className="btn"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>
                pause
              </span>
              Pause
            </button>
          )}
        </div>
      </footer>
    </li>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="label-mono">{label}</p>
      <p className="text-ink-dim truncate">{value}</p>
    </div>
  );
}

function FutureQueueTable({
  items,
  inflight,
  onCancel,
}: {
  items: FutureQueueItem[];
  inflight: string | null;
  onCancel: (id: UUID) => void;
}) {
  return (
    <div className="overflow-x-auto scroll-thin">
      <table className="w-full text-xs">
        <thead className="bg-bg-raised/40 border-b border-border">
          <tr className="text-left">
            <th className="px-3 py-2 label-mono">Intent</th>
            <th className="px-3 py-2 label-mono">Trigger</th>
            <th className="px-3 py-2 label-mono">Due</th>
            <th className="px-3 py-2 label-mono">Status</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((item) => (
            <tr key={item.id} className="hover:bg-bg-raised/40">
              <td className="px-3 py-2 max-w-[280px]">
                <p className="text-ink truncate">{truncate(item.intent, 80)}</p>
                <p className="text-[10px] text-ink-mute font-mono">
                  {formatRelative(item.created_at)}
                </p>
              </td>
              <td className="px-3 py-2 label-mono text-primary">
                {item.trigger_type}
              </td>
              <td className="px-3 py-2 font-mono text-ink-dim">
                {formatDateTime(item.due_at)}
              </td>
              <td className="px-3 py-2">
                <StatusIndicator
                  status={
                    item.status === "pending"
                      ? "warn"
                      : item.status === "fired"
                        ? "ok"
                        : "idle"
                  }
                  label={item.status.toUpperCase()}
                  pulse={false}
                />
              </td>
              <td className="px-3 py-2 text-right">
                {item.status === "pending" ? (
                  <button
                    type="button"
                    onClick={() => onCancel(item.id)}
                    disabled={inflight === `cancel:${item.id}`}
                    className="btn-danger"
                  >
                    <span
                      className="material-symbols-outlined"
                      style={{ fontSize: "14px" }}
                    >
                      cancel
                    </span>
                    Cancel
                  </button>
                ) : (
                  <span className="text-ink-mute font-mono text-[10px]">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecentRunsPanel({
  jobs,
}: {
  jobs: PaginatedResponse<CronJob> | null;
}) {
  // Pull runs for the first job so the panel still shows something useful
  // without a "select-a-job" UX. A future enhancement is a job picker.
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
    <Panel
      title="Recent Run Log"
      subtitle={jobId ? `Job: ${jobName}` : "Select a job"}
      icon="history"
      bodyClassName="p-0"
    >
      {list.length === 0 ? (
        <EmptyState
          icon="history_toggle_off"
          title="No run history"
          description="Run history will appear after the next firing."
        />
      ) : (
        <ul className="divide-y divide-border max-h-[420px] overflow-y-auto scroll-thin">
          {list.map((run) => (
            <li key={run.id} className="px-4 py-2.5 hover:bg-bg-raised/40">
              <LogEntry
                timestamp={run.started_at}
                tag={`RUN·${run.status.toUpperCase()}`}
                tone={
                  run.status === "ok"
                    ? "ok"
                    : run.status === "error" || run.status === "timeout"
                      ? "error"
                      : "warn"
                }
                message={
                  <span>
                    {run.summary || run.error_text || "(no summary)"}
                    <span className={cn("ml-2 label-mono")}>
                      {run.duration_ms
                        ? `${run.duration_ms}ms`
                        : run.delivery_status || ""}
                    </span>
                  </span>
                }
              />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
