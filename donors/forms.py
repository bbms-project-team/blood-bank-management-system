
from django import forms
from .models import DonorProfile


class DonorProfileForm(forms.ModelForm):
    class Meta:
        model = DonorProfile
        fields = [
            "phone",
            "date_of_birth",
            "address",
            "blood_group",
            "last_donation_date",
            "eligibility_notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "last_donation_date": forms.DateInput(attrs={"type": "date"}),
        }
