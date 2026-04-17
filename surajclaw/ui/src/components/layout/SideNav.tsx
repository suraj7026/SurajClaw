import { NavLink } from "react-router-dom";

import { cn } from "@/lib/cn";

export interface NavItem {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: "dashboard", end: true },
  { to: "/pipeline", label: "Pipeline", icon: "schema" },
  { to: "/memory", label: "Memory", icon: "memory" },
  { to: "/tasks", label: "Tasks", icon: "schedule" },
  { to: "/chat", label: "Chat", icon: "forum" },
  { to: "/integrations", label: "Integrations", icon: "hub" },
];

interface Props {
  className?: string;
}

export function SideNav({ className }: Props) {
  return (
    <nav
      className={cn(
        "hidden md:flex flex-col w-56 shrink-0 border-r border-border bg-bg-surface/60",
        className,
      )}
    >
      <div className="px-4 py-5 border-b border-border">
        <p className="label-mono text-primary">SURAJCLAW</p>
        <p className="font-display text-base mt-0.5 leading-tight">
          Operator Console
        </p>
      </div>
      <ul className="flex-1 py-3 space-y-0.5">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-4 py-2.5 text-sm transition-colors",
                  "border-l-2 border-transparent",
                  "text-ink-dim hover:text-ink hover:bg-bg-raised/50",
                  isActive &&
                    "text-primary border-primary bg-primary/5 font-medium",
                )
              }
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "20px" }}
              >
                {item.icon}
              </span>
              <span className="font-display tracking-wide uppercase text-xs">
                {item.label}
              </span>
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="px-4 py-3 border-t border-border text-[10px] text-ink-mute">
        <div className="flex items-center justify-between">
          <span className="label-mono">Build</span>
          <span className="font-mono">v0.1.0</span>
        </div>
      </div>
    </nav>
  );
}
