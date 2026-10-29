
import uuid

from django.conf import settings
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


class BloodUnit(models.Model):
    STATUS_CHOICES = [
        ("AVAILABLE", "Available"),
        ("RESERVED", "Reserved"),
        ("ISSUED", "Issued"),
        ("EXPIRED", "Expired"),
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
        max_length=10,
        choices=STATUS_CHOICES,
        default="AVAILABLE",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=["AVAILABLE", "RESERVED", "ISSUED", "EXPIRED"]
                ),
                name="blood_unit_valid_status",
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

    def __str__(self):
        return str(self.unit_code)
