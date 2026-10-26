
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404

from accounts.decorators import role_required
from accounts.models import User
from .forms import DonorProfileForm
from .models import DonorProfile


@role_required(User.Role.DONOR)
def my_profile(request):
    profile = DonorProfile.objects.filter(user=request.user).first()

    if request.method == "POST":
        form = DonorProfileForm(request.POST, instance=profile)
        if form.is_valid():
            donor_profile = form.save(commit=False)
            donor_profile.user = request.user
            donor_profile.save()
            messages.success(request, "Donor profile saved successfully.")
            return redirect("my_profile")
    else:
        form = DonorProfileForm(instance=profile)

    return render(
        request,
        "donors/profile.html",
        {"form": form, "profile": profile},
    )


@role_required(User.Role.STAFF, User.Role.ADMIN)
def donor_list(request):
    profiles = DonorProfile.objects.select_related("user").all()
    return render(
        request,
        "donors/donor_list.html",
        {"profiles": profiles},
    )
