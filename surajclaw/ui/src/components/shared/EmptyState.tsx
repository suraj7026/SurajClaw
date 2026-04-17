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
        className="material-symbols-outlined text-primary/60 mb-2"
        style={{ fontSize: "32px" }}
      >
        {icon}
      </span>
      <p className="font-display text-sm uppercase tracking-wider text-ink">{title}</p>
      {description && <p className="text-xs mt-1 max-w-xs">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
