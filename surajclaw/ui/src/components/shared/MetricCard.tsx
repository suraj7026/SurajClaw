import { cn } from "@/lib/cn";

interface Props {
  label: string;
  value: string | number;
  hint?: string;
  trend?: {
    direction: "up" | "down" | "flat";
    value: string;
  };
  icon?: string;
  tone?: "primary" | "secondary" | "tertiary" | "danger" | "neutral";
  className?: string;
}

const TONES: Record<NonNullable<Props["tone"]>, string> = {
  primary: "text-primary",
  secondary: "text-secondary",
  tertiary: "text-tertiary",
  danger: "text-danger",
  neutral: "text-ink",
};

const TREND_TONES = {
  up: "text-tertiary",
  down: "text-danger",
  flat: "text-ink-dim",
};

const TREND_ICON = {
  up: "trending_up",
  down: "trending_down",
  flat: "trending_flat",
};

export function MetricCard({
  label,
  value,
  hint,
  trend,
  icon,
  tone = "neutral",
  className,
}: Props) {
  return (
    <div className={cn("panel p-4 relative overflow-hidden", className)}>
      <div className="flex items-start justify-between gap-3">
        <span className="label-mono">{label}</span>
        {icon && (
          <span
            className={cn(
              "material-symbols-outlined text-base opacity-60",
              TONES[tone],
            )}
            style={{ fontSize: "18px" }}
          >
            {icon}
          </span>
        )}
      </div>
      <div className={cn("font-display text-3xl mt-2 tabular-nums", TONES[tone])}>
        {value}
      </div>
      <div className="flex items-center justify-between mt-2 text-xs">
        {hint ? <span className="text-ink-dim">{hint}</span> : <span />}
        {trend && (
          <span
            className={cn(
              "inline-flex items-center gap-1 label-mono",
              TREND_TONES[trend.direction],
            )}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "14px" }}
            >
              {TREND_ICON[trend.direction]}
            </span>
            {trend.value}
          </span>
        )}
      </div>
    </div>
  );
}
