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
    <header className="h-14 shrink-0 border-b border-border bg-bg-surface/80 backdrop-blur flex items-center px-4 gap-4 z-20">
      <div className="md:hidden flex items-center gap-2">
        <span className="font-display text-sm tracking-wider text-primary">
          SURAJCLAW
        </span>
      </div>
      <div className="flex-1 hidden md:flex items-center gap-6 text-xs">
        <div className="flex items-center gap-2">
          <StatusIndicator status={statusKindFor(doctor?.status)} />
          <span className="label-mono">
            {doctor?.status ? `SYSTEM ${doctor.status.toUpperCase()}` : "BOOTING"}
          </span>
        </div>
        <span className="font-mono text-ink-mute">|</span>
        <span className="font-mono text-ink-dim">{stamp}</span>
      </div>
      <div className="flex items-center gap-3">
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
          className="btn"
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
