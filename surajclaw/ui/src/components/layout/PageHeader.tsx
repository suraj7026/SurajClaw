import { cn } from "@/lib/cn";

interface Props {
  title: string;
  subtitle?: string;
  icon?: string;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, subtitle, icon, actions, className }: Props) {
  return (
    <div
      className={cn(
        "flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6",
        className,
      )}
    >
      <div className="flex items-center gap-3">
        {icon && (
          <span
            className="material-symbols-outlined text-primary border border-border rounded-lg p-2 bg-bg-surface"
            style={{ fontSize: "22px" }}
          >
            {icon}
          </span>
        )}
        <div>
          <h1 className="font-display text-xl sm:text-2xl tracking-wide uppercase">
            {title}
          </h1>
          {subtitle && (
            <p className="text-xs sm:text-sm text-ink-dim mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex items-center gap-2 flex-wrap">{actions}</div>
      )}
    </div>
  );
}
