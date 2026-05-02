import { cn } from "@/lib/cn";

interface Props {
  value: number;
  label?: string;
  hint?: string;
  tone?: "primary" | "secondary" | "tertiary" | "danger";
  className?: string;
}

const BAR_COLORS = {
  primary: "bg-primary",
  secondary: "bg-secondary",
  tertiary: "bg-tertiary",
  danger: "bg-danger",
};

const TEXT_COLORS = {
  primary: "text-primary",
  secondary: "text-secondary",
  tertiary: "text-tertiary",
  danger: "text-danger",
};

export function ProgressBar({
  value,
  label,
  hint,
  tone = "primary",
  className,
}: Props) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("space-y-1.5", className)}>
      {(label || hint) && (
        <div className="flex items-center justify-between">
          {label && (
            <span className="text-[10px] font-display uppercase tracking-widest text-ink-mute">
              {label}
            </span>
          )}
          {hint && (
            <span className={cn("text-[10px] font-display", TEXT_COLORS[tone])}>
              {hint}
            </span>
          )}
        </div>
      )}
      <div className="relative h-1.5 bg-bg-overlay rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500 ease-out", BAR_COLORS[tone])}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
