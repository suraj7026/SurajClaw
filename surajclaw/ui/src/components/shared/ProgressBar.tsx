import { cn } from "@/lib/cn";

interface Props {
  value: number; // 0..100
  label?: string;
  hint?: string;
  tone?: "primary" | "secondary" | "tertiary" | "danger";
  className?: string;
}

const TONES = {
  primary: "bg-primary shadow-[0_0_10px_rgba(129,236,255,0.55)]",
  secondary: "bg-secondary shadow-[0_0_10px_rgba(255,191,0,0.55)]",
  tertiary: "bg-tertiary shadow-[0_0_10px_rgba(184,255,187,0.55)]",
  danger: "bg-danger shadow-[0_0_10px_rgba(255,107,107,0.55)]",
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
          {label && <span className="label-mono">{label}</span>}
          {hint && <span className="label-mono text-ink-dim">{hint}</span>}
        </div>
      )}
      <div className="relative h-1.5 bg-bg-base border border-border rounded-sm overflow-hidden">
        <div
          className={cn("h-full transition-all duration-500 ease-out", TONES[tone])}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
