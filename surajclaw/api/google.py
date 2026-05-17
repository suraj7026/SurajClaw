"""Google account management API.

Surfaces ``core.google_accounts`` to the dashboard so an operator can:

* List which Google accounts have valid OAuth tokens on disk.
* Kick off a browser-based OAuth flow to add a new account (web flow with
  redirect, not the loopback flow used by ``manage.py google_oauth_login``).
* Disconnect (delete the token file) for an existing account.

The OAuth callback target must be registered in the Google Cloud Console
as an authorized redirect URI for the OAuth client. We default to
``{request scheme}://{request host}/api/google/accounts/callback/`` so it
matches whatever host the dashboard is being served from.
"""
from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseRedirect
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from api.serializers import GoogleAccountSerializer
from core.google_accounts import (
    LABEL_RE,
    GoogleAccount,
    list_accounts,
    path_for,
    validate_label,
)

logger = logging.getLogger(__name__)

# Cache key prefix for OAuth state -> account label mapping. State tokens
# are short-lived (10 min) and consumed once.
_STATE_CACHE_PREFIX = "google_oauth_state:"
_STATE_TTL_SECONDS = 600

# Same scope set as the management command. Keep these in sync.
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/contacts.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


def _account_payload(account: GoogleAccount) -> dict:
    """Read a token file and surface dashboard-friendly metadata.

    We do *not* return the token itself — only the email + granted scopes
    so the UI can show "connected as you@example.com (8 scopes)".
    """
    payload: dict = {
        "label": account.label,
        "token_path": str(account.token_path),
        "email": "",
        "scopes": [],
        "expires_at": None,
    }
    try:
        data = json.loads(account.token_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not read token %s: %s", account.token_path, exc)
        return payload

    payload["scopes"] = data.get("scopes") or []
    # `client_email` shows up on service accounts; ID-token email is more
    # reliable for end-user OAuth, but the management command logs it
    # separately so we fall back through several plausible keys.
    payload["email"] = (
        data.get("account")
        or data.get("client_email")
        or data.get("email")
        or ""
    )
    payload["expires_at"] = data.get("expiry") or data.get("expires_at")
    return payload


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_google_accounts(_request: Request) -> Response:
    """List all Google accounts with token files on disk."""
    accounts = [_account_payload(a) for a in list_accounts()]
    return Response(GoogleAccountSerializer(accounts, many=True).data)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def disconnect_google_account(_request: Request, label: str) -> Response:
    """Delete the token file for ``label``. Idempotent."""
    try:
        validate_label(label)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    token_path: Path = path_for(label)
    if token_path.exists():
        try:
            token_path.unlink()
        except OSError as exc:
            return Response(
                {"detail": f"could not delete: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    return Response({"status": "disconnected", "label": label})


def _redirect_uri(request: Request) -> str:
    """Compute the OAuth callback URL the way Google sees it.

    Must match an Authorized redirect URI on the OAuth client in the GCP
    console. We let Django build the absolute URI from the request so it
    works behind nginx/host header rewrites.
    """
    return request.build_absolute_uri("/api/google/accounts/callback/")


def _build_flow(redirect_uri: str, state: str | None = None):
    """Construct an InstalledAppFlow configured for the web redirect flow."""
    from google_auth_oauthlib.flow import Flow  # type: ignore[import-not-found]

    secrets_path = Path(settings.GOOGLE_CLIENT_SECRETS_PATH)
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"Client secrets not found at {secrets_path}. "
            "Set GOOGLE_CLIENT_SECRETS_PATH or upload your OAuth client JSON."
        )
    flow = Flow.from_client_secrets_file(
        str(secrets_path),
        scopes=DEFAULT_SCOPES,
        redirect_uri=redirect_uri,
        state=state,
    )
    return flow


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def connect_google_account(request: Request, label: str) -> Response:
    """Begin a Google OAuth flow for the given account label.

    Returns ``{auth_url, state}``; the frontend redirects the browser to
    ``auth_url``. After consent, Google redirects back to
    ``/api/google/accounts/callback/?code=...&state=...`` which writes the
    token file and redirects to the integrations page.
    """
    try:
        validate_label(label)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    state = secrets.token_urlsafe(24)

    redirect_uri = _redirect_uri(request)
    try:
        flow = _build_flow(redirect_uri=redirect_uri, state=state)
    except FileNotFoundError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:  # noqa: BLE001 -- surface as 500 with detail
        logger.exception("google flow init failed")
        return Response(
            {"detail": f"flow init failed: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    # Modern google-auth-oauthlib enables PKCE by default: `authorization_url`
    # generates a `code_verifier`, sends a derived `code_challenge` to Google,
    # and stores the verifier on the flow instance. Because the callback is a
    # separate request that builds a fresh Flow, we must persist the verifier
    # alongside the state token and restore it before `fetch_token`, or
    # Google replies `invalid_grant: Missing code verifier`.
    cache.set(
        _STATE_CACHE_PREFIX + state,
        {"label": label, "code_verifier": getattr(flow, "code_verifier", None)},
        timeout=_STATE_TTL_SECONDS,
    )
    return Response({"auth_url": auth_url, "state": state, "label": label})


@api_view(["GET"])
@permission_classes([AllowAny])
def google_oauth_callback(request: Request):
    """OAuth redirect target. Exchanges code -> token, writes to disk.

    Public on purpose because Google's redirect won't carry our auth header.
    Security comes from the cached `state` token: if we don't have an
    in-memory mapping of `state -> label`, we reject.
    """
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    error = request.query_params.get("error", "")

    if error:
        return _redirect_to_integrations(error=error)
    if not state or not code:
        return _redirect_to_integrations(error="missing_state_or_code")

    cached = cache.get(_STATE_CACHE_PREFIX + state)
    if not cached:
        return _redirect_to_integrations(error="invalid_or_expired_state")
    cache.delete(_STATE_CACHE_PREFIX + state)

    # Tolerate the legacy cache shape (raw label string) so old in-flight
    # flows from before the PKCE fix don't 500.
    if isinstance(cached, str):
        label, code_verifier = cached, None
    else:
        label = cached.get("label", "")
        code_verifier = cached.get("code_verifier")

    if not label or not LABEL_RE.match(label):
        return _redirect_to_integrations(error="bad_label")

    redirect_uri = _redirect_uri(request)
    try:
        flow = _build_flow(redirect_uri=redirect_uri, state=state)
        # Restore the PKCE verifier captured during the connect step.
        if code_verifier:
            flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        creds = flow.credentials
    except Exception as exc:  # noqa: BLE001
        logger.exception("google token exchange failed")
        return _redirect_to_integrations(error=f"token_exchange_failed:{exc}")

    token_path = path_for(label)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    logger.info("wrote token for account %s -> %s", label, token_path)
    return _redirect_to_integrations(label=label)


def _redirect_to_integrations(
    label: str | None = None, error: str | None = None
) -> HttpResponse:
    """Return a self-closing HTML page summarising the OAuth result.

    Replaces the previous redirect-to-``/integrations`` flow because the
    TUI doesn't host a dashboard page there — we just want the browser
    tab to confirm success/failure and close itself so the operator
    returns to the terminal.
    """
    if error:
        title = "Connection failed"
        color = "#dc2626"
        body = (
            f"Google rejected the flow: <code>{error}</code>. Re-try from the "
            "TUI with <code>/google</code>."
        )
        ok = False
    else:
        title = "Account connected"
        color = "#16a34a"
        body = (
            f"<b>{label or ''}</b> is now linked. This tab will close in a "
            "moment — return to the TUI."
        )
        ok = True

    # We try window.close() first. Modern browsers only honour it for tabs
    # opened by JavaScript (window.open) — for tabs opened by webbrowser.open
    # most browsers refuse, but Chrome+Edge often allow it for tabs that
    # ARE the only page in that tab's history. Either way, we show clear
    # fallback text so the operator can close manually.
    auto_close_ms = 1500 if ok else 0
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title} — SurajClaw</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif;
       background: #0a0a0a; color: #e5e5e5;
       display: flex; align-items: center; justify-content: center;
       height: 100vh; margin: 0; padding: 2rem; }}
.box {{ max-width: 480px; padding: 2rem;
       border: 1px solid #262626; border-radius: 0.75rem; background: #111; }}
h1 {{ color: {color}; margin: 0 0 1rem 0; }}
p {{ line-height: 1.55; margin: 0.5rem 0; }}
.hint {{ color: #737373; font-size: 0.875rem; }}
code {{ background: #1f1f1f; padding: 0.1rem 0.4rem; border-radius: 0.25rem; }}
button {{ background: #1f1f1f; color: #e5e5e5; border: 1px solid #404040;
         padding: 0.5rem 1rem; border-radius: 0.375rem; cursor: pointer;
         margin-top: 1rem; }}
button:hover {{ background: #262626; }}
</style></head>
<body><div class="box">
<h1>{title}</h1>
<p>{body}</p>
<p class="hint">If this tab doesn't close on its own, just close it manually
(⌘W on macOS / Ctrl+W on Windows/Linux).</p>
<button onclick="window.close()">Close tab</button>
</div>
<script>
  // Try to auto-close. Browsers may refuse for tabs not opened via
  // window.open() — that's why we also show the manual instructions.
  if ({str(auto_close_ms).lower()} > 0) {{
    setTimeout(function() {{
      try {{ window.close(); }} catch(e) {{}}
    }}, {auto_close_ms});
  }}
</script>
</body></html>"""
    return HttpResponse(html)
