"""Approval gate views: user confirms or rejects a pending destructive tool call."""
from __future__ import annotations

from django.http import HttpRequest
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

# Note: ApprovalRequest is defined in approval/models.py (Phase 5). Until the
# model is migrated this view will lazy-import to avoid a hard dependency at
# URL-resolve time.


@api_view(["POST"])
def respond(request: HttpRequest, request_id: str) -> Response:
    from approval.models import ApprovalRequest

    decision = request.data.get("decision", "").lower()  # type: ignore[attr-defined]
    responder = str(request.data.get("responded_by", "web"))  # type: ignore[attr-defined]

    if decision not in {"approved", "rejected"}:
        return Response(
            {"detail": "decision must be 'approved' or 'rejected'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        ar = ApprovalRequest.objects.get(pk=request_id)
    except ApprovalRequest.DoesNotExist:
        return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)

    if ar.status != ApprovalRequest.Status.PENDING:
        return Response(
            {"detail": f"already {ar.status}"},
            status=status.HTTP_409_CONFLICT,
        )

    ar.status = decision
    ar.responded_by = responder
    ar.responded_at = timezone.now()
    ar.save(update_fields=["status", "responded_by", "responded_at"])

    # Notify any waiting agent thread (see approval.gate for wait_for_approval).
    from approval.gate import notify_responded

    notify_responded(str(ar.id))

    return Response({"id": str(ar.id), "status": ar.status})
