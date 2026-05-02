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
    <div className="min-h-screen flex items-center justify-center px-4 bg-bg-base">
      <div className="w-full max-w-sm">
        {/* Brand header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-primary/10 border border-primary/20 mb-4">
            <span className="material-symbols-outlined text-primary" style={{ fontSize: "28px" }}>security</span>
          </div>
          <p className="font-display text-xs text-primary font-bold uppercase tracking-[0.2em]">SURAJCLAW</p>
          <h1 className="font-display text-2xl font-semibold tracking-tight mt-1">Operator Sign-In</h1>
          <p className="text-xs text-ink-mute mt-2">Authenticate to access the control console.</p>
        </div>

        {/* Login card */}
        <div className="panel p-6">
          <form className="space-y-5" onSubmit={handleSubmit}>
            <div className="space-y-1.5">
              <label htmlFor="login-username" className="font-display text-[10px] font-bold text-ink-mute uppercase tracking-widest">Username</label>
              <input id="login-username" type="text" required autoComplete="username" autoFocus
                value={username} onChange={(e) => setUsername(e.target.value)}
                className="input w-full" placeholder="Operator username"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="login-password" className="font-display text-[10px] font-bold text-ink-mute uppercase tracking-widest">Password</label>
              <input id="login-password" type="password" required autoComplete="current-password"
                value={password} onChange={(e) => setPassword(e.target.value)}
                className="input w-full" placeholder="Password"
              />
            </div>
            {error && (
              <div className="text-xs text-danger border border-danger/30 bg-danger/10 px-3 py-2 rounded">{error}</div>
            )}
            <button type="submit" disabled={loading || submitting} className="btn-solid w-full justify-center py-2.5">
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>login</span>
              {submitting ? "Authenticating…" : "Authenticate"}
            </button>
          </form>
          <p className="text-[11px] text-ink-mute leading-relaxed mt-5 text-center">
            Backed by Django auth tokens. Create the operator account with{" "}
            <code className="text-primary font-mono text-[10px]">manage.py createsuperuser</code> on the host.
          </p>
        </div>
      </div>
    </div>
  );
}
