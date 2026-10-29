
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
from bloodbank_requests.audit import record_audit


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
                    expiry_date=(
                        donation.donation_date + timedelta(days=35)
                    ),
                )

                donor = donation.donor
                donor.last_donation_date = donation.donation_date
                donor.save(update_fields=["last_donation_date"])
                record_audit(
                    request.user,
                    "DONATION_RECORDED",
                    "Donation",
                    donation.pk,
                    {"blood_group": donation.blood_group, "component": donation.component},
                )

            messages.success(
                request,
                "Donation recorded and inventory unit created successfully.",
            )
            return redirect("inventory")
    else:
        form = DonationForm()

    return render(request, "donations/record.html", {"form": form})


@role_required(User.Role.REQUESTER, User.Role.STAFF, User.Role.ADMIN)
def inventory(request):
    today = timezone.localdate()

    all_units = (
        BloodUnit.objects
        .select_related("donation", "donation__donor", "donation__donor__user")
        .order_by("-created_at")
    )

    counts = {
        "available": all_units.filter(
            status="AVAILABLE",
            expiry_date__gte=today,
            donation__accepted=True,
        ).count(),
        "reserved": all_units.filter(status="RESERVED").count(),
        "issued": all_units.filter(status="ISSUED").count(),
        "expired": all_units.filter(
            expiry_date__lt=today
        ).count(),
    }

    blood_group = request.GET.get("blood_group", "").strip()
    component = request.GET.get("component", "").strip()
    location = request.GET.get("location", "").strip()
    status = request.GET.get("status", "").strip()

    # Availability search only returns available, unexpired units.
    units = all_units.filter(
        status="AVAILABLE",
        expiry_date__gte=today,
        donation__accepted=True,
    )

    if blood_group:
        units = units.filter(donation__blood_group=blood_group)

    if component:
        units = units.filter(donation__component=component)

    if location:
        units = units.filter(location__icontains=location)

    # The search must only show available units.
    # Other status values are not used to expose unavailable units.

    return render(
        request,
        "donations/inventory.html",
        {
            "units": units,
            "counts": counts,
            "selected_blood_group": blood_group,
            "selected_component": component,
            "selected_location": location,
            "selected_status": status,
            "blood_groups": DonorBloodGroups(),
            "components": Donation.COMPONENTS,
        },
    )


def DonorBloodGroups():
    return DonorProfile.BLOOD_GROUPS
