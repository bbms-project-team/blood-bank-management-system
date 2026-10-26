
from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import User
from donors.models import DonorProfile
from .forms import DonationForm
from .models import Donation, BloodUnit


@role_required(User.Role.STAFF, User.Role.ADMIN)
def record_donation(request):
    if request.method == "POST":
        form = DonationForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                donation = form.save(commit=False)
                donation.accepted = True
                donation.save()

                BloodUnit.objects.create(
                    donation=donation,
                    expiry_date=donation.donation_date + timedelta(days=35),
                )

                donor = donation.donor
                donor.last_donation_date = donation.donation_date
                donor.save(update_fields=["last_donation_date"])

            messages.success(
                request,
                "Donation recorded and inventory unit created successfully.",
            )
            return redirect("inventory")
    else:
        form = DonationForm()

    return render(request, "donations/record.html", {"form": form})


@role_required(User.Role.STAFF, User.Role.ADMIN)
def inventory(request):
    units = (
        BloodUnit.objects
        .select_related("donation", "donation__donor", "donation__donor__user")
        .order_by("-created_at")
    )

    today = timezone.localdate()
    counts = {
        "available": units.filter(
            status="AVAILABLE", expiry_date__gte=today
        ).count(),
        "reserved": units.filter(status="RESERVED").count(),
        "issued": units.filter(status="ISSUED").count(),
        "expired": units.filter(expiry_date__lt=today).count(),
    }

    return render(
        request,
        "donations/inventory.html",
        {"units": units, "counts": counts},
    )
