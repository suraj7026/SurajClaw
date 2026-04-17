"""Auth endpoints for the dashboard.

Two ways for the frontend to authenticate:

* `POST /api/auth/login/` — username/password -> `{token, user}`. Token is
  the standard DRF `Token` row, used in `Authorization: Token <key>`.
* `POST /api/auth/logout/` — invalidates the current token (if any).
* `GET /api/auth/me/` — returns the authenticated user (or 401).

Login is intentionally `AllowAny`; everything else requires auth.
"""
from __future__ import annotations

from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response


def _user_payload(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request: Request) -> Response:
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    if not username or not password:
        return Response(
            {"detail": "username and password required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        return Response(
            {"detail": "invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": _user_payload(user)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request: Request) -> Response:
    Token.objects.filter(user=request.user).delete()
    return Response({"status": "logged_out"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request: Request) -> Response:
    return Response(_user_payload(request.user))
