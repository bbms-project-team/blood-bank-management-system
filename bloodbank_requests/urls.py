
from django.urls import path
from . import views

urlpatterns = [
    path("submit/", views.submit_request, name="submit_request"),
    path("my-requests/", views.my_requests, name="my_requests"),
    path(
        "<uuid:request_id>/decide/",
        views.decide_request,
        name="decide_request",
    ),
    path("<uuid:request_id>/reserve/", views.reserve_request, name="reserve_request"),
    path("<uuid:request_id>/issue/", views.issue_request, name="issue_request"),
    path("alerts/", views.alerts, name="alerts"),
    path("reports/", views.reports, name="reports"),
    path("audit/", views.audit_log, name="audit_log"),
]
