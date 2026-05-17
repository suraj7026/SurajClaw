"""Root URL configuration for SurajClaw.

The operator surface is the `surajclaw` CLI (see `surajclaw/clawcli/`); HTTP
serves only REST API, webhooks, approval forms, admin, and a tiny JSON info
page at `/` so a stray browser hit gets a useful message instead of a 404.
"""
from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import include, path


def info(_request: HttpRequest) -> JsonResponse:
    """Tiny landing JSON. The real interface is the CLI."""
    return JsonResponse(
        {
            "name": "surajclaw",
            "interface": "cli",
            "docs": "surajclaw chat --help",
            "endpoints": {
                "api": "/api/",
                "webhooks": "/webhooks/",
                "approval": "/approval/",
                "admin": "/admin/",
                "ws_chat": "/ws/chat/<session_uuid>/",
            },
        }
    )


def integrations(request: HttpRequest) -> HttpResponse:
    """Landing page for the Google OAuth callback redirect.

    The OAuth callback at ``/api/google/accounts/callback/`` bounces the
    browser here with ``?google=ok&label=...`` (success) or
    ``?google=error&reason=...`` (failure). We render a minimal HTML page
    so the operator sees a confirmation and knows it's safe to close the
    tab / return to the TUI.
    """
    status = (request.GET.get("google") or "").lower()
    label = request.GET.get("label") or ""
    reason = request.GET.get("reason") or ""
    if status == "ok":
        title, body, color = (
            "Account connected",
            f"<b>{label}</b> is now linked. You can close this tab and return to the TUI.",
            "#16a34a",
        )
    elif status == "error":
        title, body, color = (
            "Connection failed",
            f"Google rejected the flow: <code>{reason}</code>. Re-try from the TUI.",
            "#dc2626",
        )
    else:
        title, body, color = (
            "Integrations",
            "Open the TUI and run <code>/google</code> to manage Workspace accounts.",
            "#6b7280",
        )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title} — SurajClaw</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 540px;
       margin: 4rem auto; padding: 2rem; background: #0a0a0a; color: #e5e5e5; }}
h1 {{ color: {color}; }}
a, code {{ color: #a5b4fc; }}
.box {{ border: 1px solid #262626; padding: 1.5rem; border-radius: 0.5rem; }}
</style></head><body><div class="box"><h1>{title}</h1><p>{body}</p>
<p><a href="/admin/core/session/">View sessions in admin</a> ·
<a href="/admin/">Admin home</a></p></div></body></html>"""
    return HttpResponse(html)


urlpatterns = [
    path("", info, name="root-info"),
    path("integrations", integrations, name="integrations"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("webhooks/", include("webhooks.urls")),
    path("approval/", include("approval.urls")),
    path("ui/", include("web.urls")),
]
