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
  { to: "/pipeline", label: "Pipeline", icon: "account_tree" },
  { to: "/tasks", label: "Tasks", icon: "assignment" },
  { to: "/memory", label: "Memory", icon: "memory" },
  { to: "/chat", label: "Chat", icon: "forum" },
  { to: "/integrations", label: "Integrations", icon: "hub" },
];

interface Props {
  className?: string;
}

export function SideNav({ className }: Props) {
  return (
    <aside
      className={cn(
        "hidden md:flex flex-col w-64 shrink-0 h-screen",
        "bg-[var(--sidebar-bg)] border-r border-border",
        className,
      )}
    >
      {/* Operator identity card */}
      <div className="px-6 pt-8 pb-6">
        <div className="flex items-center gap-3 p-3 bg-bg-raised rounded-lg mb-4">
          <div className="w-10 h-10 bg-primary/10 rounded flex items-center justify-center">
            <span
              className="material-symbols-outlined text-primary filled"
              style={{ fontSize: "20px" }}
            >
              security
            </span>
          </div>
          <div>
            <div className="text-[var(--sidebar-text-active)] font-black text-xs font-display">
              OPERATOR_01
            </div>
            <div className="text-[10px] text-ink-mute font-display uppercase tracking-widest">
              LEVEL_4_ACCESS
            </div>
          </div>
        </div>
      </div>

      {/* Navigation links */}
      <nav className="flex-1 font-display uppercase tracking-[0.05rem] text-xs">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "px-6 py-3 flex items-center gap-3 transition-all duration-200",
                isActive
                  ? "bg-[var(--sidebar-active)] text-[var(--sidebar-text-active)] border-l-4 border-[var(--sidebar-border)]"
                  : "text-[var(--sidebar-text)] hover:bg-bg-raised/50 hover:text-primary border-l-4 border-transparent",
              )
            }
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "20px" }}
            >
              {item.icon}
            </span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Bottom section */}
      <div className="px-6 pb-6 mt-auto">
        <button type="button" className="btn-emergency rounded mb-4">
          EMERGENCY_HALT
        </button>
        <div className="flex flex-col gap-2 border-t border-border pt-4 font-display text-[10px]">
          <a
            href="#"
            className="text-ink-mute flex items-center gap-2 hover:text-primary transition-colors"
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "14px" }}
            >
              description
            </span>
            Docs
          </a>
          <a
            href="#"
            className="text-ink-mute flex items-center gap-2 hover:text-primary transition-colors"
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "14px" }}
            >
              help
            </span>
            Support
          </a>
        </div>
      </div>
    </aside>
  );
}
