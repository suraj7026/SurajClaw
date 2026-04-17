import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { authApi } from "@/api/endpoints";
import { ApiError, clearToken, getToken, setToken } from "@/api/client";
import type { User } from "@/types/api";

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    loading: true,
    error: null,
  });

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setState({ user: null, loading: false, error: null });
      return;
    }
    try {
      const user = await authApi.me();
      setState({ user, loading: false, error: null });
    } catch (err) {
      // 401 already cleared the token in api client.
      const message = err instanceof Error ? err.message : "auth failed";
      setState({ user: null, loading: false, error: message });
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const { token, user } = await authApi.login(username, password);
      setToken(token);
      setState({ user, loading: false, error: null });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "login failed";
      setState({ user: null, loading: false, error: message });
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // best-effort; we'll still drop the token client-side.
    }
    clearToken();
    setState({ user: null, loading: false, error: null });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, logout, refresh }),
    [state, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
