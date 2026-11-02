
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .forms import RegistrationForm, UserProfileForm
from .models import User


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
    context = {}
    if request.user.is_authenticated:
        from datetime import timedelta

        from django.conf import settings
        from django.db.models import Count
        from django.utils import timezone

        from bloodbank_requests.models import BloodRequest, RequestNotification
        from donations.models import BloodUnit, Donation, DonationBooking
        from donors.eligibility import booking_eligibility_error
        from donors.models import DonorProfile

        today = timezone.localdate()
        now = timezone.now()
        role = request.user.role

        if role == User.Role.DONOR:
            profile = DonorProfile.objects.filter(user=request.user).first()
            upcoming_booking = None
            donation_count = 0
            eligibility_error = None
            if profile:
                upcoming_booking = (
                    DonationBooking.objects.filter(
                        donor=profile,
                        slot__starts_at__gt=now,
                    )
                    .select_related("slot")
                    .first()
                )
                donation_count = Donation.objects.filter(
                    donor=profile,
                    accepted=True,
                ).count()
                eligibility_error = booking_eligibility_error(profile)
            context.update({
                "donor_profile": profile,
                "donor_eligibility_error": eligibility_error,
                "donor_donation_count": donation_count,
                "upcoming_booking": upcoming_booking,
            })

        elif role == User.Role.REQUESTER:
            requests = BloodRequest.objects.filter(requester=request.user)
            request_totals = {
                row["status"]: row["total"]
                for row in requests.values("status").annotate(total=Count("pk"))
            }
            context.update({
                "request_totals": request_totals,
                "request_total": sum(request_totals.values()),
                "active_request_total": sum(
                    request_totals.get(status, 0)
                    for status in (
                        BloodRequest.Status.PENDING,
                        BloodRequest.Status.APPROVED,
                        BloodRequest.Status.RESERVED,
                    )
                ),
                "unread_notification_total": RequestNotification.objects.filter(
                    recipient=request.user,
                    read_at__isnull=True,
                ).count(),
                "recent_notifications": RequestNotification.objects.filter(
                    recipient=request.user,
                    read_at__isnull=True,
                ).select_related("request")[:3],
                "requester_available_units": BloodUnit.objects.filter(
                    status="AVAILABLE",
                    expiry_date__gte=today,
                    donation__accepted=True,
                ).count(),
                "recent_requests": requests.order_by("-created_at")[:5],
            })

        elif role in (User.Role.STAFF, User.Role.ADMIN):
            request_totals = {
                row["status"]: row["total"]
                for row in BloodRequest.objects.values("status")
                .annotate(total=Count("pk"))
            }
            available_units = BloodUnit.objects.filter(
                status="AVAILABLE",
                expiry_date__gte=today,
                donation__accepted=True,
            )
            expiring_units = BloodUnit.objects.filter(
                status__in=("AVAILABLE", "RESERVED"),
                expiry_date__range=(today, today + timedelta(days=7)),
            )
            context.update({
                "staff_request_totals": request_totals,
                "staff_pending_requests": request_totals.get(
                    BloodRequest.Status.PENDING, 0
                ),
                "staff_available_units": available_units.count(),
                "staff_expiring_units": expiring_units.count(),
                "staff_expired_units": BloodUnit.objects.filter(
                    status__in=("AVAILABLE", "RESERVED"),
                    expiry_date__lt=today,
                ).count(),
                "staff_low_stock_threshold": getattr(
                    settings, "BBMS_LOW_STOCK_THRESHOLD", 5
                ),
                "recent_requests": BloodRequest.objects.select_related(
                    "requester"
                ).order_by("-created_at")[:5],
            })

    return render(request, "home.html", context)


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

