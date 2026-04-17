import { cn } from "@/lib/cn";

export type LogTone = "info" | "ok" | "warn" | "error" | "muted" | "primary";

interface Props {
  timestamp?: string | Date;
  tag?: string;
  message: React.ReactNode;
  tone?: LogTone;
  className?: string;
}

const TONES: Record<LogTone, string> = {
  info: "text-ink",
  ok: "text-tertiary",
  warn: "text-secondary",
  error: "text-danger",
  muted: "text-ink-dim",
  primary: "text-primary",
};

function formatStamp(ts?: string | Date): string {
  if (!ts) return "--:--:--";
  const d = typeof ts === "string" ? new Date(ts) : ts;
  if (Number.isNaN(d.getTime())) return "--:--:--";
  return d.toLocaleTimeString(undefined, {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function LogEntry({ timestamp, tag, message, tone = "info", className }: Props) {
  return (
    <div className={cn("font-mono text-[11px] leading-relaxed flex gap-3", className)}>
      <span className="text-ink-mute shrink-0">{formatStamp(timestamp)}</span>
      {tag && (
        <span className={cn("shrink-0 uppercase tracking-wider", TONES[tone])}>
          [{tag}]
        </span>
      )}
      <span className={cn("min-w-0 break-words", TONES[tone])}>{message}</span>
    </div>
  );
}
