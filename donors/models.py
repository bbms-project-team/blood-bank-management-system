
from django.conf import settings
from django.db import models
from django.db.models import Q

from config.domain import BLOOD_GROUPS


class DonorProfile(models.Model):
    BLOOD_GROUPS = BLOOD_GROUPS

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

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(blood_group__in=[value for value, _ in BLOOD_GROUPS]),
                name="donor_profile_valid_blood_group",
            ),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.blood_group}"
