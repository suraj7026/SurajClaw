import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { sessionsApi } from "@/api/endpoints";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/context/AuthContext";
import { useWebSocket } from "@/hooks/useWebSocket";
import { cn } from "@/lib/cn";
import { formatTime } from "@/lib/format";
import type { Message as ApiMessage, Session, UUID } from "@/types/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Constants — model picker + suggested prompts.
//
// `MODELS` mirrors the providers our agent.graph wires up; keeping the list
// hard-coded avoids a round trip just to render the dropdown.
// ---------------------------------------------------------------------------
const MODELS = [
  { id: "auto", label: "Auto", hint: "Pick best for the task" },
  { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash", hint: "Fast · default" },
  { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro", hint: "Deeper reasoning" },
];

const SUGGESTIONS: Array<{
  icon: string;
  title: string;
  subtitle: string;
  prompt: string;
}> = [
  {
    icon: "code",
    title: "Show me a code snippet",
    subtitle: "of a website's sticky header",
    prompt:
      "Show me a code snippet for a website's sticky header in plain HTML/CSS.",
  },
  {
    icon: "palette",
    title: "Give me ideas",
    subtitle: "for what to do with my kids' art",
    prompt: "Give me ideas for what to do with my kids' art.",
  },
  {
    icon: "schedule",
    title: "Overcome procrastination",
    subtitle: "give me tips",
    prompt: "Give me tips to overcome procrastination today.",
  },
  {
    icon: "school",
    title: "Help me study",
    subtitle: "vocabulary for a college entrance exam",
    prompt:
      "Help me study vocabulary for a college entrance exam. Quiz me on 10 words.",
  },
];

function uuidV4(): UUID {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "00000000-0000-4000-8000-000000000000".replace(/0/g, () =>
    Math.floor(Math.random() * 16).toString(16),
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function Chat() {
  const { user } = useAuth();
  // Single-active-session policy: on mount we try to resume the last
  // open web session before falling back to a brand-new UUID. The
  // initial value is a synchronous placeholder so the WebSocket hook
  // can connect immediately; the resume effect below replaces it once
  // the API responds. `sessionReady` gates the WS connection so we
  // don't briefly spin up a session row that gets thrown away when
  // the resume fetch returns.
  const [sessionId, setSessionId] = useState<UUID>(() => uuidV4());
  const [sessionReady, setSessionReady] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [model, setModel] = useState(MODELS[0]!);
  const [modelOpen, setModelOpen] = useState(false);
  const [search, setSearch] = useState("");

  const streamRef = useRef<ChatMessage | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const modelRef = useRef<HTMLDivElement>(null);

  const { data: history, reload: reloadHistory } = useApi(
    () => sessionsApi.list({ source: "web", limit: 30 }),
    [],
    { pollMs: 30_000 },
  );

  // -----------------------------------------------------------------------
  // Resume the most recent active session (or accept the placeholder
  // UUID we already minted). Runs once on mount.
  // -----------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await sessionsApi.list({
          source: "web",
          is_active: true,
          limit: 1,
        });
        const live = list.results[0];
        if (cancelled) return;
        if (live) {
          setSessionId(live.id);
          // Hydrate prior messages so the user lands back inside the
          // conversation they left, not an empty pane.
          try {
            const past = await sessionsApi.messages(live.id, 200);
            const rows: ApiMessage[] = Array.isArray(past)
              ? past
              : past.results;
            if (cancelled) return;
            setMessages(
              rows.map((m) => ({
                id: m.id,
                role: m.role as ChatRole,
                content: m.content,
                ts: m.created_at,
              })),
            );
          } catch {
            // History fetch is best-effort; an empty pane is fine.
          }
        }
      } catch {
        // No-op; we'll just use the placeholder UUID and create a new
        // session on first send.
      } finally {
        if (!cancelled) setSessionReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -----------------------------------------------------------------------
  // WebSocket frames → message log. Token frames are coalesced into a single
  // streaming assistant bubble; `done` flips the pending flag off.
  // -----------------------------------------------------------------------
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
            const idx = next.findIndex((msg) => msg.id === current.id);
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
        // eslint-disable-next-line no-console
        console.debug("unknown ws frame", frame);
    }
  }, []);

  // Hold the connection until the resume probe finishes so we don't
  // briefly open a WS for the placeholder UUID and then have to swap.
  const { status, send } = useWebSocket(
    sessionReady ? `/ws/chat/${sessionId}/` : null,
    { onMessage },
  );

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  // Close the model menu on outside click.
  useEffect(() => {
    if (!modelOpen) return;
    const onDocClick = (ev: MouseEvent) => {
      if (modelRef.current && !modelRef.current.contains(ev.target as Node)) {
        setModelOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [modelOpen]);

  // Auto-grow the composer textarea up to ~6 lines.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [draft]);

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------
  const wsLabel = useMemo(() => {
    switch (status) {
      case "open":
        return "Connected";
      case "connecting":
        return "Connecting…";
      case "closed":
        return "Offline";
      case "error":
        return "Error";
      default:
        return "Idle";
    }
  }, [status]);

  const wsTone =
    status === "open"
      ? "bg-tertiary"
      : status === "connecting"
        ? "bg-primary"
        : status === "error"
          ? "bg-danger"
          : "bg-ink-mute";

  const greetingName = useMemo(() => {
    if (!user?.username) return "there";
    const u = user.username;
    return u.charAt(0).toUpperCase() + u.slice(1);
  }, [user?.username]);

  const initials = useMemo(() => {
    const u = user?.username ?? "OP";
    return u.slice(0, 2).toUpperCase();
  }, [user?.username]);

  const grouped = useMemo(() => {
    // Hide empty placeholder sessions (zero messages) — they're typically
    // pages that were opened but never sent in. Always keep the
    // currently-active sessionId visible even if empty so the user can
    // see where they are.
    const rows = (history?.results ?? []).filter(
      (s) => (s.message_count ?? 0) > 0 || s.id === sessionId,
    );
    return groupSessionsByDate(rows, search);
  }, [history?.results, search, sessionId]);

  // -----------------------------------------------------------------------
  // Handlers
  // -----------------------------------------------------------------------
  const submitText = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || status !== "open") return;
      setMessages((prev) => [
        ...prev,
        {
          id: uuidV4(),
          role: "user",
          content: trimmed,
          ts: new Date().toISOString(),
        },
      ]);
      send({ message: trimmed });
      setDraft("");
      setStreaming(true);
    },
    [send, status],
  );

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submitText(draft);
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitText(draft);
    }
  };

  const handleNewChat = () => {
    // Mint a fresh UUID; the backend's single-active policy will close
    // the previous session as soon as the first message persists.
    setSessionId(uuidV4());
    setSessionReady(true);
    setMessages([]);
    setDraft("");
    streamRef.current = null;
    setStreaming(false);
    // Refresh the rail so the just-retired session shows the right
    // "active" badge state on next render.
    void reloadHistory();
  };

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 bg-bg-base text-ink">
      {/* ===========================================================
       *  Conversations rail — chat-scoped sidebar (history, search,
       *  new-chat). Sits inside the global SideNav so the operator
       *  console still owns the outermost shell.
       *  ========================================================= */}
      <aside className="hidden lg:flex w-64 shrink-0 flex-col border-r border-border bg-[var(--sidebar-bg)]">
        <div className="px-3 pt-4 pb-2 flex items-center justify-between">
          <button
            type="button"
            onClick={handleNewChat}
            className="flex-1 flex items-center gap-2 rounded-md px-3 py-2 text-sm font-display font-semibold text-ink hover:bg-bg-raised transition-colors"
          >
            <span
              className="material-symbols-outlined text-primary"
              style={{ fontSize: "18px" }}
            >
              edit_square
            </span>
            New Chat
          </button>
          <button
            type="button"
            className="ml-1 p-2 rounded-md text-ink-mute hover:bg-bg-raised hover:text-primary transition-colors"
            title="Toggle rail"
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "18px" }}
            >
              dock_to_right
            </span>
          </button>
        </div>

        <nav className="px-2 mt-1 space-y-0.5">
          <RailItem icon="grid_view" label="Workspace" />
          <RailItem icon="search" label="Search" asSearch>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search"
              className="w-full bg-transparent text-sm text-ink placeholder:text-ink-mute focus:outline-none"
            />
          </RailItem>
        </nav>

        <div className="flex-1 overflow-y-auto scroll-thin px-2 mt-3 pb-4">
          {grouped.length === 0 ? (
            <p className="px-3 py-6 text-xs text-ink-mute">
              No conversations yet.
            </p>
          ) : (
            grouped.map((group) => (
              <div key={group.label} className="mb-3">
                <p className="px-3 pb-1 pt-2 text-[11px] font-display font-semibold uppercase tracking-wider text-ink-mute">
                  {group.label}
                </p>
                <ul className="space-y-0.5">
                  {group.sessions.map((s) => (
                    <li key={s.id}>
                      <button
                        type="button"
                        className={cn(
                          "w-full text-left rounded-md px-3 py-2 text-sm truncate transition-colors",
                          s.id === sessionId
                            ? "bg-bg-raised text-ink"
                            : "text-ink-dim hover:bg-bg-raised/60 hover:text-ink",
                        )}
                        title={s.summary ?? "Untitled chat"}
                      >
                        {sessionTitle(s)}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>

        {/* Account chip pinned bottom — mirrors the screenshot's avatar. */}
        <div className="border-t border-border px-3 py-3 flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center font-display font-bold text-xs shrink-0">
            {initials}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-display font-semibold truncate">
              {user?.username ?? "Operator"}
            </p>
            <p className="text-[10px] text-ink-mute truncate">
              {user?.email ?? "local"}
            </p>
          </div>
        </div>
      </aside>

      {/* ===========================================================
       *  Main chat column — model picker bar, message list / empty
       *  state, and bottom composer.
       *  ========================================================= */}
      <section className="flex flex-1 min-w-0 flex-col">
        {/* Top bar */}
        <div className="h-14 shrink-0 flex items-center justify-between px-4 md:px-6 border-b border-border bg-bg-base/80 backdrop-blur">
          <div ref={modelRef} className="relative">
            <button
              type="button"
              onClick={() => setModelOpen((v) => !v)}
              className="flex items-center gap-1.5 rounded-md px-2 py-1 hover:bg-bg-raised transition-colors"
            >
              <span className="font-display font-semibold text-sm text-ink">
                {model.id === "auto" ? "Select a model" : model.label}
              </span>
              <span
                className="material-symbols-outlined text-ink-mute"
                style={{ fontSize: "18px" }}
              >
                expand_more
              </span>
              <span
                className="material-symbols-outlined text-ink-mute ml-1"
                style={{ fontSize: "18px" }}
              >
                add
              </span>
            </button>
            <p className="ml-2 text-[10px] text-ink-mute">
              {model.id === "auto" ? "Set as default" : model.hint}
            </p>

            {modelOpen && (
              <div className="absolute z-30 mt-2 w-64 rounded-lg border border-border bg-bg-surface shadow-sahara overflow-hidden">
                {MODELS.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => {
                      setModel(m);
                      setModelOpen(false);
                    }}
                    className={cn(
                      "w-full text-left px-3 py-2 hover:bg-bg-raised transition-colors flex flex-col",
                      model.id === m.id && "bg-bg-raised",
                    )}
                  >
                    <span className="text-sm font-display font-semibold text-ink">
                      {m.label}
                    </span>
                    <span className="text-[11px] text-ink-mute">{m.hint}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <span className="hidden sm:inline-flex items-center gap-1.5 text-[11px] text-ink-mute font-mono">
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  wsTone,
                  status === "open" && "animate-pulseDot",
                )}
              />
              {wsLabel}
            </span>
            <button
              type="button"
              className="p-2 rounded-md text-ink-mute hover:bg-bg-raised hover:text-primary transition-colors"
              title="Settings"
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: "20px" }}
              >
                tune
              </span>
            </button>
            <div className="w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center font-display font-bold text-xs shadow-sahara">
              {initials}
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 min-h-0 overflow-y-auto scroll-thin">
          {isEmpty ? (
            <EmptyHero
              greeting={greetingName}
              onPick={(prompt) => {
                setDraft(prompt);
                textareaRef.current?.focus();
              }}
            />
          ) : (
            <div
              ref={scrollRef}
              className="mx-auto max-w-3xl px-4 md:px-6 py-6 space-y-5"
            >
              {messages.map((m) => (
                <Bubble key={m.id} message={m} />
              ))}
              {streaming && !streamRef.current && (
                <div className="flex items-center gap-2 text-ink-mute text-xs px-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulseDot" />
                  Thinking…
                </div>
              )}
            </div>
          )}
        </div>

        {/* Composer */}
        <div className="shrink-0 px-4 md:px-6 pb-6 pt-2 bg-gradient-to-t from-bg-base via-bg-base to-transparent">
          <form
            onSubmit={handleSubmit}
            className="mx-auto max-w-3xl rounded-2xl border border-border bg-bg-surface shadow-sahara focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/15 transition-all"
          >
            <div className="flex items-end gap-2 px-3 py-2.5">
              <button
                type="button"
                className="shrink-0 w-8 h-8 rounded-full bg-bg-raised text-ink-dim flex items-center justify-center hover:text-primary hover:bg-primary/10 transition-colors"
                title="Attach"
              >
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "18px" }}
                >
                  add
                </span>
              </button>

              <textarea
                ref={textareaRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKey}
                placeholder={
                  status === "open"
                    ? "Send a Message"
                    : "Connecting WebSocket…"
                }
                disabled={status !== "open"}
                rows={1}
                className="flex-1 resize-none bg-transparent text-sm text-ink placeholder:text-ink-mute focus:outline-none py-1.5 max-h-40 scroll-thin"
              />

              <button
                type="submit"
                disabled={
                  status !== "open" || !draft.trim() || streaming
                }
                className={cn(
                  "shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-all",
                  draft.trim() && status === "open" && !streaming
                    ? "bg-tertiary text-white hover:opacity-90 shadow-[0_0_14px_var(--tertiary-glow)]"
                    : "bg-bg-raised text-ink-mute cursor-not-allowed",
                )}
                title="Send"
              >
                <span
                  className="material-symbols-outlined"
                  style={{ fontSize: "18px" }}
                >
                  arrow_upward
                </span>
              </button>

              <div className="hidden sm:flex items-center gap-1 pl-1 border-l border-border ml-1">
                <button
                  type="button"
                  className="w-8 h-8 rounded-full text-ink-mute hover:text-primary hover:bg-bg-raised transition-colors flex items-center justify-center"
                  title="Voice input"
                >
                  <span
                    className="material-symbols-outlined"
                    style={{ fontSize: "18px" }}
                  >
                    mic
                  </span>
                </button>
                <button
                  type="button"
                  className="w-8 h-8 rounded-full text-ink-mute hover:text-primary hover:bg-bg-raised transition-colors flex items-center justify-center"
                  title="Voice mode"
                >
                  <span
                    className="material-symbols-outlined"
                    style={{ fontSize: "18px" }}
                  >
                    headphones
                  </span>
                </button>
              </div>
            </div>
          </form>
          <p className="mx-auto max-w-3xl text-center text-[11px] text-ink-mute mt-2">
            LLMs can make mistakes. Verify important information.
          </p>
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function RailItem({
  icon,
  label,
  asSearch,
  children,
}: {
  icon: string;
  label: string;
  asSearch?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md px-3 py-2 text-sm text-ink-dim",
        !asSearch && "hover:bg-bg-raised hover:text-ink transition-colors cursor-pointer",
      )}
    >
      <span
        className="material-symbols-outlined text-ink-mute shrink-0"
        style={{ fontSize: "18px" }}
      >
        {icon}
      </span>
      {asSearch ? children : <span>{label}</span>}
    </div>
  );
}

function EmptyHero({
  greeting,
  onPick,
}: {
  greeting: string;
  onPick: (prompt: string) => void;
}) {
  return (
    <div className="h-full flex flex-col items-center justify-center px-4 md:px-6 py-10">
      <div className="w-14 h-14 rounded-full bg-ink text-bg-lowest flex items-center justify-center font-display font-bold text-xl shadow-sahara mb-5">
        SC
      </div>
      <h1 className="font-headline text-3xl md:text-4xl text-ink text-center leading-tight">
        Hello, {greeting}
      </h1>
      <p className="font-headline text-2xl md:text-3xl text-ink-dim text-center mt-1">
        How can I help you today?
      </p>

      <div className="mt-8 flex items-center gap-1.5 text-xs font-display uppercase tracking-wider text-primary">
        <span
          className="material-symbols-outlined"
          style={{ fontSize: "14px" }}
        >
          auto_awesome
        </span>
        Suggested
      </div>

      <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 w-full max-w-5xl">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.title}
            type="button"
            onClick={() => onPick(s.prompt)}
            className="group text-left rounded-xl border border-border bg-bg-surface hover:bg-bg-raised hover:border-primary/40 transition-all p-4 flex flex-col gap-2 shadow-sahara"
          >
            <span
              className="material-symbols-outlined text-primary"
              style={{ fontSize: "20px" }}
            >
              {s.icon}
            </span>
            <p className="font-display text-sm font-semibold text-ink leading-snug">
              {s.title}
            </p>
            <p className="text-xs text-ink-dim leading-snug">{s.subtitle}</p>
            <div className="mt-auto pt-2 flex items-center gap-1 text-[10px] font-display uppercase tracking-wider text-ink-mute group-hover:text-primary transition-colors">
              Prompt
              <span
                className="material-symbols-outlined ml-auto"
                style={{ fontSize: "14px" }}
              >
                arrow_upward
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  if (isSystem) {
    return (
      <div className="flex justify-center">
        <pre className="max-w-[85%] whitespace-pre-wrap break-words rounded-md border border-secondary/30 bg-secondary/5 px-3 py-2 text-[11px] font-mono text-secondary">
          {message.content}
        </pre>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-primary text-white px-4 py-2.5 text-sm whitespace-pre-wrap break-words shadow-sahara">
          {message.content}
        </div>
      </div>
    );
  }

  // Assistant — flat layout (no card), avatar + text, ChatGPT-style.
  return (
    <div className="flex gap-3">
      <div className="w-7 h-7 rounded-full bg-ink text-bg-lowest flex items-center justify-center font-display font-bold text-[10px] shrink-0 mt-0.5">
        SC
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-display text-xs font-semibold text-ink">
            Assistant
          </span>
          <span className="text-[10px] text-ink-mute font-mono">
            {formatTime(message.ts)}
          </span>
        </div>
        <div
          className={cn(
            "text-sm text-ink whitespace-pre-wrap break-words leading-relaxed",
            message.pending && "after:inline-block after:ml-1 after:w-1 after:h-4 after:bg-primary after:align-middle after:animate-pulseDot",
          )}
        >
          {message.content}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function sessionTitle(s: Session): string {
  const summary = (s.summary ?? "").trim();
  if (summary) return summary.length > 48 ? `${summary.slice(0, 47)}…` : summary;
  const stamp = new Date(s.started_at);
  if (Number.isNaN(stamp.getTime())) return "Untitled chat";
  return `Chat · ${stamp.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  })}`;
}

interface SessionGroup {
  label: string;
  sessions: Session[];
}

function groupSessionsByDate(sessions: Session[], filter: string): SessionGroup[] {
  const now = new Date();
  const today = startOfDay(now);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);
  const monthAgo = new Date(today);
  monthAgo.setMonth(monthAgo.getMonth() - 1);

  const buckets: Record<string, Session[]> = {};
  const order: string[] = [];

  const push = (label: string, s: Session) => {
    if (!buckets[label]) {
      buckets[label] = [];
      order.push(label);
    }
    buckets[label].push(s);
  };

  const q = filter.trim().toLowerCase();
  for (const s of sessions) {
    if (q && !(s.summary ?? "").toLowerCase().includes(q)) continue;
    const ts = new Date(s.started_at);
    if (Number.isNaN(ts.getTime())) {
      push("Older", s);
      continue;
    }
    if (ts >= today) push("Today", s);
    else if (ts >= yesterday) push("Yesterday", s);
    else if (ts >= weekAgo) push("Previous 7 Days", s);
    else if (ts >= monthAgo) push("Previous 30 Days", s);
    else push(String(ts.getFullYear()), s);
  }

  return order.map((label) => ({ label, sessions: buckets[label]! }));
}

function startOfDay(d: Date): Date {
  const out = new Date(d);
  out.setHours(0, 0, 0, 0);
  return out;
}
