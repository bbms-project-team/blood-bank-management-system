
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
]
