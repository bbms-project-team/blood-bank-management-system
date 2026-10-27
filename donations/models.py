
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from donors.models import DonorProfile
from bloodbank_requests.models import BloodRequest


class Donation(models.Model):
    COMPONENTS = [
        ("WHOLE_BLOOD", "Whole Blood"),
        ("RED_CELLS", "Red Blood Cells"),
        ("PLASMA", "Plasma"),
        ("PLATELETS", "Platelets"),
    ]

    donor = models.ForeignKey(
        DonorProfile,
        on_delete=models.PROTECT,
        related_name="donations",
    )
    donation_date = models.DateField()
    blood_group = models.CharField(max_length=3)
    component = models.CharField(
        max_length=20,
        choices=COMPONENTS,
    )
    volume_ml = models.PositiveIntegerField(default=450)
    accepted = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
