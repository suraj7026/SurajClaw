import { cn } from "@/lib/cn";

export type StatusKind = "ok" | "warn" | "error" | "idle" | "info";

interface Props {
  status: StatusKind;
  label?: string;
  className?: string;
  pulse?: boolean;
}

const DOT_COLORS: Record<StatusKind, string> = {
  ok: "bg-tertiary",
  warn: "bg-secondary",
  error: "bg-danger",
  idle: "bg-ink-mute",
  info: "bg-primary",
};

const GLOW_COLORS: Record<StatusKind, string> = {
  ok: "shadow-[0_0_8px_var(--tertiary-glow)]",
  warn: "shadow-[0_0_8px_var(--secondary-glow)]",
  error: "shadow-[0_0_8px_var(--danger-glow)]",
  idle: "",
  info: "shadow-[0_0_8px_var(--primary-glow)]",
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
          DOT_COLORS[status],
          status !== "idle" && GLOW_COLORS[status],
          pulse && status !== "idle" && "animate-pulseDot",
        )}
      />
      {label !== undefined && (
        <span className={cn("text-[10px] font-display font-bold uppercase tracking-widest", TEXT_COLORS[status])}>
          {label}
        </span>
      )}
    </span>
  );
}
