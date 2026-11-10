
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from donors.models import DonorProfile
from bloodbank_requests.models import BloodRequest
from config.domain import BLOOD_GROUPS, COMPONENTS


class Donation(models.Model):
    COMPONENTS = COMPONENTS

    donor = models.ForeignKey(
        DonorProfile,
        on_delete=models.PROTECT,
        related_name="donations",
    )
    booking = models.OneToOneField(
        "DonationBooking", on_delete=models.PROTECT, null=True, blank=True,
        related_name="donation",
    )
    donation_date = models.DateField()
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUPS)
    component = models.CharField(
        max_length=20,
        choices=COMPONENTS,
    )
    volume_ml = models.PositiveIntegerField(default=450)
    accepted = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(blood_group__in=[value for value, _ in BLOOD_GROUPS]),
                name="donation_valid_blood_group",
            ),
            models.CheckConstraint(
                condition=Q(component__in=[value for value, _ in COMPONENTS]),
                name="donation_valid_component",
            ),
            models.CheckConstraint(
                condition=Q(volume_ml__gt=0),
                name="donation_volume_positive",
            ),
        ]

    def __str__(self):
        return f"Donation #{self.pk} - {self.blood_group}"


class DonationSlot(models.Model):
    starts_at = models.DateTimeField()
    location = models.CharField(max_length=150, default="Main Blood Bank")
    capacity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["starts_at"]
        constraints = [
            models.UniqueConstraint(fields=["starts_at", "location"], name="unique_slot_time_per_centre"),
        ]

    def __str__(self):
        return f"{self.starts_at:%Y-%m-%d %H:%M} — {self.location}"


class DonationBooking(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CHECKED_IN = "CHECKED_IN", "Checked in"
        SCREENING = "SCREENING", "Screening"
        ELIGIBLE = "ELIGIBLE", "Eligible"
        DEFERRED = "DEFERRED", "Deferred"
        IN_PROGRESS = "IN_PROGRESS", "Donation in progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        NO_SHOW = "NO_SHOW", "No show"

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    donor = models.ForeignKey(
        DonorProfile,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    slot = models.ForeignKey(
        DonationSlot,
        on_delete=models.PROTECT,
        related_name="booking",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.TextField(blank=True)
    screening_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="scheduled_donation_bookings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slot__starts_at"]

    def __str__(self):
        return f"{self.reference} — {self.donor} — {self.slot}"

    @property
    def is_active(self):
        return self.status not in {self.Status.CANCELLED, self.Status.NO_SHOW, self.Status.COMPLETED, self.Status.DEFERRED}


class AppointmentNotification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="appointment_notifications")
    booking = models.ForeignKey(DonationBooking, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class BloodUnit(models.Model):
    STATUS_CHOICES = [
        ("QUARANTINED", "Awaiting processing and testing"),
        ("AVAILABLE", "Available"),
        ("RESERVED", "Reserved"),
        ("ISSUED", "Issued"),
        ("EXPIRED", "Expired"),
    ]
    PROCESSING_CHOICES = [
        ("PENDING", "Pending processing and testing"),
        ("TESTED", "Tested and cleared"),
        ("FAILED", "Failed testing"),
    ]

    donation = models.OneToOneField(
        Donation,
        on_delete=models.PROTECT,
        related_name="blood_unit",
    )
    reserved_for = models.ForeignKey(
        BloodRequest,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reserved_units",
    )
    reserved_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="issued_blood_units",
    )
    unit_code = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    expiry_date = models.DateField()
    location = models.CharField(
        max_length=150,
        default="Main Blood Bank",
    )
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default="QUARANTINED",
    )
    processing_status = models.CharField(max_length=10, choices=PROCESSING_CHOICES, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=["QUARANTINED", "AVAILABLE", "RESERVED", "ISSUED", "EXPIRED"]
                ),
                name="blood_unit_valid_status",
            ),
            models.CheckConstraint(
                condition=~Q(status="AVAILABLE") | Q(processing_status="TESTED"),
                name="available_unit_tested",
            ),
            models.CheckConstraint(
                condition=~Q(status="QUARANTINED") | Q(processing_status__in=["PENDING", "FAILED"]),
                name="quarantined_unit_not_cleared",
            ),
            models.CheckConstraint(
                condition=~Q(status="RESERVED") | Q(reserved_for__isnull=False),
                name="reserved_unit_has_request",
            ),
            models.CheckConstraint(
                condition=~Q(status="ISSUED") | (
                    Q(reserved_for__isnull=False)
                    & Q(issued_at__isnull=False)
                    & Q(issued_by__isnull=False)
                ),
                name="issued_unit_has_dispatch_record",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.donation_id
            and self.expiry_date
            and self.expiry_date < self.donation.donation_date
        ):
            raise ValidationError({
                "expiry_date": "Expiry date cannot be before the donation date."
            })

    def __str__(self):
        return str(self.unit_code)
