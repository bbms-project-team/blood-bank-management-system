
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        DONOR = "DONOR", "Donor"
        REQUESTER = "REQUESTER", "Requester / Hospital Staff"
        STAFF = "STAFF", "Blood Bank Staff"
        ADMIN = "ADMIN", "Administrator"
        RECEPTIONIST = "RECEPTIONIST", "Receptionist"
        MEDICAL = "MEDICAL", "Medical Staff"
        INVENTORY = "INVENTORY", "Inventory Manager"

    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.DONOR,
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
