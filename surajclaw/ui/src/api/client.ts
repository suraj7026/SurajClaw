// Thin fetch wrapper. Everything goes through here so we get one place to
// add the auth token, normalize errors, and (later) request cancellation.

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const TOKEN_KEY = "surajclaw_token";

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(API_BASE + path, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null) continue;
      url.searchParams.set(k, String(v));
    }
  }
  // Strip the origin if we're talking to the same host (lets the dev proxy work).
  if (url.origin === window.location.origin) {
    return url.pathname + url.search;
  }
  return url.toString();
}

export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, query, headers, ...rest } = options;
  const token = getToken();
  const finalHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(headers as Record<string, string> | undefined),
  };
  if (body !== undefined && !(body instanceof FormData)) {
    finalHeaders["Content-Type"] = "application/json";
  }
  if (token) {
    finalHeaders.Authorization = `Token ${token}`;
  }

  const resp = await fetch(buildUrl(path, query), {
    ...rest,
    headers: finalHeaders,
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
    credentials: "include",
  });

  // 204 = no content; nothing to parse.
  if (resp.status === 204) {
    return undefined as T;
  }

  let payload: unknown = null;
  const contentType = resp.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      payload = await resp.json();
    } catch {
      payload = null;
    }
  } else {
    payload = await resp.text();
  }

  if (!resp.ok) {
    const message =
      (payload as { detail?: string })?.detail ??
      (typeof payload === "string" ? payload : `HTTP ${resp.status}`);
    if (resp.status === 401) {
      // Drop the stale token so the next render bounces to /login.
      clearToken();
    }
    throw new ApiError(resp.status, message, payload);
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "body" | "method">) =>
    apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "body" | "method">) =>
    apiFetch<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "body" | "method">) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "body" | "method">) =>
    apiFetch<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, "body" | "method">) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
};
