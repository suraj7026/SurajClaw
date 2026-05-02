import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";

interface Props {
  children: React.ReactNode;
}

export function RequireAuth({ children }: Props) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-bg-base text-ink-dim">
        <div className="flex items-center gap-3 font-display text-xs uppercase tracking-widest">
          <span className="h-2 w-2 animate-pulseDot rounded-full bg-primary shadow-[0_0_8px_var(--primary-glow)]" />
          Authenticating session…
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
