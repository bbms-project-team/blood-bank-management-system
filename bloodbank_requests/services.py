
import logging
import time

from django.db import transaction
from django.db.utils import OperationalError
from django.utils import timezone

from donations.models import BloodUnit

from .audit import record_audit
from .compatibility import is_blood_compatible
from .models import BloodRequest, RequestNotification


logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    """A request or inventory transition cannot be completed."""


@transaction.atomic
def _reserve_request_once(request_id, actor):
    """Reserve compatible blood units atomically."""

    blood_request = BloodRequest.objects.select_for_update().get(
        request_id=request_id
    )

    if blood_request.status != BloodRequest.Status.APPROVED:
        raise WorkflowError(
            "Only an approved request can be reserved."
        )

    today = timezone.localdate()

    candidates = list(
        BloodUnit.objects.select_for_update()
        .filter(
            status="AVAILABLE",
            expiry_date__gte=today,
            donation__accepted=True,
            donation__component=blood_request.component,
        )
        .order_by("expiry_date", "created_at", "pk")
    )

    compatible_units = [
        unit for unit in candidates
        if is_blood_compatible(
            unit.donation.blood_group,
            blood_request.blood_group,
            blood_request.component,
        )
    ]

    selected_units = compatible_units[:blood_request.units_required]

    if len(selected_units) != blood_request.units_required:
        raise WorkflowError(
            "There are not enough compatible, unexpired blood units."
        )

    unit_ids = [unit.pk for unit in selected_units]
    now = timezone.now()

    changed = BloodUnit.objects.filter(
        pk__in=unit_ids,
        status="AVAILABLE",
        expiry_date__gte=today,
        donation__accepted=True,
        donation__component=blood_request.component,
    ).update(
        status="RESERVED",
        reserved_for=blood_request,
        reserved_at=now,
    )

    if changed != blood_request.units_required:
        raise WorkflowError(
            "Inventory changed while reserving; please retry."
        )

    updated = BloodRequest.objects.filter(
        pk=blood_request.pk,
        status=BloodRequest.Status.APPROVED,
    ).update(
        status=BloodRequest.Status.RESERVED
    )

    if updated != 1:
        raise WorkflowError(
            "Request status changed while reserving; please retry."
        )

    record_audit(
        actor,
        "REQUEST_RESERVED",
        "BloodRequest",
        blood_request.request_id,
        {
            "unit_count": changed,
            "blood_group": blood_request.blood_group,
            "component": blood_request.component,
            "compatibility_policy": "EXACT_GROUP_MATCH",
        },
    )

    RequestNotification.objects.create(
        request=blood_request,
        recipient=blood_request.requester,
        message=(
            "Your request has been approved "
            "and compatible units reserved."
        ),
    )

    return blood_request


def reserve_request(request_id, actor):
    """Reserve blood units with retry handling and operational logging."""

    for attempt in range(3):
        try:
            result = _reserve_request_once(request_id, actor)

            logger.info(
                "Blood request reservation completed successfully."
            )

            return result

        except WorkflowError:
            logger.warning(
                "Blood request reservation rejected due to workflow validation."
            )
            raise

        except OperationalError:
            if attempt == 2:
                logger.error(
                    "Blood request reservation failed after 3 attempts "
                    "because of database contention."
                )

                raise WorkflowError(
                    "Inventory is busy due to another update; please retry."
                ) from None

            logger.warning(
                "Database contention during blood request reservation. "
                "Retry attempt %s of 3.",
                attempt + 1,
            )

            time.sleep(0.05 * (attempt + 1))


@transaction.atomic
def _issue_request_once(request_id, actor):
    """Issue all compatible, unexpired reserved units atomically."""

    blood_request = BloodRequest.objects.select_for_update().get(
        request_id=request_id
    )

    if blood_request.status != BloodRequest.Status.RESERVED:
        raise WorkflowError(
            "Only a request with reserved units can be issued."
        )

    today = timezone.localdate()

    units = list(
        BloodUnit.objects.select_for_update().filter(
            reserved_for=blood_request,
            status="RESERVED",
            expiry_date__gte=today,
            donation__accepted=True,
            donation__component=blood_request.component,
        )
    )

    compatible_units = [
        unit for unit in units
        if is_blood_compatible(
            unit.donation.blood_group,
            blood_request.blood_group,
            blood_request.component,
        )
    ]

    if len(compatible_units) != blood_request.units_required:
        raise WorkflowError(
            "The reserved inventory is incomplete, incompatible or expired."
        )

    unit_ids = [unit.pk for unit in compatible_units]
    now = timezone.now()

    changed = BloodUnit.objects.filter(
        pk__in=unit_ids,
        reserved_for=blood_request,
        status="RESERVED",
        expiry_date__gte=today,
        donation__accepted=True,
        donation__component=blood_request.component,
    ).update(
        status="ISSUED",
        issued_at=now,
        issued_by=actor,
    )

    if changed != blood_request.units_required:
        raise WorkflowError(
            "Inventory changed while issuing; please retry."
        )

    updated = BloodRequest.objects.filter(
        pk=blood_request.pk,
        status=BloodRequest.Status.RESERVED,
    ).update(
        status=BloodRequest.Status.ISSUED
    )

    if updated != 1:
        raise WorkflowError(
            "Request status changed while issuing; please retry."
        )

    record_audit(
        actor,
        "REQUEST_ISSUED",
        "BloodRequest",
        blood_request.request_id,
        {"unit_count": changed},
    )

    RequestNotification.objects.create(
        request=blood_request,
        recipient=blood_request.requester,
        message="Your reserved units have been issued / dispatched.",
    )

    return blood_request


def issue_request(request_id, actor):
    """Issue reserved blood units with retry handling and logging."""

    for attempt in range(3):
        try:
            result = _issue_request_once(request_id, actor)

            logger.info(
                "Blood request issuance completed successfully."
            )

            return result

        except WorkflowError:
            logger.warning(
                "Blood request issuance rejected due to workflow validation."
            )
            raise

        except OperationalError:
            if attempt == 2:
                logger.error(
                    "Blood request issuance failed after 3 attempts "
                    "because of database contention."
                )

                raise WorkflowError(
                    "Inventory is busy due to another update; please retry."
                ) from None

            logger.warning(
                "Database contention during blood request issuance. "
                "Retry attempt %s of 3.",
                attempt + 1,
            )

            time.sleep(0.05 * (attempt + 1))
