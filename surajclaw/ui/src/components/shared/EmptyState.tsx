import { cn } from "@/lib/cn";

interface Props {
  icon?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ icon = "blur_on", title, description, action, className }: Props) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center py-10 px-4 text-ink-dim",
        className,
      )}
    >
      <span
        className="material-symbols-outlined text-primary/50 mb-3"
        style={{ fontSize: "36px" }}
      >
        {icon}
      </span>
      <p className="font-display text-sm font-bold uppercase tracking-wider text-ink">
        {title}
      </p>
      {description && <p className="text-xs mt-1.5 max-w-xs text-ink-dim">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
