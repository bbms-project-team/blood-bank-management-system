
from django.contrib import admin
from django.urls import path, include, reverse_lazy
from django.contrib.auth import views as auth_views
from accounts import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("health/", views.health_check, name="health_check"),
    path("accounts/", include("accounts.urls")),
    path("accounts/password-reset/", auth_views.PasswordResetView.as_view(template_name="accounts/password_reset_form.html", email_template_name="accounts/password_reset_email.html", success_url=reverse_lazy("password_reset_done")), name="password_reset"),
    path("accounts/password-reset/sent/", auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("accounts/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html", success_url=reverse_lazy("password_reset_complete")), name="password_reset_confirm"),
    path("accounts/reset/complete/", auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),
    path("donors/", include("donors.urls")),
    path("donations/", include("donations.urls")),
    path("reception/", include("donations.reception_urls")),
    path("blood-requests/", include("bloodbank_requests.urls")),
]
