
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import User

from .forms import BloodRequestForm
from .models import BloodRequest


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
        {"requests": requests},
    )


@role_required(User.Role.STAFF, User.Role.ADMIN)
def decide_request(request, request_id):
    blood_request = get_object_or_404(
        BloodRequest,
        request_id=request_id,
    )

    if request.method == "POST":
        decision = request.POST.get("decision")

        if decision not in [
            BloodRequest.Status.APPROVED,
            BloodRequest.Status.REJECTED,
        ]:
            messages.error(request, "Invalid decision.")
            return redirect("my_requests")

        if blood_request.status != BloodRequest.Status.PENDING:
            messages.error(
                request,
                "This request has already been decided.",
            )
            return redirect("my_requests")

        blood_request.status = decision
        blood_request.decision_by = request.user
        blood_request.decision_at = timezone.now()
        blood_request.save(
            update_fields=[
                "status",
                "decision_by",
                "decision_at",
            ]
        )

        messages.success(
            request,
            f"Request {blood_request.request_id} "
            f"{decision.lower()} successfully.",
        )

    return redirect("my_requests")
