import { useEffect, useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { useApi } from "@/hooks/useApi";
import { systemApi } from "@/api/endpoints";
import { StatusIndicator } from "@/components/shared/StatusIndicator";
import type { DoctorStatus } from "@/types/api";

function statusKindFor(status: DoctorStatus | undefined) {
  if (!status) return "idle" as const;
  if (status === "ok") return "ok" as const;
  if (status === "warn") return "warn" as const;
  return "error" as const;
}

export function TopAppBar() {
  const { user, logout } = useAuth();
  const { data: doctor } = useApi(() => systemApi.doctor(), [], { pollMs: 30_000 });
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const stamp = now
    .toLocaleString(undefined, {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      day: "2-digit",
      month: "short",
    })
    .toUpperCase();

  return (
    <header
      className="h-16 shrink-0 flex items-center justify-between px-6 z-20"
      style={{
        background: "var(--header-bg)",
        boxShadow: "var(--header-shadow)",
      }}
    >
      {/* Mobile brand */}
      <div className="md:hidden flex items-center gap-2">
        <span className="text-xl font-bold tracking-tighter text-primary font-display">
          SURAJCLAW
        </span>
      </div>

      {/* Desktop brand + status */}
      <div className="hidden md:flex items-center gap-4">
        <span className="text-xl font-bold tracking-tighter text-primary font-display">
          SURAJCLAW
        </span>
      </div>

      {/* Desktop nav links */}
      <nav className="hidden md:flex items-center gap-6 font-display tracking-wider uppercase text-sm">
        <div className="flex items-center gap-2">
          <StatusIndicator status={statusKindFor(doctor?.status)} />
          <span className="text-ink-dim text-xs">
            {doctor?.status ? `SYSTEM_${doctor.status.toUpperCase()}` : "BOOTING"}
          </span>
        </div>
        <span className="text-ink-mute">|</span>
        <span className="font-mono text-ink-dim text-xs">{stamp}</span>
      </nav>

      {/* Right section */}
      <div className="flex items-center gap-4">
        <button
          type="button"
          className="text-ink-mute hover:text-primary transition-colors"
        >
          <span className="material-symbols-outlined">notifications</span>
        </button>
        <button
          type="button"
          className="text-ink-mute hover:text-primary transition-colors"
        >
          <span className="material-symbols-outlined">settings</span>
        </button>
        {user && (
          <span className="hidden sm:inline-flex items-center gap-2 text-xs text-ink-dim">
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              account_circle
            </span>
            <span className="font-mono">{user.username}</span>
          </span>
        )}
        <button
          type="button"
          onClick={() => void logout()}
          className="btn text-xs"
          title="Sign out"
        >
          <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
            logout
          </span>
          <span className="hidden sm:inline">Sign out</span>
        </button>
      </div>
    </header>
  );
}
