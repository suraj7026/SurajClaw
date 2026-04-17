import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { googleApi } from "@/api/endpoints";
import { useApi } from "@/hooks/useApi";
import { Panel } from "@/components/shared/Panel";
import { StatusIndicator } from "@/components/shared/StatusIndicator";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";

const LABEL_HINT =
  "Use lowercase letters, digits, dash or underscore (e.g. personal, work, ops).";

const SCOPE_PRESETS: { id: string; label: string }[] = [
  { id: "gmail.readonly", label: "Gmail (read)" },
  { id: "calendar", label: "Calendar" },
  { id: "tasks", label: "Tasks" },
  { id: "drive.file", label: "Drive (app files)" },
  { id: "documents", label: "Docs" },
  { id: "spreadsheets", label: "Sheets" },
  { id: "contacts.readonly", label: "Contacts" },
];

export default function Integrations() {
  const { data: accounts, reload, error: listError } = useApi(
    () => googleApi.list(),
    [],
    { pollMs: 30_000 },
  );
  const [searchParams, setSearchParams] = useSearchParams();
  const [newLabel, setNewLabel] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [inflight, setInflight] = useState<string | null>(null);
  const [toast, setToast] = useState<
    { kind: "ok" | "error"; message: string } | null
  >(null);

  // Surface OAuth callback flags as a toast and clean the URL.
  useEffect(() => {
    const status = searchParams.get("google");
    if (!status) return;
    if (status === "ok") {
      const label = searchParams.get("label") ?? "";
      setToast({
        kind: "ok",
        message: `Connected Google account "${label}".`,
      });
      void reload();
    } else {
      setToast({
        kind: "error",
        message:
          "OAuth flow failed: " + (searchParams.get("reason") ?? "unknown"),
      });
    }
    // Strip the params so refresh doesn't re-fire the toast.
    searchParams.delete("google");
    searchParams.delete("label");
    searchParams.delete("reason");
    setSearchParams(searchParams, { replace: true });
  }, [searchParams, setSearchParams, reload]);

  const handleConnect = async (label: string) => {
    setInflight(`connect:${label}`);
    setActionError(null);
    try {
      const { auth_url } = await googleApi.connect(label);
      // Top-level redirect — Google won't render in an iframe.
      window.location.href = auth_url;
    } catch (err) {
      setActionError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "connect failed",
      );
      setInflight(null);
    }
  };

  const handleDisconnect = async (label: string) => {
    if (!window.confirm(`Disconnect ${label}? Token will be deleted.`)) return;
    setInflight(`disconnect:${label}`);
    setActionError(null);
    try {
      await googleApi.disconnect(label);
      await reload();
    } catch (err) {
      setActionError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "disconnect failed",
      );
    } finally {
      setInflight(null);
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-[1200px] mx-auto">
      <PageHeader
        title="Integrations"
        subtitle="Connected services · OAuth tokens"
        icon="hub"
      />

      {toast && (
        <div
          className={cn(
            "mb-4 px-3 py-2 rounded border text-xs flex items-center justify-between",
            toast.kind === "ok"
              ? "border-tertiary/40 bg-tertiary/10 text-tertiary"
              : "border-danger/40 bg-danger/10 text-danger",
          )}
        >
          <span>{toast.message}</span>
          <button
            type="button"
            onClick={() => setToast(null)}
            className="text-ink-dim hover:text-ink"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              close
            </span>
          </button>
        </div>
      )}

      {(actionError || listError) && (
        <div className="mb-4 px-3 py-2 rounded border border-danger/40 bg-danger/10 text-danger text-xs">
          {actionError || listError}
        </div>
      )}

      <Panel
        title="Google Workspace Accounts"
        subtitle="Tokens stored under GOOGLE_TOKEN_DIR"
        icon="account_circle"
        className="mb-4"
      >
        {!accounts || accounts.length === 0 ? (
          <EmptyState
            icon="link_off"
            title="No accounts connected"
            description="Connect a Google account below to enable Gmail, Calendar, Drive, and Tasks tools."
          />
        ) : (
          <ul className="space-y-2">
            {accounts.map((acct) => (
              <li
                key={acct.label}
                className="border border-border rounded-md p-3 bg-bg-base/40"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <StatusIndicator status="ok" />
                      <span className="font-display text-sm uppercase tracking-wider">
                        {acct.label}
                      </span>
                    </div>
                    <p className="text-xs text-ink-dim font-mono truncate">
                      {acct.email || acct.token_path}
                    </p>
                    {acct.expires_at && (
                      <p className="text-[10px] text-ink-mute mt-1 font-mono">
                        Expires {formatDateTime(acct.expires_at)}
                      </p>
                    )}
                    {acct.scopes && acct.scopes.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {acct.scopes.map((scope) => (
                          <span
                            key={scope}
                            className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-primary/30 text-primary"
                            title={scope}
                          >
                            {scope.replace(
                              "https://www.googleapis.com/auth/",
                              "",
                            )}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => handleConnect(acct.label)}
                      disabled={inflight === `connect:${acct.label}`}
                      className="btn"
                      title="Re-run OAuth flow to refresh scopes"
                    >
                      <span
                        className="material-symbols-outlined"
                        style={{ fontSize: "14px" }}
                      >
                        refresh
                      </span>
                      Refresh
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDisconnect(acct.label)}
                      disabled={inflight === `disconnect:${acct.label}`}
                      className="btn-danger"
                    >
                      <span
                        className="material-symbols-outlined"
                        style={{ fontSize: "14px" }}
                      >
                        link_off
                      </span>
                      Disconnect
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Connect a New Account" icon="add_link" scanline>
        <form
          className="flex flex-col sm:flex-row gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (newLabel.trim()) void handleConnect(newLabel.trim());
          }}
        >
          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value.toLowerCase())}
            placeholder="account label (e.g. personal)"
            pattern="[a-z0-9][a-z0-9_-]{0,31}"
            className="input flex-1"
          />
          <button
            type="submit"
            disabled={!newLabel.trim() || inflight === `connect:${newLabel.trim()}`}
            className="btn-primary justify-center"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              login
            </span>
            Begin OAuth
          </button>
        </form>
        <p className="text-[11px] text-ink-mute mt-2">{LABEL_HINT}</p>
        <div className="mt-4 border-t border-border pt-3">
          <p className="label-mono mb-2">Default Scopes Requested</p>
          <div className="flex flex-wrap gap-1">
            {SCOPE_PRESETS.map((s) => (
              <span
                key={s.id}
                className="text-[10px] font-mono px-2 py-1 rounded border border-border text-ink-dim"
              >
                {s.label}
              </span>
            ))}
          </div>
          <p className="text-[11px] text-ink-mute mt-3 leading-relaxed">
            The OAuth client must have an authorized redirect URI matching{" "}
            <code className="text-primary">
              {window.location.origin}/api/google/accounts/callback/
            </code>
            . Configure the client in Google Cloud Console &rsaquo; APIs &rsaquo; Credentials.
          </p>
        </div>
      </Panel>
    </div>
  );
}
