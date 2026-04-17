import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/api/client";

interface UseApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

interface UseApiResult<T> extends UseApiState<T> {
  reload: () => Promise<void>;
  setData: (data: T | null) => void;
}

/**
 * Lightweight data-fetching hook. Re-runs `fetcher` whenever any of `deps`
 * change. Optional `pollMs` polls on an interval (paused when the tab is
 * hidden so we don't burn API quota in the background).
 */
export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: React.DependencyList = [],
  options: { pollMs?: number; immediate?: boolean } = {},
): UseApiResult<T> {
  const { pollMs, immediate = true } = options;
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    error: null,
    loading: immediate,
  });
  const mounted = useRef(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const reload = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const data = await fetcherRef.current();
      if (!mounted.current) return;
      setState({ data, error: null, loading: false });
    } catch (err) {
      if (!mounted.current) return;
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "request failed";
      setState((s) => ({ ...s, error: message, loading: false }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    mounted.current = true;
    if (immediate) void reload();
    return () => {
      mounted.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (!pollMs) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void reload();
      }
    }, pollMs);
    return () => window.clearInterval(id);
  }, [pollMs, reload]);

  const setData = useCallback((data: T | null) => {
    setState((s) => ({ ...s, data }));
  }, []);

  return { ...state, reload, setData };
}
