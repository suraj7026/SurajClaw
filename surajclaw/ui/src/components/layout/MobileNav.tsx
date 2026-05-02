import { NavLink } from "react-router-dom";

import { NAV_ITEMS } from "./SideNav";
import { cn } from "@/lib/cn";

const MOBILE_ITEMS = NAV_ITEMS.slice(0, 4);

export function MobileNav() {
  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-bg-surface border-t border-border">
      <ul className="flex justify-around items-center h-16 px-4">
        {MOBILE_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex flex-col items-center gap-1 py-1",
                  isActive ? "text-primary" : "text-ink-mute",
                )
              }
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "22px" }}
              >
                {item.icon}
              </span>
              <span className="text-[10px] font-display uppercase tracking-wider">
                {item.label}
              </span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
