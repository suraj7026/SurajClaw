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

const BORDER_TONES: Record<NonNullable<Props["tone"]>, string> = {
  primary: "border-l-primary",
  secondary: "border-l-secondary",
  tertiary: "border-l-tertiary",
  danger: "border-l-danger",
  neutral: "border-l-ink-mute",
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
    <div
      className={cn(
        "panel p-4 border-l-2 relative overflow-hidden",
        BORDER_TONES[tone],
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="text-[10px] font-display font-bold text-ink-mute uppercase tracking-widest">
          {label}
        </span>
        {icon && (
          <span
            className={cn("material-symbols-outlined opacity-60", TONES[tone])}
            style={{ fontSize: "20px" }}
          >
            {icon}
          </span>
        )}
      </div>
      <div className={cn("font-display text-2xl font-bold mt-1 tabular-nums", TONES[tone])}>
        {value}
      </div>
      <div className="flex items-center justify-between mt-2 text-xs">
        {hint ? <span className="text-ink-dim">{hint}</span> : <span />}
        {trend && (
          <span
            className={cn(
              "inline-flex items-center gap-1 text-[11px] font-bold",
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
