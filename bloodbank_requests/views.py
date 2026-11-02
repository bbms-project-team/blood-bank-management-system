
from datetime import timedelta
import logging

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import User

from .forms import BloodRequestForm
from .models import AuditLog, BloodRequest, RequestNotification
from .services import WorkflowError, reserve_request as reserve_request_service
from .services import issue_request as issue_request_service

logger = logging.getLogger(__name__)


def _workflow_error(request, operation, code, message, status):
    request_id = request.resolver_match.kwargs.get("request_id")
    logger.warning(
        "Blood request operation failed operation=%s code=%s request_id=%s user_id=%s",
        operation,
        code,
        request_id,
        request.user.pk,
    )
    if request.accepts("application/json"):
        return JsonResponse(
            {"error": {"code": code, "message": message}},
            status=status,
        )
    messages.error(request, message)
    return redirect("my_requests")


@role_required(User.Role.REQUESTER, User.Role.ADMIN)
def submit_request(request):
    if request.method == "POST":
        form = BloodRequestForm(request.POST)

        if form.is_valid():
            blood_request = form.save(commit=False)
            blood_request.requester = request.user
            blood_request.save()

            messages.success(
                request,
                f"Blood request submitted successfully. "
                f"Request ID: {blood_request.request_id}",
            )
            return redirect("my_requests")
    else:
        form = BloodRequestForm()

    return render(
        request,
        "bloodbank_requests/submit_request.html",
        {"form": form},
    )


@role_required(
    User.Role.REQUESTER,
    User.Role.STAFF,
    User.Role.ADMIN,
)
def my_requests(request):
    if request.user.role == User.Role.REQUESTER:
        requests = BloodRequest.objects.filter(
            requester=request.user
        ).order_by("-created_at")
    else:
        requests = BloodRequest.objects.all().order_by("-created_at")

    return render(
        request,
        "bloodbank_requests/my_requests.html",
        {
            "requests": requests,
            "notifications": RequestNotification.objects.filter(
                recipient=request.user,
                read_at__isnull=True,
            ) if request.user.role == User.Role.REQUESTER else [],
        },
    )


@role_required(User.Role.REQUESTER)
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(
        RequestNotification,
        pk=notification_id,
        recipient=request.user,
    )
    RequestNotification.objects.filter(
        pk=notification.pk,
        recipient=request.user,
        read_at__isnull=True,
    ).update(read_at=timezone.now())
    return redirect("my_requests")


@role_required(User.Role.STAFF, User.Role.ADMIN)
def decide_request(request, request_id):
    try:
        blood_request = BloodRequest.objects.get(request_id=request_id)
    except BloodRequest.DoesNotExist:
        return _workflow_error(
            request,
            "decide",
            "request_not_found",
            "Request was not found.",
            404,
        )

    if request.method != "POST":
        return _workflow_error(
            request,
            "decide",
            "method_not_allowed",
            "Submit this action using POST.",
            405,
        )

    decision = request.POST.get("decision")
    if decision not in [
        BloodRequest.Status.APPROVED,
        BloodRequest.Status.REJECTED,
    ]:
        return _workflow_error(
            request,
            "decide",
            "invalid_decision",
            "Invalid decision.",
            400,
        )

    if blood_request.status != BloodRequest.Status.PENDING:
        return _workflow_error(
            request,
            "decide",
            "request_already_decided",
            "This request has already been decided.",
            409,
        )

    with transaction.atomic():
        updated = BloodRequest.objects.filter(
            pk=blood_request.pk,
            status=BloodRequest.Status.PENDING,
        ).update(
            status=decision,
            decision_by=request.user,
            decision_at=timezone.now(),
        )
        if updated != 1:
            return _workflow_error(
                request,
                "decide",
                "request_already_decided",
                "This request has already been decided.",
                409,
            )
        AuditLog.objects.create(
            actor=request.user,
            action=f"REQUEST_{decision}",
            object_type="BloodRequest",
            object_id=str(blood_request.request_id),
        )
        RequestNotification.objects.create(
            request=blood_request,
            recipient=blood_request.requester,
            message=f"Your blood request was {decision.lower()}.",
        )

    messages.success(
        request,
        f"Request {blood_request.request_id} "
        f"{decision.lower()} successfully.",
    )

    return redirect("my_requests")


@role_required(User.Role.STAFF, User.Role.ADMIN)
def reserve_request(request, request_id):
    if request.method != "POST":
        return _workflow_error(
            request, "reserve", "method_not_allowed", "Submit this action using POST.", 405
        )
    try:
        reserve_request_service(request_id, request.user)
    except BloodRequest.DoesNotExist:
        return _workflow_error(
            request,
            "reserve",
            "request_not_found",
            "Request was not found.",
            404,
        )
    except WorkflowError as exc:
        return _workflow_error(
            request, "reserve", "reservation_failed", str(exc), 409
        )
    else:
        messages.success(request, "Matching units reserved for this request.")
    return redirect("my_requests")


@role_required(User.Role.STAFF, User.Role.ADMIN)
def issue_request(request, request_id):
    if request.method != "POST":
        return _workflow_error(
            request, "issue", "method_not_allowed", "Submit this action using POST.", 405
        )
    try:
        issue_request_service(request_id, request.user)
    except BloodRequest.DoesNotExist:
        return _workflow_error(
            request,
            "issue",
            "request_not_found",
            "Request was not found.",
            404,
        )
    except WorkflowError as exc:
        return _workflow_error(
            request, "issue", "dispatch_failed", str(exc), 409
        )
    else:
        messages.success(request, "Reserved units issued and request completed.")
    return redirect("my_requests")


@role_required(User.Role.STAFF, User.Role.ADMIN)
def alerts(request):
    from donations.models import BloodUnit, Donation
    from donors.models import DonorProfile

    today = timezone.localdate()
    soon = today + timedelta(days=7)
    threshold = getattr(settings, "BBMS_LOW_STOCK_THRESHOLD", 5)
    available = BloodUnit.objects.filter(
        status="AVAILABLE",
        expiry_date__gte=today,
        donation__accepted=True,
    )
    grouped_stock = {
        (row["donation__blood_group"], row["donation__component"]): row["units"]
        for row in available.values("donation__blood_group", "donation__component")
        .annotate(units=Count("pk"))
    }
    stock = [
        {
            "donation__blood_group": blood_group,
            "donation__component": component,
            "units": grouped_stock.get((blood_group, component), 0),
        }
        for blood_group, _ in DonorProfile.BLOOD_GROUPS
        for component, _ in Donation.COMPONENTS
        if grouped_stock.get((blood_group, component), 0) < threshold
    ]
    stock = sorted(
        stock,
        key=lambda item: (
            item["donation__blood_group"],
            item["donation__component"],
        ),
    )
    expiring = BloodUnit.objects.filter(
        status__in=["AVAILABLE", "RESERVED"],
        expiry_date__range=(today, soon),
    ).select_related("donation")
    expired = BloodUnit.objects.filter(
        status__in=["AVAILABLE", "RESERVED"],
        expiry_date__lt=today,
    ).select_related("donation")
    return render(request, "bloodbank_requests/alerts.html", {
        "stock_alerts": stock,
        "expiring_units": expiring,
        "expired_units": expired,
        "threshold": threshold,
    })


@role_required(User.Role.STAFF, User.Role.ADMIN)
def reports(request):
    from donations.models import BloodUnit, Donation

    today = timezone.localdate()
    return render(request, "bloodbank_requests/reports.html", {
        "donation_count": Donation.objects.filter(accepted=True).count(),
        "requests_by_status": BloodRequest.objects.values("status")
            .annotate(total=Count("pk")).order_by("status"),
        "units_by_status": BloodUnit.objects.values("status")
            .annotate(total=Count("pk")).order_by("status"),
        "available_units": BloodUnit.objects.filter(
            status="AVAILABLE", expiry_date__gte=today,
            donation__accepted=True,
        ).count(),
    })


@role_required(User.Role.ADMIN)
def audit_log(request):
    events = AuditLog.objects.select_related("actor")[:200]
    return render(request, "bloodbank_requests/audit_log.html", {"events": events})
