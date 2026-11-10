
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .forms import EmailAuthenticationForm, RegistrationForm, UserProfileForm


def role_home(user):
    if user.role == user.Role.DONOR:
        return redirect("donor_dashboard")
    if user.role in (user.Role.ADMIN, user.Role.STAFF, user.Role.RECEPTIONIST):
        return redirect("reception_dashboard")
    if user.role == user.Role.MEDICAL:
        return redirect("appointment_list")
    if user.role == user.Role.INVENTORY:
        return redirect("inventory")
    return redirect("home")


def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)
            user.role = user.Role.DONOR
            user.save()

            login(request, user)
            messages.success(request, "Your account was created successfully.")
            return role_home(user)
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


def home(request):
    if request.user.is_authenticated:
        if request.user.role == request.user.Role.DONOR:
            return redirect("donor_dashboard")
        if request.user.role in (request.user.Role.ADMIN, request.user.Role.STAFF, request.user.Role.RECEPTIONIST):
            return redirect("reception_dashboard")
        if request.user.role == request.user.Role.MEDICAL:
            return redirect("appointment_list")
    return render(request, "home.html")


@login_required
def profile(request):
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your account profile was updated.")
            return redirect("account_profile")
    else:
        form = UserProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})


@require_GET
@never_cache
def health_check(request):
    """Return readiness without exposing database details."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return HttpResponse("unavailable", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")



def user_login(request):
    if request.method == "POST":
        form = EmailAuthenticationForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, "You have logged in successfully.")
            return role_home(user)
    else:
        form = EmailAuthenticationForm(request)

    return render(request, "accounts/login.html", {"form": form})


@login_required
def user_logout(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "You have logged out.")
        return redirect("home")

    return redirect("home")

