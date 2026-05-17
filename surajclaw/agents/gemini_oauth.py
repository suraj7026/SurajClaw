"""Google OAuth flow for Gemini Code Assist (consumer / paid subscription).

Lets SurajClaw call Gemini via the cloudcode-pa endpoint using your Google
account's Gemini subscription quota instead of a static ``GEMINI_API_KEY``.
Mirrors what hermes-agent's ``google-gemini-cli`` provider and the official
``gemini-cli`` tool do.

Flow:

1. ``surajclaw_gemini_login()`` opens the user's browser, runs a one-shot
   loopback callback server on a random localhost port, and completes a
   PKCE authorization code exchange against ``oauth2.googleapis.com``.
2. The resulting refresh + access tokens are persisted to
   ``$GOOGLE_TOKEN_DIR/gemini_oauth.json`` (chmod 0o600 on POSIX).
3. ``get_valid_access_token()`` refreshes the access token on expiry
   (with a 60-second skew) using the stored refresh token.
4. ``onboard_project()`` calls Code Assist's ``loadCodeAssist`` /
   ``onboardUser`` endpoints on first use to discover or assign the
   user's billing project id.

PKCE is mandatory; the public client id/secret below are the same ones
shipped by Google's official gemini-cli (desktop OAuth doesn't require
secret-keeping, the secret is just there to identify the client).
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public client credentials -- same as Google's official gemini-cli.
# These are not secret; PKCE provides the actual security. Override via env
# if you've registered your own client.
# ---------------------------------------------------------------------------
_DEFAULT_CLIENT_ID = (
    "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j"
    ".apps.googleusercontent.com"
)
_DEFAULT_CLIENT_SECRET = "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"

OAUTH_SCOPES = " ".join([
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
])

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v1/userinfo"

CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"
CODE_ASSIST_USER_AGENT = "surajclaw (gemini-cli-compat)"

REFRESH_SKEW_SECONDS = 60
TOKEN_TIMEOUT_SECONDS = 30


def _client_id() -> str:
    return os.environ.get("SURAJCLAW_GEMINI_CLIENT_ID") or _DEFAULT_CLIENT_ID


def _client_secret() -> str:
    return os.environ.get("SURAJCLAW_GEMINI_CLIENT_SECRET") or _DEFAULT_CLIENT_SECRET


def _token_path() -> Path:
    base = Path(getattr(settings, "GOOGLE_TOKEN_DIR", "google_tokens"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "gemini_oauth.json"


# ---------------------------------------------------------------------------
# Credential model + on-disk format
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class GeminiCredentials:
    access_token: str
    refresh_token: str
    expires_ms: int
    email: str = ""
    project_id: str = ""

    def is_expired(self, skew: int = REFRESH_SKEW_SECONDS) -> bool:
        if not self.access_token or not self.expires_ms:
            return True
        return (time.time() + max(0, skew)) * 1000 >= self.expires_ms

    @classmethod
    def from_disk(cls, data: dict[str, Any]) -> "GeminiCredentials":
        refresh_field = data.get("refresh") or ""
        # Hermes packs "refresh_token|project_id|managed_project_id". We use
        # the same format for forward compatibility but only consume the
        # first two parts.
        parts = refresh_field.split("|") if "|" in refresh_field else [refresh_field]
        refresh_token = parts[0] if parts else ""
        project_id = parts[1] if len(parts) > 1 else (data.get("project_id") or "")
        return cls(
            access_token=data.get("access") or "",
            refresh_token=refresh_token,
            expires_ms=int(data.get("expires") or 0),
            email=data.get("email") or "",
            project_id=project_id,
        )

    def to_disk(self) -> dict[str, Any]:
        return {
            "refresh": f"{self.refresh_token}|{self.project_id}",
            "access": self.access_token,
            "expires": self.expires_ms,
            "email": self.email,
        }


def load_credentials() -> GeminiCredentials | None:
    path = _token_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("could not read %s: %s", path, exc)
        return None
    return GeminiCredentials.from_disk(data)


def save_credentials(creds: GeminiCredentials) -> None:
    path = _token_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(creds.to_disk(), indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def clear_credentials() -> bool:
    path = _token_path()
    if path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# PKCE login flow
# ---------------------------------------------------------------------------
def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class _CallbackHandler(BaseHTTPRequestHandler):
    """One-shot HTTP handler that captures Google's OAuth redirect."""

    server_state: dict[str, Any] = {}

    def do_GET(self):  # noqa: N802 -- HTTPServer interface
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        state = (params.get("state") or [""])[0]
        code = (params.get("code") or [""])[0]
        err = (params.get("error") or [""])[0]

        if state != self.server_state.get("expected_state"):
            self._reply(400, "state mismatch")
            return
        if err:
            self.server_state["error"] = err
            self._reply(400, f"OAuth error: {err}")
            return
        if not code:
            self._reply(400, "missing code")
            return

        self.server_state["code"] = code
        self._reply(
            200,
            "SurajClaw Gemini login succeeded. You can close this tab.",
        )

    def log_message(self, *args, **kwargs):  # silence default access log
        return

    def _reply(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())


def surajclaw_gemini_login(
    *, open_browser: bool = True, port: int = 0
) -> GeminiCredentials:
    """Run the PKCE auth flow end-to-end. Blocks until the browser callback fires.

    ``port=0`` picks a random free localhost port.
    """
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)

    httpd = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    actual_port = httpd.server_address[1]
    redirect_uri = f"http://127.0.0.1:{actual_port}/"

    _CallbackHandler.server_state = {"expected_state": state}

    auth_url = AUTH_ENDPOINT + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": redirect_uri,
        "scope": OAUTH_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    })

    if open_browser:
        webbrowser.open(auth_url)
    else:
        print("Open this URL in a browser to sign in:\n  " + auth_url)

    print(f"Listening for callback on {redirect_uri} ...")

    server_thread = threading.Thread(target=httpd.handle_request, daemon=True)
    server_thread.start()
    server_thread.join(timeout=300)
    httpd.server_close()

    state_data = _CallbackHandler.server_state
    if "code" not in state_data:
        raise RuntimeError(
            "OAuth callback did not arrive (timeout or error: "
            f"{state_data.get('error', 'unknown')})"
        )

    token_resp = _exchange_code(
        code=state_data["code"],
        verifier=verifier,
        redirect_uri=redirect_uri,
    )

    email = _fetch_userinfo_email(token_resp["access_token"])

    creds = GeminiCredentials(
        access_token=token_resp["access_token"],
        refresh_token=token_resp["refresh_token"],
        expires_ms=_expires_in_to_ms(token_resp.get("expires_in", 3600)),
        email=email,
    )
    save_credentials(creds)
    return creds


def _exchange_code(*, code: str, verifier: str, redirect_uri: str) -> dict[str, Any]:
    data = {
        "code": code,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }
    with httpx.Client(timeout=TOKEN_TIMEOUT_SECONDS) as client:
        r = client.post(TOKEN_ENDPOINT, data=data)
        r.raise_for_status()
        return r.json()


def _expires_in_to_ms(expires_in: int) -> int:
    return int((time.time() + int(expires_in)) * 1000)


def _fetch_userinfo_email(access_token: str) -> str:
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            r.raise_for_status()
            return r.json().get("email", "") or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("userinfo fetch failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Refresh & access
# ---------------------------------------------------------------------------
_refresh_lock = threading.Lock()


def get_valid_access_token(*, force_refresh: bool = False) -> str:
    """Return a non-expired access token, refreshing if needed.

    Raises ``RuntimeError`` if no credentials exist (run ``gemini_login`` first).
    """
    with _refresh_lock:
        creds = load_credentials()
        if creds is None:
            raise RuntimeError(
                "no gemini OAuth credentials. Run: python manage.py gemini_login"
            )
        if not force_refresh and not creds.is_expired():
            return creds.access_token

        refreshed = _refresh(creds.refresh_token)
        creds.access_token = refreshed["access_token"]
        creds.expires_ms = _expires_in_to_ms(refreshed.get("expires_in", 3600))
        if "refresh_token" in refreshed:
            # Google occasionally rotates refresh tokens.
            creds.refresh_token = refreshed["refresh_token"]
        save_credentials(creds)
        return creds.access_token


def _refresh(refresh_token: str) -> dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
    }
    with httpx.Client(timeout=TOKEN_TIMEOUT_SECONDS) as client:
        r = client.post(TOKEN_ENDPOINT, data=data)
    if r.status_code in (400, 401):
        body = r.text
        if "invalid_grant" in body:
            clear_credentials()
            raise RuntimeError(
                "gemini refresh token rejected (invalid_grant). "
                "Run: python manage.py gemini_login"
            )
        r.raise_for_status()
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Code Assist project + tier discovery
# ---------------------------------------------------------------------------
# Order matters: higher-quota tiers come first so we prefer them when the
# user is entitled to multiple. Google has changed the canonical names over
# time; the list below covers what gemini-cli + hermes both check for.
_TIER_PREFERENCE: tuple[str, ...] = (
    "standard-tier",     # Google Cloud paid project (highest)
    "legacy-tier",       # Consumer Google AI Pro / Gemini Advanced ($20/mo)
    "google-one-tier",
    "free-tier",         # Auto-assigned managed project (lowest)
)


def onboard_project(*, force: bool = False) -> str:
    """Resolve (and persist) a Code Assist project id for this account.

    Detects the highest-quota tier Google offers this user (Pro subscribers
    land on ``legacy-tier``; free accounts on ``free-tier``). If the project
    id was previously cached under a lower tier, pass ``force=True`` to
    re-onboard.
    """
    creds = load_credentials()
    if creds is None:
        raise RuntimeError("no gemini credentials; run gemini_login first")
    if creds.project_id and not force:
        return creds.project_id

    override = os.environ.get("SURAJCLAW_GEMINI_PROJECT_ID", "").strip()
    if override:
        creds.project_id = override
        save_credentials(creds)
        return creds.project_id

    project_id = _load_code_assist(creds)
    creds.project_id = project_id
    save_credentials(creds)
    return project_id


def _pick_tier(load_response: dict[str, Any]) -> str:
    """Pick the best tier from a loadCodeAssist response.

    ``SURAJCLAW_GEMINI_TIER`` env var overrides everything.
    """
    forced = os.environ.get("SURAJCLAW_GEMINI_TIER", "").strip()
    if forced:
        return forced

    # ``currentTier`` is what Google has already onboarded the account to.
    current = (load_response.get("currentTier") or {}).get("id") or ""
    allowed_raw = load_response.get("allowedTiers") or []
    allowed_ids: set[str] = set()
    for entry in allowed_raw:
        tid = entry.get("id") if isinstance(entry, dict) else entry
        if tid:
            allowed_ids.add(tid)
    if current:
        allowed_ids.add(current)

    for candidate in _TIER_PREFERENCE:
        if candidate in allowed_ids:
            return candidate
    # If Google offered nothing recognizable, fall back to the most-permissive
    # name we know; if THAT fails the onboardUser call returns 400 and the
    # caller sees a useful error.
    return current or "legacy-tier"


def _load_code_assist(creds: GeminiCredentials) -> str:
    """Hit loadCodeAssist; onboard with the best tier we can detect."""
    headers = {
        "Authorization": f"Bearer {creds.access_token}",
        "Content-Type": "application/json",
        "User-Agent": CODE_ASSIST_USER_AGENT,
    }
    with httpx.Client(timeout=30) as client:
        r = client.post(
            f"{CODE_ASSIST_ENDPOINT}/v1internal:loadCodeAssist",
            headers=headers,
            json={"metadata": {"pluginType": "GEMINI"}},
        )
        body: dict[str, Any] = {}
        if r.status_code == 200:
            body = r.json()
            project = (
                body.get("cloudaicompanionProject")
                or body.get("managedProject")
                or (body.get("currentTier") or {}).get("cloudaicompanionProject")
                or ""
            )
            if project:
                logger.info(
                    "Code Assist: using existing project=%s tier=%s",
                    project,
                    (body.get("currentTier") or {}).get("id"),
                )
                return project
        else:
            logger.warning(
                "loadCodeAssist returned %s: %s", r.status_code, r.text[:300]
            )

        tier_id = _pick_tier(body)
        logger.info("Code Assist: onboarding user with tier=%s", tier_id)
        r2 = client.post(
            f"{CODE_ASSIST_ENDPOINT}/v1internal:onboardUser",
            headers=headers,
            json={
                "tierId": tier_id,
                "metadata": {"pluginType": "GEMINI"},
            },
        )
        if r2.status_code >= 400:
            raise RuntimeError(
                f"onboardUser({tier_id}) failed with {r2.status_code}: "
                f"{r2.text[:300]}"
            )
        op = r2.json()
        project = (
            op.get("response", {}).get("cloudaicompanionProject")
            or op.get("response", {}).get("project")
            or op.get("metadata", {}).get("cloudaicompanionProject")
            or ""
        )
        if project:
            return project
    raise RuntimeError(
        "Could not discover a Code Assist project id automatically. "
        "Set SURAJCLAW_GEMINI_PROJECT_ID to your GCP project id, or "
        "SURAJCLAW_GEMINI_TIER to override tier detection."
    )
