
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from config.domain import BLOOD_GROUPS, COMPONENTS


class BloodRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        RESERVED = "RESERVED", "Units reserved"
        ISSUED = "ISSUED", "Issued / dispatched"
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
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUPS)
    component = models.CharField(max_length=20, choices=COMPONENTS)
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

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(units_required__gt=0),
                name="blood_request_positive_unit_count",
            ),
            models.CheckConstraint(
                condition=Q(blood_group__in=[value for value, _ in BLOOD_GROUPS]),
                name="blood_request_valid_blood_group",
            ),
            models.CheckConstraint(
                condition=Q(component__in=[value for value, _ in COMPONENTS]),
                name="blood_request_valid_component",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=["PENDING", "APPROVED", "RESERVED", "ISSUED", "REJECTED"]
                ),
                name="blood_request_valid_status",
            ),
        ]

    def __str__(self):
        return f"Request {self.request_id} - {self.status}"


class RequestNotification(models.Model):
    request = models.ForeignKey(
        BloodRequest,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="request_notifications",
    )
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bbms_audit_events",
    )
    action = models.CharField(max_length=40)
    object_type = models.CharField(max_length=60)
    object_id = models.CharField(max_length=80)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
