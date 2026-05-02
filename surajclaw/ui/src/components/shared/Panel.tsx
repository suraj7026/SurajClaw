import { cn } from "@/lib/cn";

interface Props {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  icon?: string;
  scanline?: boolean;
  glass?: boolean;
  bodyClassName?: string;
  className?: string;
  children: React.ReactNode;
}

export function Panel({
  title,
  subtitle,
  actions,
  icon,
  scanline,
  glass,
  bodyClassName,
  className,
  children,
}: Props) {
  return (
    <section
      className={cn(
        glass ? "panel-glass" : "panel",
        scanline && "scanline",
        className,
      )}
    >
      {(title || actions) && (
        <header className="panel-header">
          <div className="flex items-center gap-2 min-w-0">
            {icon && (
              <span
                className="material-symbols-outlined text-primary shrink-0"
                style={{ fontSize: "18px" }}
              >
                {icon}
              </span>
            )}
            <div className="min-w-0">
              {title && (
                <h3 className="font-display text-xs font-bold tracking-[0.1rem] uppercase truncate">
                  {title}
                </h3>
              )}
              {subtitle && (
                <p className="text-xs text-ink-dim truncate">{subtitle}</p>
              )}
            </div>
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn("panel-body", bodyClassName)}>{children}</div>
    </section>
  );
}
