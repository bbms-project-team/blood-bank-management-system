import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.forms import PasswordResetForm
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import User
from bloodbank_requests.audit import record_audit
from bloodbank_requests.models import AuditLog
from donors.forms import ReceptionDonorForm
from donors.models import DonorProfile

from .forms import DonationBookingForm, DonationSlotForm
from .models import AppointmentNotification, BloodUnit, Donation, DonationBooking, DonationSlot

RECEPTION_ROLES = (User.Role.ADMIN, User.Role.STAFF, User.Role.RECEPTIONIST)
MEDICAL_ROLES = RECEPTION_ROLES + (User.Role.MEDICAL,)
ACTIVE = ("SCHEDULED", "CONFIRMED", "CHECKED_IN", "SCREENING", "ELIGIBLE", "IN_PROGRESS")


@role_required(*RECEPTION_ROLES)
def dashboard(request):
    today = timezone.localdate()
    active_bookings = DonationBooking.objects.filter(status__in=ACTIVE)
    units = BloodUnit.objects.select_related("donation")
    upcoming = DonationBooking.objects.filter(
        slot__starts_at__date=today
    ).exclude(status__in=("CANCELLED", "COMPLETED", "NO_SHOW", "DEFERRED")).select_related(
        "donor__user", "slot"
    ).order_by("slot__starts_at")[:8]
    stock_by_group = []
    for code, label in DonorProfile.BLOOD_GROUPS:
        count = units.filter(
            donation__blood_group=code, status="AVAILABLE", processing_status="TESTED",
            expiry_date__gte=today,
        ).count()
        stock_by_group.append({"group": code, "label": label, "count": count})
    context = {
        "donor_count": DonorProfile.objects.count(),
        "appointment_count": DonationBooking.objects.count(),
        "today_count": active_bookings.filter(slot__starts_at__date=today).count(),
        "pending_count": DonationBooking.objects.filter(status="SCHEDULED").count(),
        "completed_count": DonationBooking.objects.filter(status="COMPLETED").count(),
        "cancelled_count": DonationBooking.objects.filter(status__in=("CANCELLED", "NO_SHOW")).count(),
        "unit_count": units.filter(status="AVAILABLE", processing_status="TESTED", expiry_date__gte=today).count(),
        "expiring_units": units.filter(status="AVAILABLE", processing_status="TESTED", expiry_date__gte=today, expiry_date__lte=today + timedelta(days=7)).select_related("donation")[:8],
        "stock_by_group": stock_by_group,
        "recent_donors": DonorProfile.objects.select_related("user").order_by("-pk")[:6],
        "recent_activity": AuditLog.objects.select_related("actor")[:8],
        "today_appointments": upcoming,
    }
    return render(request, "reception/dashboard.html", context)


@role_required(*RECEPTION_ROLES)
def donor_search(request):
    query = request.GET.get("q", "").strip()
    donors = DonorProfile.objects.select_related("user").all()
    if query:
        donors = donors.filter(
            Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query) | Q(phone__icontains=query)
            | Q(user__username__icontains=query) | Q(pk__icontains=query)
        )
    return render(request, "reception/donors.html", {"donors": donors[:100], "query": query})


@role_required(*RECEPTION_ROLES)
def donor_create(request):
    form = ReceptionDonorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        username_base = "".join(ch for ch in data["email"].split("@")[0].lower() if ch.isalnum() or ch in "._-")[:135] or "donor"
        username, suffix = username_base, 1
        while User.objects.filter(username=username).exists():
            username = f"{username_base[:140]}{suffix}"
            suffix += 1
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username, email=data["email"], first_name=data["first_name"],
                    last_name=data["last_name"], role=User.Role.DONOR,
                    password=secrets.token_urlsafe(32),
                )
                donor = DonorProfile.objects.create(
                    user=user, phone=data["phone"], date_of_birth=data["date_of_birth"],
                    address=data["address"], blood_group=data["blood_group"],
                    emergency_contact=data["emergency_contact"], gender=data["gender"],
                )
                record_audit(request.user, "DONOR_REGISTERED", "DonorProfile", donor.pk)
        except IntegrityError:
            form.add_error(None, "A donor with these account details was just added. Search for the donor and try again.")
        else:
            password_form = PasswordResetForm({"email": user.email})
            if password_form.is_valid():
                password_form.save(
                    request=request,
                    use_https=request.is_secure(),
                    email_template_name="accounts/password_reset_email.html",
                )
            messages.success(request, "Donor registered. A password setup link was sent to their email; schedule their visit below.")
            return redirect("schedule_appointment_for_donor", donor_id=donor.pk)
    return render(request, "reception/donor_form.html", {"form": form})


@role_required(*RECEPTION_ROLES)
def donor_detail(request, donor_id):
    donor = get_object_or_404(DonorProfile.objects.select_related("user"), pk=donor_id)
    return render(request, "reception/donor_detail.html", {
        "donor": donor,
        "appointments": donor.bookings.select_related("slot").order_by("-slot__starts_at"),
        "donations": donor.donations.order_by("-donation_date"),
    })


@role_required(*RECEPTION_ROLES)
def donor_edit(request, donor_id):
    donor = get_object_or_404(DonorProfile.objects.select_related("user"), pk=donor_id)
    initial = {
        "first_name": donor.user.first_name,
        "last_name": donor.user.last_name,
        "email": donor.user.email,
        "phone": donor.phone,
        "gender": donor.gender,
        "date_of_birth": donor.date_of_birth,
        "address": donor.address,
        "blood_group": donor.blood_group,
        "emergency_contact": donor.emergency_contact,
    }
    form = ReceptionDonorForm(request.POST or None, donor=donor, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            donor.user.first_name = data["first_name"]
            donor.user.last_name = data["last_name"]
            donor.user.email = data["email"]
            donor.user.save(update_fields=["first_name", "last_name", "email"])
            for field in ("phone", "gender", "date_of_birth", "address", "blood_group", "emergency_contact"):
                setattr(donor, field, data[field])
            donor.save(update_fields=["phone", "gender", "date_of_birth", "address", "blood_group", "emergency_contact"])
            record_audit(request.user, "DONOR_PROFILE_UPDATED", "DonorProfile", donor.pk)
        messages.success(request, "Donor profile updated.")
        return redirect("reception_donor_detail", donor_id=donor.pk)
    return render(request, "reception/donor_form.html", {"form": form, "donor": donor, "editing": True})


@role_required(*(RECEPTION_ROLES + (User.Role.MEDICAL,)))
def appointment_list(request):
    appointments = DonationBooking.objects.select_related("donor__user", "slot")
    date_filter = request.GET.get("date", "").strip()
    status_filter = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    if date_filter:
        appointments = appointments.filter(slot__starts_at__date=date_filter)
    if status_filter in DonationBooking.Status.values:
        appointments = appointments.filter(status=status_filter)
    if query:
        appointments = appointments.filter(
            Q(donor__user__first_name__icontains=query) | Q(donor__user__last_name__icontains=query)
            | Q(donor__phone__icontains=query) | Q(reference__icontains=query)
        )
    return render(request, "reception/appointments.html", {
        "appointments": appointments.order_by("slot__starts_at"), "date_filter": date_filter,
        "status_filter": status_filter, "query": query,
        "statuses": DonationBooking.Status.choices,
    })


def _available_slots():
    return DonationSlot.objects.filter(starts_at__gt=timezone.now()).annotate(
        active_bookings=Count("booking", filter=Q(booking__status__in=ACTIVE))
    ).filter(active_bookings__lt=F("capacity"))


@role_required(*RECEPTION_ROLES)
def schedule_appointment(request, donor_id=None):
    donor = get_object_or_404(DonorProfile.objects.select_related("user"), pk=donor_id) if donor_id else None
    form = DonationBookingForm(request.POST or None)
    form.fields["slot"].queryset = _available_slots()
    if request.method == "POST" and form.is_valid():
        selected_donor = donor or form.cleaned_data.get("donor")
        if not selected_donor:
            form.add_error("donor", "Select a donor.")
        else:
            slot_id = form.cleaned_data["slot"].pk
            try:
                with transaction.atomic():
                    slot = DonationSlot.objects.select_for_update().get(pk=slot_id, starts_at__gt=timezone.now())
                    used = slot.booking.filter(status__in=ACTIVE).count()
                    if used >= slot.capacity:
                        raise ValueError("That slot has reached capacity. Choose another time.")
                    if selected_donor.bookings.filter(
                        slot__starts_at__gt=timezone.now(), status__in=ACTIVE,
                    ).exists():
                        raise ValueError("This donor already has an upcoming appointment. Cancel or reschedule it before booking again.")
                    booking = DonationBooking.objects.create(
                        donor=selected_donor, slot=slot, notes=form.cleaned_data.get("notes", ""),
                        created_by=request.user,
                    )
                    AppointmentNotification.objects.create(
                        recipient=selected_donor.user, booking=booking,
                        message=f"A donation appointment was scheduled for {slot.starts_at:%d %b %Y at %H:%M} at {slot.location}.",
                    )
                    record_audit(request.user, "APPOINTMENT_SCHEDULED", "DonationBooking", booking.pk, {"reference": str(booking.reference)})
            except (DonationSlot.DoesNotExist, ValueError, IntegrityError) as error:
                form.add_error(None, str(error) if str(error) else "That slot is no longer available.")
            else:
                messages.success(request, f"Appointment {booking.reference} scheduled for {selected_donor.user.get_full_name() or selected_donor.user.username}.")
                return redirect("appointment_list")
    return render(request, "reception/schedule.html", {"form": form, "donor": donor})


@role_required(*RECEPTION_ROLES)
def slot_management(request):
    form = DonationSlotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                slot = DonationSlot.objects.create(
                    starts_at=form.cleaned_data["starts_at"],
                    location=form.cleaned_data["location"],
                    capacity=form.cleaned_data["capacity"],
                )
                record_audit(request.user, "DONATION_SLOT_CREATED", "DonationSlot", slot.pk)
        except IntegrityError:
            form.add_error("time", "That slot was just added at this centre. Refresh and choose another time.")
        else:
            messages.success(request, "Donation time slot added. It is now available for scheduling.")
            return redirect("manage_donation_slots")
    slots = DonationSlot.objects.filter(starts_at__gt=timezone.now()).annotate(
        active_bookings=Count("booking", filter=Q(booking__status__in=ACTIVE))
    ).order_by("starts_at", "location")
    return render(request, "reception/slots.html", {"form": form, "slots": slots})


@role_required(*MEDICAL_ROLES)
@require_POST
def appointment_action(request, booking_id):
    booking = get_object_or_404(DonationBooking.objects.select_related("slot", "donor__user"), pk=booking_id)
    action = request.POST.get("action", "")
    allowed = {
        "confirm": ("SCHEDULED", "CONFIRMED"), "check_in": ("CONFIRMED", "CHECKED_IN"),
        "start_screening": ("CHECKED_IN", "SCREENING"), "eligible": ("SCREENING", "ELIGIBLE"),
        "defer": ("SCREENING", "DEFERRED"), "start_donation": ("ELIGIBLE", "IN_PROGRESS"),
        "cancel": ("SCHEDULED", "CANCELLED"),
        "no_show": ("SCHEDULED", "NO_SHOW"),
    }
    if action in {"start_screening", "eligible", "defer", "start_donation"}:
        if request.user.role not in (User.Role.ADMIN, User.Role.STAFF, User.Role.MEDICAL):
            messages.error(request, "Medical staff must record screening and eligibility decisions.")
            return redirect("appointment_list")
        booking.screening_notes = request.POST.get("screening_notes", "")[:2000]
    transition = allowed.get(action)
    if transition and booking.status == transition[0]:
        booking.status = transition[1]
        booking.save(update_fields=["status", "screening_notes", "updated_at"])
        AppointmentNotification.objects.create(
            recipient=booking.donor.user, booking=booking,
            message=f"Your appointment {booking.reference} is now {booking.get_status_display().lower()}.",
        )
        record_audit(request.user, f"APPOINTMENT_{transition[1]}", "DonationBooking", booking.pk)
        messages.success(request, f"Appointment updated to {booking.get_status_display()}.")
    else:
        messages.error(request, "That status change is not available for this appointment.")
    return redirect(request.POST.get("next") or "appointment_list")


@role_required(User.Role.DONOR)
def donor_dashboard(request):
    donor = DonorProfile.objects.filter(user=request.user).first()
    bookings = donor.bookings.select_related("slot").order_by("-slot__starts_at") if donor else DonationBooking.objects.none()
    donations = donor.donations.order_by("-donation_date") if donor else Donation.objects.none()
    upcoming = bookings.filter(slot__starts_at__gte=timezone.now()).exclude(status__in=("CANCELLED", "COMPLETED", "NO_SHOW", "DEFERRED")).order_by("slot__starts_at").first()
    notifications = request.user.appointment_notifications.select_related("booking")[:8]
    unread = request.user.appointment_notifications.filter(read_at__isnull=True).count()
    return render(request, "reception/donor_dashboard.html", {
        "donor": donor, "bookings": bookings, "upcoming": upcoming,
        "donations": donations[:8], "donation_count": donations.filter(accepted=True).count(),
        "unread_notifications": unread, "notifications": notifications,
    })


@role_required(User.Role.ADMIN, User.Role.STAFF, User.Role.MEDICAL, User.Role.INVENTORY)
@require_POST
def process_blood_unit(request, unit_id):
    unit = get_object_or_404(BloodUnit, pk=unit_id)
    result = request.POST.get("result")
    if result == "TESTED" and unit.status == "QUARANTINED":
        unit.processing_status = "TESTED"
        unit.status = "AVAILABLE"
        unit.save(update_fields=["processing_status", "status"])
        action, message = "BLOOD_UNIT_TESTED", "Unit passed processing and testing and is now available."
    elif result == "FAILED" and unit.status == "QUARANTINED":
        unit.processing_status = "FAILED"
        unit.status = "QUARANTINED"
        unit.save(update_fields=["processing_status", "status"])
        action, message = "BLOOD_UNIT_FAILED", "Unit marked as failed; it remains unavailable."
    else:
        messages.error(request, "That unit cannot be updated in its current state.")
        return redirect("inventory")
    record_audit(request.user, action, "BloodUnit", unit.pk)
    messages.success(request, message)
    return redirect("inventory")
