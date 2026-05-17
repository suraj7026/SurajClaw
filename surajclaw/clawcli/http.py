"""Tiny HTTP helper around the Django REST endpoints.

We use ``httpx`` (already pinned in ``requirements.txt``) and inject the
DRF auth header on every authenticated call. Errors are surfaced as
:class:`ApiError` so callers can render them without a stack trace.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class ApiError(RuntimeError):
    """Raised for any non-2xx response or network failure."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class ApiClient:
    server: str
    token: str | None = None

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        return headers

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.server.rstrip('/')}{path}"

    # ---- low-level ------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                response = client.request(
                    method,
                    self._url(path),
                    headers=self._headers(json_body=json is not None),
                    json=json,
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise ApiError(f"network error: {exc}") from exc
        if response.status_code >= 400:
            detail = _extract_detail(response)
            raise ApiError(detail, status=response.status_code)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=params or None)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json=body or {})

    # ---- high-level helpers --------------------------------------------
    def login(self, username: str, password: str) -> dict[str, Any]:
        return self.post("/api/auth/login/", {"username": username, "password": password})

    def logout(self) -> dict[str, Any]:
        return self.post("/api/auth/logout/")

    def me(self) -> dict[str, Any]:
        return self.get("/api/auth/me/")

    def doctor(self) -> dict[str, Any]:
        return self.get("/api/doctor/")

    def health(self) -> dict[str, Any]:
        return self.get("/api/health/")


def _extract_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text.strip() or response.reason_phrase}"
    if isinstance(body, dict):
        for key in ("detail", "error", "message"):
            value = body.get(key)
            if isinstance(value, str):
                return f"HTTP {response.status_code}: {value}"
        return f"HTTP {response.status_code}: {body}"
    return f"HTTP {response.status_code}: {body}"
