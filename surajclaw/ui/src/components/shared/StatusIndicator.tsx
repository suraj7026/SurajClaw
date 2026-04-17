import { cn } from "@/lib/cn";

export type StatusKind = "ok" | "warn" | "error" | "idle" | "info";

interface Props {
  status: StatusKind;
  label?: string;
  className?: string;
  pulse?: boolean;
}

const COLORS: Record<StatusKind, string> = {
  ok: "bg-tertiary shadow-[0_0_8px_rgba(184,255,187,0.6)]",
  warn: "bg-secondary shadow-[0_0_8px_rgba(255,191,0,0.6)]",
  error: "bg-danger shadow-[0_0_8px_rgba(255,107,107,0.6)]",
  idle: "bg-ink-mute",
  info: "bg-primary shadow-[0_0_8px_rgba(129,236,255,0.6)]",
};

const TEXT_COLORS: Record<StatusKind, string> = {
  ok: "text-tertiary",
  warn: "text-secondary",
  error: "text-danger",
  idle: "text-ink-mute",
  info: "text-primary",
};

export function StatusIndicator({ status, label, className, pulse = true }: Props) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          COLORS[status],
          pulse && status !== "idle" && "animate-pulseDot",
        )}
      />
      {label !== undefined && (
        <span className={cn("label-mono", TEXT_COLORS[status])}>{label}</span>
      )}
    </span>
  );
}
