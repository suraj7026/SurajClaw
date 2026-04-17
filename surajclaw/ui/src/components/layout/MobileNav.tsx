import { NavLink } from "react-router-dom";

import { NAV_ITEMS } from "./SideNav";
import { cn } from "@/lib/cn";

export function MobileNav() {
  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-bg-surface/95 backdrop-blur border-t border-border">
      <ul className="grid grid-cols-6">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex flex-col items-center gap-0.5 py-2 text-[10px] text-ink-dim",
                  isActive && "text-primary",
                )
              }
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "20px" }}
              >
                {item.icon}
              </span>
              <span className="uppercase tracking-wider">{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
