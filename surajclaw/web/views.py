"""Operator Web UI views.

Server-rendered HTMX dashboard at ``/ui/``. The flagship view is the
Approvals table -- one row per pending ``ApprovalRequest`` with Approve /
Deny buttons. HTMX polls the table partial every 3s, which is more than
fast enough given the approval gate poller's 1.5s cadence on the agent
side. Live push via Channels is out of scope for this iteration; polling
is simpler and works behind any reverse proxy.
"""
from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from approval.models import ApprovalRequest
from chat.auth import is_owner


def _owner_check(request: HttpRequest) -> bool:
    """Reuse the chat allowlist: the WebUI owner is whoever the chat consumer accepts."""
    user = request.user
    if not user.is_authenticated:
        return False
    identifier = user.email or user.username or str(user.pk)
    return is_owner("web", identifier)


def _deny(request: HttpRequest):
    return render(request, "web/denied.html", status=403)


@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    next_url = request.GET.get("next") or request.POST.get("next") or reverse("web-approvals")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            return render(request, "web/login.html", {"error": "invalid credentials", "next": next_url})
        login(request, user)
        return HttpResponseRedirect(next_url)
    return render(request, "web/login.html", {"next": next_url})


def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("web-login")


@login_required(login_url="web-login")
def root(request: HttpRequest) -> HttpResponse:
    return redirect("web-approvals")


@login_required(login_url="web-login")
def approvals(request: HttpRequest) -> HttpResponse:
    if not _owner_check(request):
        return _deny(request)
    return render(request, "web/approvals.html")


@login_required(login_url="web-login")
def approvals_table(request: HttpRequest) -> HttpResponse:
    """HTMX partial: live list of pending requests + recent decided ones."""
    if not _owner_check(request):
        return _deny(request)
    pending = ApprovalRequest.objects.filter(
        status=ApprovalRequest.Status.PENDING,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at")[:50]
    recent = ApprovalRequest.objects.exclude(
        status=ApprovalRequest.Status.PENDING
    ).order_by("-responded_at")[:10]
    return render(
        request,
        "web/_approvals_table.html",
        {"pending": pending, "recent": recent, "now": timezone.now()},
    )


@login_required(login_url="web-login")
@require_http_methods(["POST"])
def approve(request: HttpRequest, request_id) -> HttpResponse:
    return _respond(request, request_id, ApprovalRequest.Status.APPROVED)


@login_required(login_url="web-login")
@require_http_methods(["POST"])
def deny(request: HttpRequest, request_id) -> HttpResponse:
    return _respond(request, request_id, ApprovalRequest.Status.REJECTED)


def _respond(request: HttpRequest, request_id, decision: str) -> HttpResponse:
    if not _owner_check(request):
        return _deny(request)
    try:
        ar = ApprovalRequest.objects.get(pk=request_id)
    except ApprovalRequest.DoesNotExist:
        return HttpResponse("not found", status=404)
    if ar.status != ApprovalRequest.Status.PENDING:
        # Already decided; just re-render the table so the UI is consistent.
        return approvals_table(request)
    ar.status = decision
    ar.responded_by = request.user.email or request.user.username or "web"
    ar.responded_at = timezone.now()
    ar.save(update_fields=["status", "responded_by", "responded_at"])

    from approval.gate import notify_responded

    notify_responded(str(ar.id))
    return approvals_table(request)
