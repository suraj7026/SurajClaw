import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { sessionsApi } from "@/api/endpoints";
import { useApi } from "@/hooks/useApi";
import { useWebSocket } from "@/hooks/useWebSocket";
import { Panel } from "@/components/shared/Panel";
import { StatusIndicator } from "@/components/shared/StatusIndicator";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { cn } from "@/lib/cn";
import { formatRelative, formatTime } from "@/lib/format";
import type { UUID } from "@/types/api";

type ChatRole = "user" | "assistant" | "system" | "tool";

interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  ts: string;
  pending?: boolean;
}

interface IncomingFrame {
  type?: string;
  content?: string;
  text?: string;
  prompt?: string;
  approval_id?: string;
}

function uuidV4(): UUID {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback (non-crypto, dev-only).
  return "00000000-0000-4000-8000-000000000000".replace(/0/g, () =>
    Math.floor(Math.random() * 16).toString(16),
  );
}

export default function Chat() {
  const [sessionId] = useState<UUID>(() => uuidV4());
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const streamRef = useRef<ChatMessage | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: history } = useApi(
    () => sessionsApi.list({ is_active: true, limit: 8 }),
    [],
    { pollMs: 30_000 },
  );

  const onMessage = useCallback((data: unknown) => {
    const frame = data as IncomingFrame;
    if (!frame || typeof frame !== "object") return;
    switch (frame.type) {
      case "token":
      case "delta": {
        const piece = frame.content ?? frame.text ?? "";
        if (!piece) return;
        setMessages((prev) => {
          const next = [...prev];
          const current = streamRef.current;
          if (!current) {
            const m: ChatMessage = {
              id: uuidV4(),
              role: "assistant",
              content: piece,
              ts: new Date().toISOString(),
              pending: true,
            };
            streamRef.current = m;
            next.push(m);
          } else {
            current.content += piece;
            const idx = next.findIndex((m) => m.id === current.id);
            if (idx >= 0) next[idx] = { ...current };
          }
          return next;
        });
        return;
      }
      case "command_result":
      case "system": {
        const text = frame.content ?? frame.text ?? "";
        if (!text) return;
        setMessages((prev) => [
          ...prev,
          {
            id: uuidV4(),
            role: "system",
            content: text,
            ts: new Date().toISOString(),
          },
        ]);
        return;
      }
      case "approval": {
        setMessages((prev) => [
          ...prev,
          {
            id: uuidV4(),
            role: "system",
            content: `APPROVAL REQUIRED · ${frame.prompt ?? "tool execution gated"} (id=${frame.approval_id ?? "?"})\nReply with /approve ${frame.approval_id ?? ""} or /deny ${frame.approval_id ?? ""}.`,
            ts: new Date().toISOString(),
          },
        ]);
        return;
      }
      case "done": {
        if (streamRef.current) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamRef.current?.id ? { ...m, pending: false } : m,
            ),
          );
          streamRef.current = null;
        }
        setStreaming(false);
        return;
      }
      case "error": {
        setMessages((prev) => [
          ...prev,
          {
            id: uuidV4(),
            role: "system",
            content: `ERROR · ${frame.content ?? frame.text ?? "unknown"}`,
            ts: new Date().toISOString(),
          },
        ]);
        setStreaming(false);
        return;
      }
      default:
        // Unknown frame — log and ignore so we don't crash the UI.
        // eslint-disable-next-line no-console
        console.debug("unknown ws frame", frame);
    }
  }, []);

  const { status, send } = useWebSocket(`/ws/chat/${sessionId}/`, {
    onMessage,
  });

  // Auto-scroll on new messages.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const wsLabel = useMemo(() => {
    switch (status) {
      case "open":
        return "CONNECTED";
      case "connecting":
        return "CONNECTING";
      case "closed":
        return "OFFLINE";
      case "error":
        return "ERROR";
      default:
        return "IDLE";
    }
  }, [status]);

  const wsKind =
    status === "open"
      ? "ok"
      : status === "connecting"
        ? "info"
        : status === "error"
          ? "error"
          : "warn";

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || status !== "open") return;
    setMessages((prev) => [
      ...prev,
      {
        id: uuidV4(),
        role: "user",
        content: text,
        ts: new Date().toISOString(),
      },
    ]);
    send({ message: text });
    setDraft("");
    setStreaming(true);
  };

  return (
    <div className="p-4 sm:p-6 max-w-[1400px] mx-auto">
      <PageHeader
        title="Live Chat"
        subtitle={`Session ${sessionId.slice(0, 8)}…`}
        icon="forum"
        actions={<StatusIndicator status={wsKind} label={wsLabel} />}
      />

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
        <Panel
          title="Conversation"
          icon="chat"
          subtitle="Web channel · real-time stream"
          bodyClassName="p-0"
        >
          <div
            ref={scrollRef}
            className="h-[60vh] overflow-y-auto scroll-thin px-4 py-3 space-y-3"
          >
            {messages.length === 0 ? (
              <EmptyState
                icon="chat_bubble"
                title="Start the conversation"
                description="Try a slash command (/help, /status) or just ask the agent something."
              />
            ) : (
              messages.map((m) => <Bubble key={m.id} message={m} />)
            )}
          </div>
          <form
            onSubmit={handleSend}
            className="border-t border-border p-3 flex gap-2"
          >
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={
                status === "open" ? "Ask anything…" : "Connecting WebSocket…"
              }
              disabled={status !== "open"}
              className="input flex-1"
            />
            <button
              type="submit"
              disabled={status !== "open" || !draft.trim() || streaming}
              className="btn-primary"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                send
              </span>
              Send
            </button>
          </form>
        </Panel>

        <Panel
          title="Active Sessions"
          icon="history"
          subtitle="Other live conversations"
        >
          {!history || history.results.length === 0 ? (
            <EmptyState icon="history_toggle_off" title="No live sessions" />
          ) : (
            <ul className="space-y-2">
              {history.results.map((s) => (
                <li
                  key={s.id}
                  className="border border-border rounded p-2 bg-bg-base/40"
                >
                  <div className="flex items-center justify-between">
                    <span className="label-mono text-primary">{s.source}</span>
                    <span className="text-[10px] text-ink-mute font-mono">
                      {formatRelative(s.started_at)}
                    </span>
                  </div>
                  <p className="text-[11px] text-ink-dim line-clamp-2 mt-1">
                    {s.summary || "in progress…"}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[78%] rounded-lg border px-3 py-2 text-sm whitespace-pre-wrap break-words",
          isUser && "bg-primary/10 border-primary/40 text-ink",
          !isUser && !isSystem && "bg-bg-raised border-border text-ink",
          isSystem &&
            "bg-secondary/10 border-secondary/30 text-secondary font-mono text-xs",
          message.pending && "shadow-glow",
        )}
      >
        <div className="flex items-center justify-between gap-3 mb-1">
          <span className="label-mono">
            {isSystem ? "SYS" : isUser ? "YOU" : "AGENT"}
          </span>
          <span className="text-[10px] text-ink-mute font-mono">
            {formatTime(message.ts)}
          </span>
        </div>
        {message.content}
        {message.pending && (
          <span className="inline-block ml-1 animate-pulseDot text-primary">
            ▍
          </span>
        )}
      </div>
    </div>
  );
}
