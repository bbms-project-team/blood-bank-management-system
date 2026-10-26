
from django.conf import settings
from django.db import models


class DonorProfile(models.Model):
    BLOOD_GROUPS = [
        ("A+", "A+"), ("A-", "A-"),
        ("B+", "B+"), ("B-", "B-"),
        ("AB+", "AB+"), ("AB-", "AB-"),
        ("O+", "O+"), ("O-", "O-"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="donor_profile",
    )
    phone = models.CharField(max_length=15)
    date_of_birth = models.DateField()
    address = models.TextField()
    blood_group = models.CharField(
        max_length=3,
        choices=BLOOD_GROUPS,
    )
    last_donation_date = models.DateField(null=True, blank=True)
    eligibility_notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.blood_group}"
