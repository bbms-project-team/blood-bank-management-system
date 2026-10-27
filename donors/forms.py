
from django import forms
from django.utils import timezone
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

    def clean_date_of_birth(self):
        value = self.cleaned_data["date_of_birth"]
        if value > timezone.localdate():
            raise forms.ValidationError("Date of birth cannot be in the future.")
        return value

    def clean_last_donation_date(self):
        value = self.cleaned_data.get("last_donation_date")
        if value and value > timezone.localdate():
            raise forms.ValidationError("Last donation date cannot be in the future.")
        return value
