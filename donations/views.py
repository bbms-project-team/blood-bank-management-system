
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import User
from donors.models import DonorProfile
from donors.eligibility import booking_eligibility_error
from .forms import DonationForm, DonationBookingForm
from .models import AppointmentNotification, Donation, BloodUnit, DonationSlot, DonationBooking
from bloodbank_requests.audit import record_audit


@role_required(User.Role.DONOR)
def book_donation(request):
    donor = DonorProfile.objects.filter(user=request.user).first()
    if donor is None:
        messages.info(request, "Complete your donor profile before booking a slot.")
        return redirect("my_profile")
    now = timezone.now()
    eligibility_error = booking_eligibility_error(donor)
    current_booking = donor.bookings.filter(
        slot__starts_at__gt=now,
        status__in=["SCHEDULED", "CONFIRMED", "CHECKED_IN", "SCREENING", "ELIGIBLE", "IN_PROGRESS"],
    ).first()
    form = DonationBookingForm(
        request.POST if request.method == "POST" else None
    )
    form.fields.pop("donor", None)

    if request.method == "POST":
        if eligibility_error:
            form.add_error(None, eligibility_error)
        elif current_booking:
            form.add_error(None, "You already have an upcoming donation booking.")
        elif form.is_valid():
            try:
                with transaction.atomic():
                    donor = DonorProfile.objects.select_for_update().get(pk=donor.pk)
                    current_error = booking_eligibility_error(donor)
                    if current_error:
                        raise ValidationError(current_error)
                    if donor.bookings.filter(
                        slot__starts_at__gt=timezone.now(),
                        status__in=["SCHEDULED", "CONFIRMED", "CHECKED_IN", "SCREENING", "ELIGIBLE", "IN_PROGRESS"],
                    ).exists():
                        raise ValidationError(
                            "You already have an upcoming donation booking."
                        )
                    slot = DonationSlot.objects.select_for_update().get(
                        pk=form.cleaned_data["slot"].pk,
                        starts_at__gt=timezone.now(),
                    )
                    active = slot.booking.filter(status__in=["SCHEDULED", "CONFIRMED", "CHECKED_IN", "SCREENING", "ELIGIBLE", "IN_PROGRESS"]).count()
                    if active >= slot.capacity:
                        raise ValidationError("That slot has reached capacity. Please choose another.")
                    DonationBooking.objects.create(donor=donor, slot=slot)
            except ValidationError as error:
                form.add_error(None, error.message)
            except (DonationSlot.DoesNotExist, IntegrityError):
                form.add_error("slot", "That slot was just booked. Please choose another.")
            else:
                messages.success(request, "Your donation slot has been booked.")
                return redirect("book_donation")

    current_booking = donor.bookings.filter(
        slot__starts_at__gt=now,
        status__in=["SCHEDULED", "CONFIRMED", "CHECKED_IN", "SCREENING", "ELIGIBLE", "IN_PROGRESS"],
    ).first()
    return render(
        request,
        "donations/book.html",
        {
            "form": form,
            "eligibility_error": eligibility_error,
            "current_booking": current_booking,
        },
    )


@role_required(User.Role.STAFF, User.Role.ADMIN, User.Role.MEDICAL)
def record_donation(request):
    if request.method == "POST":
        form = DonationForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                donation = form.save(commit=False)
                donation.booking = form.cleaned_data["booking"]
                donation.donor = donation.booking.donor
                donation.blood_group = donation.donor.blood_group
                donation.accepted = True
                donation.save()

                BloodUnit.objects.create(
                    donation=donation,
                    expiry_date=(
                        donation.donation_date + timedelta(days=35)
                    ),
                    status="QUARANTINED",
                    processing_status="PENDING",
                )

                donor = donation.donor
                donor.last_donation_date = donation.donation_date
                donor.save(update_fields=["last_donation_date"])
                donation.booking.status = "COMPLETED"
                donation.booking.save(update_fields=["status", "updated_at"])
                AppointmentNotification.objects.create(
                    recipient=donor.user, booking=donation.booking,
                    message=f"Your donation on {donation.donation_date} was recorded as completed. The blood unit is awaiting testing.",
                )
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
        form = DonationForm(initial={"booking": request.GET.get("booking")})

    return render(request, "donations/record.html", {"form": form})


@role_required(User.Role.REQUESTER, User.Role.STAFF, User.Role.ADMIN, User.Role.INVENTORY)
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
        "quarantined": all_units.filter(status="QUARANTINED").count(),
    }

    blood_group = request.GET.get("blood_group", "").strip()
    component = request.GET.get("component", "").strip()
    location = request.GET.get("location", "").strip()
    status = request.GET.get("status", "").strip()

    # Availability search only returns available, unexpired units.
    units = all_units.filter(
        status="AVAILABLE",
        processing_status="TESTED",
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
        "quarantined_units": all_units.filter(status="QUARANTINED").select_related("donation", "donation__donor", "donation__donor__user"),
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
