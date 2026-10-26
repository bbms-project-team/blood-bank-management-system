
import uuid

from django.db import models
from donors.models import DonorProfile


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
    component = models.CharField(max_length=20, choices=COMPONENTS)
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
    unit_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    expiry_date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="AVAILABLE",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.unit_code)
