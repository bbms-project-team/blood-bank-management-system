
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required

from .forms import RegistrationForm


def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)
            user.role = user.Role.DONOR
            user.save()

            login(request, user)
            messages.success(request, "Your account was created successfully.")
            return redirect("home")
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


def home(request):
    return render(request, "home.html")



def user_login(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, "You have logged in successfully.")
            return redirect("home")
    else:
        form = AuthenticationForm(request)

    return render(request, "accounts/login.html", {"form": form})


@login_required
def user_logout(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "You have logged out.")
        return redirect("home")

    return redirect("home")

