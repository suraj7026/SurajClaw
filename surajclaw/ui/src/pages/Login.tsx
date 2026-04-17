import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";

export default function Login() {
  const { login, loading, error } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const next = (location.state as { from?: string } | null)?.from ?? "/";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(username, password);
      navigate(next, { replace: true });
    } catch {
      // error surfaces via context
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm panel scanline overflow-hidden">
        <header className="panel-header flex-col items-start gap-1">
          <p className="label-mono text-primary">SURAJCLAW</p>
          <h1 className="font-display text-lg uppercase tracking-wide">
            Operator Sign-In
          </h1>
        </header>
        <form className="panel-body space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-1.5">
            <label className="label-mono">Username</label>
            <input
              type="text"
              required
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="input w-full"
            />
          </div>
          <div className="space-y-1.5">
            <label className="label-mono">Password</label>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input w-full"
            />
          </div>
          {error && (
            <div className="text-xs text-danger border border-danger/30 bg-danger/10 px-3 py-2 rounded">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={loading || submitting}
            className="btn-primary w-full justify-center"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              login
            </span>
            {submitting ? "Authenticating…" : "Authenticate"}
          </button>
          <p className="text-[11px] text-ink-mute leading-relaxed">
            Backed by Django auth tokens. Create the operator account with{" "}
            <code className="text-primary">manage.py createsuperuser</code> on
            the host.
          </p>
        </form>
      </div>
    </div>
  );
}
