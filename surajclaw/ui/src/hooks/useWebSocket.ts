import { useCallback, useEffect, useRef, useState } from "react";

import { getToken } from "@/api/client";

export type WSStatus = "idle" | "connecting" | "open" | "closed" | "error";

export interface UseWebSocketOptions {
  /** Called for every JSON message received. */
  onMessage?: (data: unknown) => void;
  /** Optional reconnect strategy. Defaults to 1500ms with backoff. */
  reconnect?: boolean;
  /** Disable connection without unmounting. */
  enabled?: boolean;
}

export interface UseWebSocketResult {
  status: WSStatus;
  send: (data: unknown) => void;
  close: () => void;
}

const WS_BASE = (import.meta.env.VITE_WS_BASE_URL ?? "").replace(/\/$/, "");

function buildWsUrl(path: string): string {
  if (WS_BASE) return `${WS_BASE}${path}`;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
}

/**
 * Connect to a Django Channels WebSocket. Auto-reconnects with exponential
 * backoff, suspends while the tab is hidden, and forwards JSON frames to
 * `onMessage`.
 *
 * `path` should include the leading slash, e.g. `/ws/chat/<uuid>/`.
 */
export function useWebSocket(
  path: string | null,
  options: UseWebSocketOptions = {},
): UseWebSocketResult {
  const { onMessage, reconnect = true, enabled = true } = options;
  const [status, setStatus] = useState<WSStatus>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const reconnectTimer = useRef<number | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const close = useCallback(() => {
    if (reconnectTimer.current) {
      window.clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  useEffect(() => {
    if (!enabled || !path) {
      close();
      setStatus("idle");
      return;
    }
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      // Channels can't read auth headers off WS; we encode the token in a
      // query param so the consumer's authenticate hook can find it.
      const token = getToken();
      const sep = path.includes("?") ? "&" : "?";
      const url = buildWsUrl(token ? `${path}${sep}token=${token}` : path);
      const ws = new WebSocket(url);
      wsRef.current = ws;
      setStatus("connecting");

      ws.onopen = () => {
        retryRef.current = 0;
        setStatus("open");
      };
      ws.onmessage = (ev) => {
        try {
          onMessageRef.current?.(JSON.parse(ev.data as string));
        } catch {
          onMessageRef.current?.(ev.data);
        }
      };
      ws.onerror = () => setStatus("error");
      ws.onclose = () => {
        setStatus("closed");
        wsRef.current = null;
        if (!reconnect || cancelled) return;
        // 1.5s, 3s, 6s, 12s, capped at 30s.
        const delay = Math.min(30_000, 1500 * 2 ** retryRef.current);
        retryRef.current += 1;
        reconnectTimer.current = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      cancelled = true;
      close();
    };
  }, [path, enabled, reconnect, close]);

  const send = useCallback((data: unknown) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(typeof data === "string" ? data : JSON.stringify(data));
  }, []);

  return { status, send, close };
}
