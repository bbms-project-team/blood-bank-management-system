from django.db import transaction
from django.db.utils import OperationalError
from django.utils import timezone
import time

from donations.models import BloodUnit

from .audit import record_audit
from .models import BloodRequest, RequestNotification


class WorkflowError(Exception):
    """A request or inventory transition cannot be completed."""


def _compatibility_filters(blood_request):
    """Use exact group and component matches until a matrix is approved."""
    return {
        "donation__blood_group": blood_request.blood_group,
        "donation__component": blood_request.component,
    }


@transaction.atomic
def _reserve_request_once(request_id, actor):
    """Reserve compatible units as one all-or-nothing step."""
    blood_request = BloodRequest.objects.select_for_update().get(
        request_id=request_id
    )
    if blood_request.status != BloodRequest.Status.APPROVED:
        raise WorkflowError("Only an approved request can be reserved.")

    today = timezone.localdate()
    compatibility = _compatibility_filters(blood_request)
    candidates = list(
        BloodUnit.objects.select_for_update()
        .filter(
            status="AVAILABLE",
            expiry_date__gte=today,
            donation__accepted=True,
            **compatibility,
        )
        .order_by("expiry_date", "created_at", "pk")[:blood_request.units_required]
    )
    if len(candidates) != blood_request.units_required:
        raise WorkflowError("There are not enough matching, unexpired units.")

    now = timezone.now()
    changed = BloodUnit.objects.filter(
        pk__in=[unit.pk for unit in candidates],
        status="AVAILABLE",
        expiry_date__gte=today,
        donation__accepted=True,
        **compatibility,
    ).update(
        status="RESERVED",
        reserved_for=blood_request,
        reserved_at=now,
    )
    if changed != blood_request.units_required:
        raise WorkflowError("Inventory changed while reserving; please retry.")

    updated = BloodRequest.objects.filter(
        pk=blood_request.pk,
        status=BloodRequest.Status.APPROVED,
    ).update(status=BloodRequest.Status.RESERVED)
    if updated != 1:
        raise WorkflowError("Request status changed while reserving; please retry.")

    record_audit(
        actor,
        "REQUEST_RESERVED",
        "BloodRequest",
        blood_request.request_id,
        {"unit_count": changed},
    )
    RequestNotification.objects.create(
        request=blood_request,
        recipient=blood_request.requester,
        message="Your request has been approved and matching units reserved.",
    )
    return blood_request


def reserve_request(request_id, actor):
    for attempt in range(3):
        try:
            return _reserve_request_once(request_id, actor)
        except OperationalError as exc:
            if attempt == 2:
                raise WorkflowError(
                    "Inventory is busy due to another update; please retry."
                ) from exc
            time.sleep(0.05 * (attempt + 1))


@transaction.atomic
def _issue_request_once(request_id, actor):
    """Issue every unexpired unit reserved for a request atomically."""
    blood_request = BloodRequest.objects.select_for_update().get(
        request_id=request_id
    )
    if blood_request.status != BloodRequest.Status.RESERVED:
        raise WorkflowError("Only a request with reserved units can be issued.")

    today = timezone.localdate()
    compatibility = _compatibility_filters(blood_request)
    units = list(
        BloodUnit.objects.select_for_update().filter(
            reserved_for=blood_request,
            status="RESERVED",
            expiry_date__gte=today,
            donation__accepted=True,
            **compatibility,
        )
    )
    if len(units) != blood_request.units_required:
        raise WorkflowError("The reserved inventory is incomplete or expired.")

    now = timezone.now()
    changed = BloodUnit.objects.filter(
        pk__in=[unit.pk for unit in units],
        reserved_for=blood_request,
        status="RESERVED",
        expiry_date__gte=today,
        donation__accepted=True,
        **compatibility,
    ).update(status="ISSUED", issued_at=now, issued_by=actor)
    if changed != blood_request.units_required:
        raise WorkflowError("Inventory changed while issuing; please retry.")

    updated = BloodRequest.objects.filter(
        pk=blood_request.pk,
        status=BloodRequest.Status.RESERVED,
    ).update(status=BloodRequest.Status.ISSUED)
    if updated != 1:
        raise WorkflowError("Request status changed while issuing; please retry.")

    record_audit(
        actor,
        "REQUEST_ISSUED",
        "BloodRequest",
        blood_request.request_id,
        {
            "unit_count": changed,
            "unit_codes": [str(unit.unit_code) for unit in units],
        },
    )
    RequestNotification.objects.create(
        request=blood_request,
        recipient=blood_request.requester,
        message="Your reserved units have been issued / dispatched.",
    )
    return blood_request


def issue_request(request_id, actor):
    for attempt in range(3):
        try:
            return _issue_request_once(request_id, actor)
        except OperationalError as exc:
            if attempt == 2:
                raise WorkflowError(
                    "Inventory is busy due to another update; please retry."
                ) from exc
            time.sleep(0.05 * (attempt + 1))
