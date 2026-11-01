
from django.contrib import admin
from django.urls import path, include
from accounts import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("health/", views.health_check, name="health_check"),
    path("accounts/", include("accounts.urls")),
    path("donors/", include("donors.urls")),
    path("donations/", include("donations.urls")),
    path("blood-requests/", include("bloodbank_requests.urls")),
]
