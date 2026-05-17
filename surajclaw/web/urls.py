"""URLs for the operator WebUI."""
from __future__ import annotations

from django.urls import path

from web import views

urlpatterns = [
    path("", views.root, name="web-root"),
    path("login/", views.login_view, name="web-login"),
    path("logout/", views.logout_view, name="web-logout"),
    path("approvals/", views.approvals, name="web-approvals"),
    path("approvals/_table/", views.approvals_table, name="web-approvals-table"),
    path("approvals/<uuid:request_id>/approve/", views.approve, name="web-approve"),
    path("approvals/<uuid:request_id>/deny/", views.deny, name="web-deny"),
]
