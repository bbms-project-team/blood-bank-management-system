
import uuid

from django.conf import settings
from django.db import models


class BloodRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    request_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="blood_requests",
    )
    patient_name = models.CharField(max_length=150)
    hospital_name = models.CharField(max_length=200)
    blood_group = models.CharField(max_length=3)
    component = models.CharField(max_length=20)
    units_required = models.PositiveIntegerField()
    reason = models.TextField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    decision_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="blood_request_decisions",
        null=True,
        blank=True,
    )
    decision_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Request {self.request_id} - {self.status}"
